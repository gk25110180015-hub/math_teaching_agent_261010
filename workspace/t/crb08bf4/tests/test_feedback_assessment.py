"""Explicit feedback protocol/recovery tests. All judgments/providers/compiler are mock."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_agent.feedback_review import (FeedbackAssessment, FeedbackReview, build_feedback_context,
    extract_feedback_items, mock_feedback_assessment, validate_assessment)
from math_agent.provider import MockProvider
from math_agent.settings import Settings
from math_agent.util import AgentError, digest, write_json

PLAN = {'hash': 'approved-plan', 'revision': 2, 'objectives': ['解释原有运算法则并提供训练'],
    'exclusions': ['不含多元函数'], 'lecture': {'answers_location': 'end', 'exercises': 'with_answers'},
    'sections': [{'id': 'S01', 'objectives': ['解释原有运算法则并提供训练']}]}
UNITS = [{'id': 'S01.U01', 'tex': '正确的乘积替换定理，不能直接用于抵消。'},
    {'id': 'S01.U02', 'tex': r'现有例子只给出乘积 $x/x=1$。'},
    {'id': 'S01.U03.answer', 'tex': '本节三题的答案放在最后。'}]
FEEDBACK = {'feedback': '范围限原计划。\n1.请补充抵消反例。\n2.请核对答案导航。\n不得扩大范围。',
    'feedback_source': 'agent_audit', 'source_event': {'sequence': 42}}


def context():
    return build_feedback_context(PLAN, UNITS, FEEDBACK)


def item(fid='F1', status='supported_improvement', targets=None, repairs=None):
    targets = ['S01.U01', 'S01.U02'] if targets is None else targets
    repairs = ['S01.U02'] if repairs is None and status == 'supported_improvement' else (repairs or [])
    return {'id': fid, 'status': status, 'reason': '当前定理是正确依据，但现有乘积训练尚未展示抵消导致的差异。',
        'unit_ids': targets, 'repair_unit_ids': repairs,
        'unit_evidence': [{'unit_id': uid, 'quote': next(u['tex'] for u in UNITS if u['id'] == uid),
            'kind': 'worked_example'} for uid in targets],
        'objective_evidence': [{'section_id': 'S01', 'field': 'objectives', 'quote': PLAN['objectives'][0]}],
        'repair_instruction': '只在已有例题中补充具体正确与错误抵消结果，保留原定理。' if status == 'supported_improvement' else None}


def verdict():
    return {'items': [item(), item('F2', 'supported_improvement', ['S01.U03.answer'], ['S01.U03.answer'])],
        'limitations': ['Synthetic verdict, no real semantic assessment.']}


class Provider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, role, payload, schema):
        assert role == 'reviewer_feedback'
        self.calls.append(copy.deepcopy(payload))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


def pipeline(tmp_path, responses):
    return SimpleNamespace(settings=Settings(workspace=tmp_path), root=tmp_path/'run',
        job={'id': 'job-current'}, model_id='gpt6', run={'input': {'provider': 'live'}}, provider=Provider(responses))


def evaluate(p, units=None):
    return FeedbackReview(p, PLAN, units or UNITS, FEEDBACK).evaluate()


def state(p):
    path, = (p.root/'feedback-reviews').glob('*/state.json')
    return path, json.loads(path.read_bytes())


@pytest.mark.parametrize('text', ['1.请核对。\n2.请补充。', '1、请核对。\n2、请补充。', 'F1:请核对。\nF2:请补充。'])
def test_numbered_feedback_without_whitespace_has_fixed_per_item_ids(text):
    assert [i['id'] for i in extract_feedback_items(text)] == ['F1', 'F2']


def test_unstructured_decimal_and_indented_math_steps_do_not_split_feedback():
    for text in ['请检查这个主题。', '数值如下\n1.25 是参数\n2.50 是参数', '请核对证明：\n  1.第一步\n  2.第二步']:
        assert len(extract_feedback_items(text)) == 1
    ctx = context()
    assert ctx['feedback_text'] == FEEDBACK['feedback']
    assert ctx['feedback_items'][0]['requested_counterexample']
    assert '不得扩大范围' in ctx['feedback_items'][-1]['text']


def test_actual_repair_targets_are_distinct_from_preserved_theorem_evidence():
    receipt, issues = validate_assessment(verdict(), context())
    assert receipt['items'][0]['unit_ids'] == ['S01.U01', 'S01.U02']
    assert [i['unit_id'] for i in issues] == ['S01.U02', 'S01.U03.answer']
    assert all(i['severity'] == 'review' and '不等于数学错误' in i['message'] for i in issues)


def test_navigation_improvement_uses_actual_approved_delivery_constraint():
    response = verdict()
    response['items'][1]['objective_evidence'] = [{'section_id': None, 'field': 'lecture.answers_location', 'quote': 'end'}]
    assert validate_assessment(response, context())[1][-1]['unit_id'] == 'S01.U03.answer'


def test_outside_plan_without_matching_unit_does_not_invent_a_target():
    response = verdict()
    response['items'][1] = item('F2', 'out_of_scope', [], [])
    response['items'][1]['objective_evidence'] = [{'section_id': None, 'field': 'exclusions', 'quote': '不含多元函数'}]
    assert validate_assessment(response, context())[0]['items'][1]['unit_ids'] == []


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'no_quote', 'wrong_quote', 'blank_quote',
    'blank_plan', 'blank_reason', 'bad_plan', 'repair_unquoted', 'repair_missing', 'counterexample_warning'])
def test_invalid_item_evidence_or_coverage_cannot_be_called_complete(change):
    response = verdict()
    first = response['items'][0]
    if change == 'missing': response['items'].pop()
    elif change == 'duplicate': response['items'][1]['id'] = 'F1'
    elif change == 'unknown': first['unit_ids'].append('S99.U01')
    elif change == 'no_quote': first['unit_evidence'].pop()
    elif change == 'wrong_quote': first['unit_evidence'][0]['quote'] = '这并不是当前单元的原文'
    elif change == 'blank_quote': first['unit_evidence'][0]['quote'] = '    '
    elif change == 'blank_plan': first['objective_evidence'][0]['quote'] = '  '
    elif change == 'blank_reason': first['reason'] = ' ' * 12
    elif change == 'bad_plan': first['objective_evidence'][0]['quote'] = '不存在的更广范围'
    elif change == 'repair_unquoted': first['repair_unit_ids'] = ['S01.U03.answer']
    elif change == 'repair_missing': first['repair_unit_ids'] = []
    elif change == 'counterexample_warning':
        first.update(status='satisfied', repair_instruction=None, repair_unit_ids=[])
        first['unit_evidence'][0]['kind'] = 'counterexample'
    with pytest.raises(ValueError): validate_assessment(response, context())


def test_valid_receipt_replay_is_same_job_context_only_and_preserves_immutable_evidence(tmp_path):
    p = pipeline(tmp_path, [verdict(), verdict(), verdict()])
    receipt, issues = evaluate(p)
    assert receipt['status'] == 'reviewed' and receipt['teacher_review'] == 'NOT_RUN'
    raw = (tmp_path/receipt['evidence_key']).read_bytes()
    assert digest(raw) == receipt['evidence_sha256']
    assert json.loads(raw) == {k: v for k, v in receipt.items() if k not in ('evidence_key', 'evidence_sha256')}
    assert evaluate(p) == (receipt, issues) and len(p.provider.calls) == 1
    p.job['id'] = 'new-formal-recheck'
    assert evaluate(p)[0]['identity_hash'] != receipt['identity_hash']
    revised = copy.deepcopy(UNITS); revised[1]['tex'] += ' 新增现有说明。'
    evaluate(p, revised)
    assert len(p.provider.calls) == 3


@pytest.mark.parametrize('invalid', [False, True])
def test_completed_unresolved_or_invalid_cannot_retry_draw_a_pass(tmp_path, invalid):
    response = verdict()
    response['items'][0] = item(status='unresolved', targets=[], repairs=[])
    if invalid: response['items'].pop()
    p = pipeline(tmp_path, [response, verdict()])
    for _ in range(2):
        with pytest.raises(AgentError) as error: evaluate(p)
        assert error.value.code == 'FEEDBACK_REVIEW_BLOCKED'
    assert len(p.provider.calls) == 1
    path, saved = state(p)
    assert saved['status'] == ('INVALID' if invalid else 'UNRESOLVED')
    receipt = json.loads((path.parent/saved['receipt_file']).read_bytes())
    if invalid:
        assert len(receipt['items']) == 2 and all(i['status'] == 'unresolved' for i in receipt['items'])


@pytest.mark.parametrize('code', ['PROVIDER_ALL_UNAVAILABLE', 'PROVIDER_TIMEOUT', 'BUDGET_EXHAUSTED',
    'PROVIDER_EMPTY_RESPONSE', 'PROVIDER_STREAM_PROTOCOL'])
def test_no_completed_response_resumes_same_slot_after_transport_or_budget_recovery(tmp_path, code):
    p = pipeline(tmp_path, [AgentError(code, 'Synthetic provider interruption'), verdict()])
    with pytest.raises(AgentError) as error: evaluate(p)
    assert error.value.code == (code if code == 'BUDGET_EXHAUSTED' else 'FEEDBACK_REVIEW_BLOCKED')
    path, saved = state(p)
    assert saved['status'] == 'TRANSPORT_PENDING'
    pending = json.loads((path.parent/saved['receipt_file']).read_bytes())
    assert pending['status'] == 'transport_pending' and all(i['status'] == 'unresolved' for i in pending['items'])
    receipt, _ = evaluate(p)
    assert receipt['status'] == 'reviewed' and p.provider.calls[0] == p.provider.calls[1]
    assert json.loads((path.parent/'receipt-1-transport_pending.json').read_bytes()) == pending


def test_completed_response_recovery_consumes_saved_verdict_without_network(tmp_path):
    p = pipeline(tmp_path, [verdict()])
    first, _ = evaluate(p)
    path, saved = state(p); saved['status'] = 'RESPONSE_RECEIVED'; write_json(path, saved)
    assert evaluate(p)[0] == first and len(p.provider.calls) == 1


def test_orphan_response_and_tampered_hash_block_instead_of_redrawing(tmp_path):
    p = pipeline(tmp_path, [AgentError('PROVIDER_TIMEOUT', 'Synthetic timeout'), verdict()])
    with pytest.raises(AgentError): evaluate(p)
    path, _ = state(p)
    write_json(path.parent/'response-1.json', verdict())
    with pytest.raises(AgentError) as error: evaluate(p)
    assert error.value.code == 'FEEDBACK_EVIDENCE_BLOCKED' and len(p.provider.calls) == 1
    (path.parent/'input.json').write_text('{}', encoding='utf-8')
    with pytest.raises(AgentError) as error: evaluate(p)
    assert error.value.code == 'FEEDBACK_EVIDENCE_BLOCKED' and len(p.provider.calls) == 1


def test_mock_provider_explicitly_declines_natural_language_assessment():
    ctx = context(); ctx['mock'] = True
    response = MockProvider().generate('reviewer_feedback', ctx, FeedbackAssessment)
    receipt, issues = validate_assessment(response, ctx)
    assert not issues
    assert all(i['status'] == 'rejected_not_supported' and i['reason'].startswith('离线演示不评估自然语言反馈')
        for i in receipt['items'])


def test_feedback_schema_invalid_http_response_has_one_draw_even_if_other_roles_allow_repair(tmp_path):
    import httpx
    from math_agent.provider import CompatibleChatProvider
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"items":[]}'}}]})

    settings = Settings(workspace=tmp_path, api_key='synthetic-key-for-mock', live_api_enabled=True,
        llm_streaming=False, max_schema_repair_attempts=2)
    provider = CompatibleChatProvider(settings, transport=httpx.MockTransport(handler), failure_dir=tmp_path/'failures')
    with pytest.raises(AgentError) as error:
        provider.generate('reviewer_feedback', context(), FeedbackAssessment)
    assert error.value.code == 'INVALID_MODEL_JSON' and len(calls) == 1
    assert list((tmp_path/'failures').glob('*.txt'))


def test_real_first_probe_missing_own_item_evidence_remains_invalid():
    root = Path(__file__).resolve().parents[1]
    folder = root/'reports/iteration4/live-feedback-controls-20260920-1801'
    path = folder/'already_satisfied_and_outside_approved_scope/response.json'
    if not path.exists(): pytest.skip('Historical real response not in this checkout')
    response = json.loads(path.read_bytes())
    # This is a migration-only fixture, not a claim that the old API returned
    # the new required field. It still must fail its original missing evidence.
    for row in response['items']: row['repair_unit_ids'] = []
    cases = json.loads((root/'reports/iteration4/feedback-review-fixtures.json').read_bytes())['cases']
    with pytest.raises(ValueError, match='actual evidence'):
        validate_assessment(response, cases[1]['input'])
