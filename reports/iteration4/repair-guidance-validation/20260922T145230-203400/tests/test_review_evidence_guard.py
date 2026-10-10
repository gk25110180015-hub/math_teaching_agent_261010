"""Pipeline guard and durable replay regressions using synthetic providers only."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.pipeline import Pipeline
from math_agent.review_evidence_attribution import detect_attribution_conflicts
from math_agent.settings import Settings
from math_agent.util import AgentError, digest, write_json

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'reports/iteration4/review-evidence-attribution-fixtures.json').read_bytes())['cases']


def verdict(case, disposition=None):
    conflict = detect_attribution_conflicts(case['original_review'], case['units'], case['prior_sections'])[0]
    target = next(u for u in case['units'] if u['id'] == conflict['target_unit_id'])
    source = next(u for section in case['prior_sections'] for u in section['units'] if u['id'] == conflict['matches'][0]['source_unit_id'])
    if disposition is None:
        disposition = 'misattributed_or_withdrawn' if case['case_id'].startswith('saved_') else 'dependency_supported'
    target_quote = target['tex']
    if '最后设' in target_quote:
        target_quote = target_quote[target_quote.index('最后设'):]
    remaining = None if disposition in ('misattributed_or_withdrawn', 'unresolved') else copy.deepcopy(case['original_review']['issues'][0])
    return {'decisions': [{'issue_index': conflict['issue_index'], 'issue_hash': conflict['issue_hash'],
        'disposition': disposition, 'reason': '依据当前目标的逐字正文和真实来源重新核对原指称；目标与来源不得混为同一个单元。',
        'target_spans': [{'unit_id': target['id'], 'quote': target_quote}],
        'source_spans': [{'unit_id': source['id'], 'quote': source['tex'][:350]}],
        'remaining_issue': remaining}], 'limitations': ['Synthetic verdict for workflow testing; not a mathematical model evaluation.']}


class Provider:
    def __init__(self, case, responses):
        self.case = case
        self.responses = list(responses)
        self.calls = []

    def generate(self, role, context, schema):
        self.calls.append({'role': role, 'context': copy.deepcopy(context)})
        if role == 'reviewer_math':
            return copy.deepcopy(self.case['original_review'])
        assert role == 'review_evidence_attribution'
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


def pipeline(tmp_path, case, responses):
    p = object.__new__(Pipeline)
    p.settings = Settings(workspace=tmp_path)
    p.root = tmp_path / 'run'
    p.root.mkdir(exist_ok=True)
    p.model_id = 'gpt6'
    p.run = {'input': {'provider': 'live'}}
    p.provider = Provider(case, responses)
    return p


def invoke(p, case, label='local', context_extra=None):
    context = {'plan': {'hash': 'approved-plan', 'revision': 2, 'lecture': {'answers_location': 'end'}},
               'prior_sections': case['prior_sections'], 'scope': {'kind': 'section_local'}}
    context.update(context_extra or {})
    return p.review_units(case['units'], context, p.root / ('draft-' + label), label)


def state(p):
    path, = (p.root / 'review-attribution').glob('*/state.json')
    return path, json.loads(path.read_bytes())


def test_real_wrong_owner_gets_one_explicit_withdrawal_preserves_other_issue_and_replays(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case)])
    result = invoke(p, case)
    assert result['issues'] == case['original_review']['issues'][1:]
    path, saved = state(p)
    assert saved['status'] == 'RESOLVED' and saved['verification_calls'] == 1
    assert json.loads((path.parent / 'original-review.json').read_bytes()) == case['original_review']
    assert 'adjudication-response-1.json' in saved['dependencies']
    assert invoke(p, case, 'new-build-after-restart') == result
    assert [c['role'] for c in p.provider.calls] == ['reviewer_math', 'review_evidence_attribution']


@pytest.mark.parametrize('disposition', ['dependency_supported', 'target_supported'])
def test_legitimate_dependency_remains_blocking_on_original_target(tmp_path, disposition):
    case = copy.deepcopy(CASES[1])
    p = pipeline(tmp_path, case, [verdict(case, disposition)])
    result = invoke(p, case)
    assert len(result['issues']) == 1
    assert result['issues'][0]['unit_id'] == 'S04.U05'
    assert result['issues'][0]['severity'] == 'blocking'
    assert 'S02.U01:' in result['issues'][0]['evidence']
    assert detect_attribution_conflicts(result, case['units'], case['prior_sections']) == []


@pytest.mark.parametrize('bad', ['empty', 'unresolved', 'absent_target', 'wrong_source', 'out_of_scope', 'missing_counterevidence'])
def test_completed_unreliable_verdict_stays_blocked_without_reroll(tmp_path, bad):
    case = copy.deepcopy(CASES[0])
    response = verdict(case)
    decision = response['decisions'][0]
    if bad == 'empty':
        response['decisions'] = []
    elif bad == 'unresolved':
        decision['disposition'] = 'unresolved'
    elif bad == 'absent_target':
        decision['target_spans'][0]['quote'] = '这句话不存在于目标正文，不能充当撤销依据。'
    elif bad == 'wrong_source':
        decision['source_spans'][0]['unit_id'] = 'S99.U99'
    elif bad == 'out_of_scope':
        decision['disposition'] = 'target_supported'
        decision['remaining_issue'] = {**case['original_review']['issues'][0], 'unit_id': 'S02.U03'}
    else:
        decision['target_spans'] = []
    p = pipeline(tmp_path, case, [response, verdict(case)])
    for label in ('first', 'retry'):
        with pytest.raises(AgentError) as caught:
            invoke(p, case, label)
        assert caught.value.code == 'REVIEW_EVIDENCE_BLOCKED'
    assert len(p.provider.calls) == 2
    assert state(p)[1]['status'] == 'UNRESOLVED'
    assert not list(p.root.rglob('repair-*-patch.json'))


def test_all_routes_transport_failure_resumes_same_slot_without_ordinary_review(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [AgentError('PROVIDER_ALL_UNAVAILABLE', '三模型均返回传输错误；无完成裁定'), verdict(case)])
    with pytest.raises(AgentError, match='归属定点核实'):
        invoke(p, case)
    path, saved = state(p)
    first_input = (path.parent / 'adjudication-input.json').read_bytes()
    assert saved['status'] == 'TRANSPORT_PENDING'
    result = invoke(p, case, 'retry')
    assert result['issues'] == case['original_review']['issues'][1:]
    assert [c['role'] for c in p.provider.calls] == ['reviewer_math', 'review_evidence_attribution', 'review_evidence_attribution']
    assert p.provider.calls[1]['context'] == p.provider.calls[2]['context']
    assert (path.parent / 'adjudication-input.json').read_bytes() == first_input
    assert (path.parent / 'adjudication-failure-1.json').exists()
    assert state(p)[1]['verification_calls'] == 2


def test_request_budget_error_preserves_existing_increase_and_retry_protocol(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [AgentError('BUDGET_EXHAUSTED', '模型请求预算已用尽'), verdict(case)])
    with pytest.raises(AgentError) as caught:
        invoke(p, case)
    assert caught.value.code == 'BUDGET_EXHAUSTED'
    assert state(p)[1]['status'] == 'TRANSPORT_PENDING'
    # In the real workflow Service.retry requires an explicit budget increase;
    # this unit test resumes only after the synthetic provider permits the call.
    result = invoke(p, case, 'after-explicit-increase')
    assert result['issues'] == case['original_review']['issues'][1:]
    assert [item['role'] for item in p.provider.calls].count('reviewer_math') == 1


def test_received_response_is_validated_after_crash_without_new_provider_draw(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [AgentError('PROVIDER_TIMEOUT', '模拟未完成')])
    with pytest.raises(AgentError):
        invoke(p, case)
    path, saved = state(p)
    response = path.parent / 'adjudication-response-1.json'
    write_json(response, verdict(case))
    saved.update(status='RESPONSE_RECEIVED', response_file=response.name)
    saved['dependencies'][response.name] = digest(response.read_bytes())
    write_json(path, saved)
    result = invoke(p, case, 'restart')
    assert result['issues'] == case['original_review']['issues'][1:]
    assert len(p.provider.calls) == 2


def test_tampered_original_evidence_blocks_replay(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case)])
    invoke(p, case)
    path, _ = state(p)
    (path.parent / 'original-review.json').write_text('{}', encoding='utf-8')
    with pytest.raises(AgentError) as caught:
        invoke(p, case, 'retry')
    assert caught.value.code == 'REVIEW_EVIDENCE_CACHE_INVALID'
    assert len(p.provider.calls) == 2


def test_orphan_response_after_crash_blocks_without_another_draw(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [AgentError('PROVIDER_TIMEOUT', '模拟未完成'), verdict(case)])
    with pytest.raises(AgentError):
        invoke(p, case)
    path, _ = state(p)
    write_json(path.parent / 'adjudication-response-1.json', verdict(case))
    with pytest.raises(AgentError) as caught:
        invoke(p, case, 'restart')
    assert caught.value.code == 'REVIEW_EVIDENCE_CACHE_INVALID'
    assert len(p.provider.calls) == 2


def test_scope_validation_retry_preserves_actual_accepted_payload(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case)])
    original_generate = p.provider.generate
    failed = False

    def generate(role, context, schema):
        nonlocal failed
        if role == 'reviewer_math' and not failed:
            failed = True
            bad = copy.deepcopy(case['original_review'])
            bad['issues'][0]['unit_id'] = 'S99.U99'
            p.provider.calls.append({'role': role, 'context': copy.deepcopy(context)})
            return bad
        return original_generate(role, context, schema)

    p.provider.generate = generate
    result = invoke(p, case)
    path, saved = state(p)
    accepted = json.loads((path.parent / 'accepted-review-input.json').read_bytes())
    assert accepted['review_validation_feedback']['invalid_issue_unit_ids'] == ['S99.U99']
    verification = json.loads((path.parent / 'adjudication-input.json').read_bytes())
    assert verification['review_context'] == accepted
    assert saved['accepted_payload_hash'] == digest(accepted)
    assert invoke(p, case, 'restart') == result
    assert len(p.provider.calls) == 3


def test_new_formal_job_rechecks_while_same_job_retry_replays(tmp_path):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case), verdict(case)])
    p.job = {'id': 'first-approved-build'}
    invoke(p, case)
    invoke(p, case, 'same-job-retry')
    assert len(p.provider.calls) == 2
    p.job = {'id': 'new-formal-recheck'}
    invoke(p, case, 'new-job')
    assert len(p.provider.calls) == 4


def test_expired_worker_lease_cannot_write_guard_state(tmp_path):
    from contextlib import contextmanager
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case)])

    class ExpiredStore:
        @contextmanager
        def transaction(self):
            yield object()

        def assert_fence(self, connection, job):
            raise AgentError('STALE_JOB', '旧worker已经失去租约')

    p.store = ExpiredStore()
    p.job = {'id': 'expired-job'}
    with pytest.raises(AgentError) as caught:
        invoke(p, case)
    assert caught.value.code == 'STALE_JOB'
    assert not list(p.root.rglob('state.json'))
    assert [c['role'] for c in p.provider.calls] == ['reviewer_math']


@pytest.mark.parametrize('change', ['target', 'dependency', 'plan'])
def test_changed_actual_context_cannot_reuse_prior_disposition(tmp_path, change):
    case = copy.deepcopy(CASES[0])
    p = pipeline(tmp_path, case, [verdict(case)])
    invoke(p, case)
    extra = None
    if change == 'target':
        case['units'][0]['tex'] += '\n新目标正文。'
    elif change == 'dependency':
        case['prior_sections'][0]['units'][0]['tex'] += '\n新的实际依赖正文。'
    else:
        extra = {'plan': {'hash': 'different-approved-plan', 'revision': 3, 'lecture': {'answers_location': 'end'}}}
    p.provider.case = case
    p.provider.responses.append(verdict(case))
    invoke(p, case, 'changed', extra)
    assert len(p.provider.calls) == 4
    assert len(list((p.root / 'review-attribution').glob('*/state.json'))) == 2


def test_new_contract_fingerprints_helper_prompt_and_schema(tmp_path):
    p = pipeline(tmp_path, copy.deepcopy(CASES[0]), [])
    contract = p._section_check_contract()
    assert 'review_evidence_attribution.py' in contract['source_hashes']
    assert len(contract['review_attribution_contract']['adjudicator_prompt_sha256']) == 64
    assert len(contract['review_attribution_contract']['adjudication_schema_sha256']) == 64
