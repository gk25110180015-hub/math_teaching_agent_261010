"""Offline disposition regression: real SQLite, injected models/compiler, no API."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.mathcheck import check_math
from math_agent.pipeline import Pipeline
from math_agent.provider import MockProvider
from math_agent.uncertainty_review import (
    UncertaintyAssessment, UncertaintyReview, build_uncertainty_context, declared_doubts,
    declared_issues, located_math_issues, validate_uncertainty_assessment, effective_uncertainty_issues,
    prior_same_body_issues,
)
from math_agent.util import AgentError, digest, write_json
from test_local_recovery import Provider, setup, state, direct_recovery


def section():
    value = Provider().generate('writer_lecture_section', {}, None)
    value['uncertainties'] = ['S01.U1 该单元对正整数索引和定义范围的说明仍需核对。']
    return value


def context():
    value = section()
    return build_uncertainty_context({'hash': 'plan', 'revision': 2}, value, [], check_math(value), [], False)


def assessment(ctx, status='resolved_by_current_body'):
    return {'items': [{'uncertainty_id': item['uncertainty_id'], 'unit_id': item['unit_id'],
        'disposition': status, 'reason': '已核对该实际单元的完整定义和索引条件，这是受控 mock 判断，不代表真实数学验收。',
        'evidence': [{'source_key': source['source_key'], 'source_sha256': source['source_sha256'], 'quote': source['tex']}]
            if (source := next((s for s in ctx['sources'] if s['source_key'] == 'current:' + str(item['unit_id'])), None)) else [],
        'remaining_dependency': status == 'open_dependency',
        'repair_instruction': '只在该已存在的目标单元明确原本欠缺的定义前提。' if status == 'open_actionable' else None}
        for item in ctx['declared_doubts']], 'limitations': ['Injected mock assessment, no teacher review.']}


def test_saved_ch03_doubt_binds_exact_owner_without_changing_original_evidence():
    root = Path(__file__).resolve().parent/'fixtures/uncertainty_ch03'
    value = json.loads((root/'2-candidate-becc07d4d97b.json').read_bytes())
    report = json.loads((root/'1-review-1f3161930303.json').read_bytes())['report']
    original = copy.deepcopy((value, report))
    doubts = declared_doubts(value)
    assert doubts[0]['unit_id'] == 'S03.U04'
    issues = located_math_issues(value, report['math'])
    assert len(issues) == 1 and issues[0]['location'] == {'unit_id': 'S03.U04'}
    assert issues[0]['message'] == value['uncertainties'][0]
    assert original == (value, report)
    assert report['llm_review']['issues'][0]['severity'] == 'review'
    assert report['math']['issues'][0]['location'] == {}


@pytest.mark.parametrize('text,target', [
    ('S01.U1 原疑点需要核对。', 'S01.U1'), ('  S01.U1：原疑点需要核对。', 'S01.U1'),
    ('S01.U1:原疑点需要核对。', 'S01.U1'), ('S01.U1.answer 原答案需要核对。', 'S01.U1.answer'),
    ('文中涉及 S01.U1 的内容。', None), ('S01.U10 原疑点需要核对。', None),
    ('S02.U1 原疑点需要核对。', None), ('S01.U1/ S01.U2 两单元需要核对。', None),
    ('S01.U1', None), ('S01.U1x 原疑点需要核对。', None),
])
def test_positive_prefix_binding_only(text, target):
    value = section()
    value['units'].append({'id': 'S01.U1.answer', 'kind': 'solution', 'tex': '答案正文已实际提供且可以独立核查。', 'relates_to': None})
    value['uncertainties'] = [text]
    assert declared_doubts(value)[0]['unit_id'] == target


def test_full_note_hash_not_truncated_and_duplicates_have_stable_occurrence_ids():
    value = section()
    value['uncertainties'] = ['S01.U1 ' + '甲' * 1100 + 'A', 'S01.U1 ' + '甲' * 1100 + 'B']
    ids = declared_doubts(value)
    assert ids[0]['original_sha256'] != ids[1]['original_sha256']
    value['uncertainties'].append(value['uncertainties'][0])
    after = declared_doubts(value)
    assert after[:2] == ids and after[0]['uncertainty_id'] != after[2]['uncertainty_id']


@pytest.mark.parametrize('damage', ['empty', 'duplicate', 'wrong_id', 'wrong_owner', 'blank_quote', 'wrong_quote',
                                   'wrong_sha', 'blank_reason', 'external_source', 'remaining_dependency', 'no_current_evidence'])
def test_invalid_resolutions_are_rejected(damage):
    ctx = context()
    value = assessment(ctx)
    item = value['items'][0]
    if damage == 'empty': value['items'] = []
    elif damage == 'duplicate': value['items'].append(copy.deepcopy(item))
    elif damage == 'wrong_id': item['uncertainty_id'] = 'made-up'
    elif damage == 'wrong_owner': item['unit_id'] = 'S01.U2'
    elif damage == 'blank_quote': item['evidence'][0]['quote'] = ' ' * 20
    elif damage == 'wrong_quote': item['evidence'][0]['quote'] = '这段不存在的证明不可以作为真实证据。'
    elif damage == 'wrong_sha': item['evidence'][0]['source_sha256'] = '0' * 64
    elif damage == 'blank_reason': item['reason'] = ' ' * 20
    elif damage == 'external_source': item['evidence'][0]['source_key'] = 'unprovided:textbook'
    elif damage == 'remaining_dependency': item['remaining_dependency'] = True
    elif damage == 'no_current_evidence': item['evidence'] = []
    with pytest.raises(ValueError): validate_uncertainty_assessment(value, ctx)


def test_resolving_declared_note_does_not_turn_symbolic_unknown_into_pass():
    value = section()
    raw = check_math(value)
    raw['issues'].append({'rule_id': 'MATH_CHECK_UNKNOWN', 'severity': 'review', 'location': {'unit_id': 'S01.U1'}, 'message': 'UNKNOWN'})
    ctx = build_uncertainty_context({'hash': 'p', 'revision': 1}, value, [], raw, [])
    result = validate_uncertainty_assessment(assessment(ctx), ctx)
    effective = [i for i in located_math_issues(value, raw) if i['rule_id'] != 'DECLARED_MATH_UNCERTAINTY'] + effective_uncertainty_issues(value, result)
    assert effective[0]['rule_id'] == 'MATH_CHECK_UNKNOWN' and effective[0]['severity'] == 'review'
    assert raw['status'] == 'NEEDS_REVIEW' and value['uncertainties']


class DoubtProvider(Provider):
    def __init__(self, disposition=None, failure=None, ordinary_error=False):
        super().__init__()
        self.disposition = disposition
        self.failure = failure
        self.ordinary_error = ordinary_error
        self.doubt_calls = []

    def generate(self, role, ctx, schema):
        if role == 'writer_lecture_section':
            self.writes += 1
            return section()
        if role == 'reviewer_uncertainty':
            self.doubt_calls.append(copy.deepcopy(ctx))
            if self.failure:
                code = self.failure
                self.failure = None
                raise AgentError(code, 'Synthetic saved-slot failure')
            fixed = '已明示前提' in ctx['section']['units'][0]['tex']
            status = self.disposition or ('resolved_by_current_body' if fixed else 'open_actionable')
            result = assessment(ctx, status)
            if status == 'invalid': result['items'] = []
            return result
        if role == 'reviewer_math':
            self.reviews += 1
            return {'issues': [{'unit_id': 'S01.U1', 'severity': 'blocking', 'message': '仍存在独立数学错误。', 'evidence': '受控 mock 普通审阅原结论。'}] if self.ordinary_error and self.reviews == 1 else [],
                    'checked_unit_ids': [u['id'] for u in ctx['units']], 'limitations': ['Mock ordinary review.']}
        return super().generate(role, ctx, schema)


def test_actual_patch_resolves_note_but_preserves_original_metadata_and_budget(tmp_path, monkeypatch):
    provider = DoubtProvider()
    service, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    approval = copy.deepcopy(service.store.get_run(p.run['id'])['approval'])
    completed, reports = p.lecture(plan)
    assert completed[0][1]['uncertainties'] == section()['uncertainties']
    assert provider.writes == provider.patches == 1 and len(provider.doubt_calls) == 2 and len(compiled) == 1
    assert state(p)['unit_applied_counts'] == {'S01.U1': 1}
    local = reports[0]
    assert local['math']['status'] == 'NEEDS_REVIEW'
    assert local['math']['issues'][0]['rule_id'] == 'DECLARED_MATH_UNCERTAINTY'
    assert not local['issues']
    assert local['uncertainty_review']['assessment']['items'][0]['disposition'] == 'resolved_by_current_body'
    assert service.store.get_run(p.run['id'])['approval'] == approval and not service.store.get_run(p.run['id'])['reviews']
    saved = list((p.root/'uncertainty-reviews').glob('*/state.json'))
    assert len(saved) == 2


@pytest.mark.parametrize('status,code', [('open_dependency', 'UNCERTAINTY_DEPENDENCY_BLOCKED'), ('invalid', 'UNCERTAINTY_REVIEW_BLOCKED')])
def test_completed_unresolved_or_invalid_does_not_redraw_on_retry(tmp_path, monkeypatch, status, code):
    provider = DoubtProvider(disposition=status)
    _, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for _ in range(2):
        with pytest.raises(AgentError) as error: p.lecture(plan)
        assert error.value.code == code
    assert len(provider.doubt_calls) == provider.reviews == 1
    assert provider.patches == 0 and not compiled
    if status == 'open_dependency':
        saved = state(p)
        assert len(saved['pending_issues']) == 1 and saved['pending_issues'][0]['location'] == {'unit_id': 'S01.U1'}


@pytest.mark.parametrize('failure', ['PROVIDER_ALL_UNAVAILABLE', 'PROVIDER_EMPTY_RESPONSE', 'BUDGET_EXHAUSTED'])
def test_transport_retry_preserves_ordinary_concern_and_exact_input(tmp_path, monkeypatch, failure):
    provider = DoubtProvider(disposition='open_dependency', failure=failure, ordinary_error=True)
    service, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error: p.lecture(plan)
    assert error.value.code == ('BUDGET_EXHAUSTED' if failure == 'BUDGET_EXHAUSTED' else 'UNCERTAINTY_REVIEW_BLOCKED')
    with pytest.raises(AgentError) as error: p.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    assert provider.doubt_calls[0] == provider.doubt_calls[1]
    assert provider.reviews == 1 and provider.patches == 0 and not compiled
    assert any(i['severity'] == 'blocking' and i['message'] == '仍存在独立数学错误。' for i in state(p)['pending_issues'])
    assert not service.store.get_run(p.run['id'])['reviews']


def test_resolved_assessment_cannot_clear_ordinary_math_blocker(tmp_path, monkeypatch):
    provider = DoubtProvider(disposition='resolved_by_current_body', ordinary_error=True)
    _, p, plan, compiled = setup(tmp_path, monkeypatch, provider, max_local_repair_attempts=0)
    with pytest.raises(AgentError) as error: p.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED'
    assert state(p)['pending_issues'][0]['severity'] == 'blocking' and not compiled


def direct_guard(tmp_path, provider=None):
    value = section()
    p, plan, recovery = direct_recovery(tmp_path, value)
    p.provider = provider or DoubtProvider(disposition='open_dependency')
    ctx = build_uncertainty_context(plan, value, [], check_math(value), [], False)
    return p, recovery, UncertaintyReview(p, ctx)


def ordinary(ctx):
    return {'issues': [], 'checked_unit_ids': [u['id'] for u in ctx['section']['units']], 'limitations': ['Mock.']}


def test_job_and_model_selection_alone_do_not_reopen_a_completed_disposition(tmp_path):
    p, _, guard = direct_guard(tmp_path)
    guard.ordinary_review(lambda _: ordinary(guard.context), {'original': 'context'})
    guard.evaluate()
    old = guard.key
    p.model_id = 'deepseek-flash'
    p.job = {**p.job, 'id': 'other-job'}
    current = UncertaintyReview(p, guard.context)
    assert current.key == old
    # Read-only replay does not need a new provider call or mutate fenced state.
    result, issues = current.evaluate()
    assert issues and len(p.provider.doubt_calls) == 1


@pytest.mark.parametrize('damage', ['response', 'missing_state', 'orphan_response'])
def test_evidence_damage_never_redraws_completed_verdict(tmp_path, damage):
    p, _, guard = direct_guard(tmp_path)
    guard.ordinary_review(lambda _: ordinary(guard.context), {'original': 'context'})
    guard.evaluate()
    if damage == 'response':
        (guard.folder/'response-1.json').write_text('{}', encoding='utf-8')
    elif damage == 'missing_state':
        guard.path.unlink()
    else:
        state_data = json.loads(guard.path.read_bytes())
        state_data['dependencies'].pop('response-1.json')
        state_data.pop('response_file')
        state_data['status'] = 'STARTED'
        write_json(guard.path, state_data)
    with pytest.raises(AgentError) as error: UncertaintyReview(p, guard.context).evaluate()
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'
    assert len(p.provider.doubt_calls) == 1


def test_new_body_requires_new_explicit_disposition_but_old_evidence_stays(tmp_path):
    p, _, guard = direct_guard(tmp_path)
    guard.ordinary_review(lambda _: ordinary(guard.context), {})
    guard.evaluate()
    old_hash = digest(guard.path.read_bytes())
    value = copy.deepcopy(guard.context['section'])
    value['units'][0]['tex'] += ' 已明示前提。'
    changed = build_uncertainty_context(guard.context['plan'], value, [], check_math(value), [], False)
    other = UncertaintyReview(p, changed)
    assert other.key != guard.key
    other.ordinary_review(lambda _: ordinary(other.context), {})
    other.evaluate()
    assert digest(guard.path.read_bytes()) == old_hash and len(p.provider.doubt_calls) == 2


def test_legacy_duplicate_migration_retains_original_normal_review_issue(tmp_path):
    p, recovery, guard = direct_guard(tmp_path)
    value = guard.context['section']
    math = check_math(value)
    original = value['uncertainties'][0]
    prior = [*math['issues'], {'severity': 'review', 'message': original},
             {'unit_id': 'S01.U1', 'severity': 'review', 'message': original, 'evidence': '独立实际审阅结论，不可按相同文字删除。'}]
    identity, _ = recovery.review_context(value, math, {'issues': prior})
    recovery.record_review(prior, identity, {'math': math, 'issues': prior})
    old_path = p.settings.workspace/recovery.state['last_review_key']
    old_sha = digest(old_path.read_bytes())
    kept, mapping = prior_same_body_issues(recovery, value)
    assert kept == [prior[-1]] and len(mapping) == 2
    assert digest(old_path.read_bytes()) == old_sha and recovery.state['pending_issues'] == prior


def test_unknown_same_rule_or_known_id_does_not_authorize_erasing_issue(tmp_path):
    _, recovery, guard = direct_guard(tmp_path)
    value = guard.context['section']
    math = check_math(value)
    original = value['uncertainties'][0]
    prior = [
        {'rule_id': 'DECLARED_MATH_UNCERTAINTY', 'severity': 'review', 'message': original, 'unit_id': 'S01.U2', 'evidence': '不同来源的独立问题。'},
        {'rule_id': 'DECLARED_MATH_UNCERTAINTY', 'severity': 'review', 'message': '未知来源的不同问题。',
         'uncertainty_id': declared_doubts(value)[0]['uncertainty_id']},
    ]
    identity, _ = recovery.review_context(value, math, {'issues': prior})
    recovery.record_review(prior, identity, {'math': math, 'issues': prior})
    kept, mapping = prior_same_body_issues(recovery, value)
    assert kept == prior and not mapping


@pytest.mark.parametrize('error_code,retries', [('INVALID_MODEL_JSON', False), ('PROVIDER_ALL_UNAVAILABLE', True)])
def test_crash_after_failure_evidence_cannot_redraw_completed_invalid_response(tmp_path, monkeypatch, error_code, retries):
    p, _, guard = direct_guard(tmp_path, DoubtProvider(disposition='open_dependency', failure=error_code))
    guard.ordinary_review(lambda _: ordinary(guard.context), {})
    original = guard._evidence
    def interrupt(name, value):
        original(name, value)
        if name.startswith('failure-'):
            raise KeyboardInterrupt('Synthetic crash after committed failure evidence')
    monkeypatch.setattr(guard, '_evidence', interrupt)
    with pytest.raises(KeyboardInterrupt): guard.evaluate()
    assert json.loads(guard.path.read_bytes())['status'] == 'STARTED'
    resumed = UncertaintyReview(p, guard.context)
    if retries:
        resumed.evaluate()
        assert len(p.provider.doubt_calls) == 2
    else:
        with pytest.raises(AgentError) as error: resumed.evaluate()
        assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'
        assert len(p.provider.doubt_calls) == 1


def test_new_role_mock_never_pretends_original_doubt_was_proved():
    ctx = context()
    value = MockProvider().generate('reviewer_uncertainty', ctx, UncertaintyAssessment)
    assert value['items'][0]['disposition'] == 'open_dependency'
    assert '离线演示' in value['items'][0]['reason']


def test_uncertainty_writes_require_active_job_lease(tmp_path):
    p, _, guard = direct_guard(tmp_path)
    p.store.finish(p.job, 'FAILED', 'test', {'code': 'PROVIDER_TIMEOUT'})
    with pytest.raises(AgentError): guard.ordinary_review(lambda _: ordinary(guard.context), {})
    assert not guard.path.exists()


def test_formal_retry_after_all_models_transport_failure_finishes_same_slot(tmp_path, monkeypatch):
    provider = DoubtProvider(disposition='resolved_by_current_body', failure='PROVIDER_ALL_UNAVAILABLE')
    service, p, plan, compiled = setup(tmp_path, monkeypatch, provider)
    approval = copy.deepcopy(service.store.get_run(p.run['id'])['approval'])
    with pytest.raises(AgentError) as error: p.lecture(plan)
    old_job = p.job['id']
    service.store.finish(p.job, 'BLOCKED', 'review.section.S01', {'code': error.value.code})
    service.retry(p.run['id'])
    resumed = Pipeline(p.settings, service.store, service.store.claim('uncertainty-resume'))
    resumed.provider = provider
    resumed.run['input']['provider'] = 'live'
    completed, _ = resumed.lecture(plan)
    assert resumed.job['id'] == old_job and completed
    assert provider.writes == 1 and provider.patches == 0
    assert len(provider.doubt_calls) == 2 and provider.doubt_calls[0] == provider.doubt_calls[1]
    # One local ordinary review, then one different-scope full chapter review.
    assert provider.reviews == 2 and len(compiled) == 1
    assert service.store.get_run(p.run['id'])['approval'] == approval
    assert state(resumed)['unit_applied_counts'] == {} and state(resumed)['proposal_calls'] == 0


def test_completed_schema_error_gets_one_attempt_and_no_model_fallback(tmp_path):
    from test_model_routing import make_provider, response
    provider, calls, records, _ = make_provider(tmp_path, lambda request: response('{"items":[]}'), max_schema_repair_attempts=2)
    with pytest.raises(AgentError) as error: provider.generate('reviewer_uncertainty', context(), UncertaintyAssessment)
    assert error.value.code == 'INVALID_MODEL_JSON'
    assert len(calls) == 1 and not any(r.get('event') == 'model_fallback' for r in records)
