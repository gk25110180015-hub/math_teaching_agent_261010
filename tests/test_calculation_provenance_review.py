"""Offline one-shot provenance adjudication of the frozen S03 95bb review."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_agent.uncertainty_review import UncertaintyReview, validate_uncertainty_assessment
from math_agent.util import AgentError, digest
from test_calculation_review_context import offline_environment
from test_local_recovery import direct_recovery


CAPTURE = Path(__file__).parent / 'fixtures' / 'calculation_provenance_review'


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


class ProvenanceProvider:
    def __init__(self, behavior='withdraw'):
        self.behavior = behavior
        self.calls = []

    def generate(self, role, context, schema):
        assert role == 'review_calculation_provenance'
        self.calls.append(copy.deepcopy(context))
        decisions = []
        for candidate in context['candidates']:
            body = next(source for source in context['sources'] if source['source_key'] == 'current:' + candidate['unit_id'])
            calculation = next(source for source in context['sources'] if source['source_key'] == candidate['source_key'])
            decisions.append({'issue_id': candidate['issue_id'], 'issue_hash': candidate['issue_hash'],
                'disposition': 'retain' if self.behavior == 'retain' else 'withdraw_provenance_only',
                'reason': '离线受控裁定：已逐字核对固定原始补丁、前后核算输入及当前正文，本裁定不构成教师验收。',
                'provenance_only': self.behavior != 'retain',
                'remaining_mathematical_concern': self.behavior == 'retain',
                'evidence': [{'source_key': source['source_key'], 'source_sha256': source['source_sha256'], 'quote': source['tex']}
                             for source in (body, calculation)]})
        response = {'decisions': decisions, 'limitations': ['Offline injected provenance judgment only.']}
        if self.behavior == 'missing_decision':
            response['decisions'].pop()
        elif self.behavior == 'wrong_hash':
            decisions[0]['issue_hash'] = '0' * 64
        elif self.behavior == 'wrong_quote':
            decisions[0]['evidence'][1]['quote'] = '这段未经提供的外部历史记录不能作为来源裁定的真实证据。'
        elif self.behavior == 'no_body':
            decisions[0]['evidence'] = decisions[0]['evidence'][1:]
        elif self.behavior == 'no_origin':
            calculation = next(source for source in context['sources'] if source['source_key'] == decisions[0]['evidence'][1]['source_key'])
            decisions[0]['evidence'][1]['quote'] = calculation['tex'].split('保留声明的内部生成来源')[0]
        elif self.behavior == 'remaining_math':
            decisions[0]['remaining_mathematical_concern'] = True
        return response


def make_case(tmp_path, behavior='withdraw'):
    pipeline, _, _ = direct_recovery(tmp_path)
    context = captured('input.json')
    pipeline.run['plan'] = copy.deepcopy(context['plan'])
    guard = UncertaintyReview(pipeline, context)
    ordinary = captured('ordinary-review.json')
    guard.ordinary_review(lambda _: copy.deepcopy(ordinary), captured('ordinary-context.json'))
    pipeline.provider = SimpleNamespace(generate=lambda *args: captured('response-1.json'))
    report, declared = guard.evaluate()
    assert report['assessment'] == captured('assessment.json')
    provider = ProvenanceProvider(behavior)
    pipeline.provider = provider
    return SimpleNamespace(p=pipeline, guard=guard, section=context['section'], math=context['tool_checks'],
        packet=context['calculation_recovery_evidence'], issues=copy.deepcopy(ordinary['issues']) + declared,
        assessment=report['assessment'], provider=provider)


def apply(case, *, issues=None, packet=None):
    from math_agent.calculation_provenance_review import apply_calculation_provenance_review
    return apply_calculation_provenance_review(case.p, case.guard, case.section, case.math,
        case.packet if packet is None else packet, case.issues if issues is None else issues, case.assessment)


def test_frozen_95bb_provenance_withdrawal_keeps_raw_evidence_and_null_owner(tmp_path):
    case = make_case(tmp_path)
    original = copy.deepcopy((case.section, case.math, case.packet, case.issues, case.assessment))
    original_files = {path: path.read_bytes() for path in case.guard.folder.iterdir() if path.is_file()}
    effective, assessment, audit = apply(case)
    assert not [issue for issue in effective if issue.get('severity') in ('blocking', 'review')]
    assert validate_uncertainty_assessment(assessment, case.guard.context) == assessment
    resolved = next(item for item in assessment['items'] if item['uncertainty_id'].startswith('D002-'))
    assert resolved['unit_id'] is None and resolved['disposition'] == 'resolved_by_current_body'
    assert not resolved['remaining_dependency'] and resolved['repair_instruction'] is None
    assert case.assessment['items'][1]['disposition'] == 'open_dependency'
    assert len(case.provider.calls) == 1 and audit
    assert original == (case.section, case.math, case.packet, case.issues, case.assessment)
    assert all(path.read_bytes() == raw for path, raw in original_files.items())
    assert all(candidate['issue_hash'] for candidate in case.provider.calls[0]['candidates'])
    result_path = case.p.settings.workspace / audit['evidence_key']
    assert digest(result_path.read_bytes()) == audit['evidence_sha256']


def test_tool_and_other_unit_issues_survive_cached_adjudication_without_another_call(tmp_path):
    case = make_case(tmp_path)
    tool = {'rule_id': 'SYMBOLIC_COUNTERCHECK_FAILED', 'severity': 'blocking',
            'location': {'unit_id': 'S03.U07', 'calculation_id': 'UNRELATED'}, 'message': '仍须处理的独立核算错误。'}
    other = {'unit_id': 'S03.U01', 'severity': 'review', 'message': '另一个单元的证明前提仍未核实。', 'evidence': 'Independent concern.'}
    issues = [*case.issues, tool, other]
    first = apply(case, issues=issues)
    assert tool in first[0] and other in first[0]
    second = apply(case, issues=issues)
    assert second == first and len(case.provider.calls) == 1
    new_issue = {'unit_id': 'S03.U02', 'severity': 'review', 'message': '裁定以后才加入的独立问题。', 'evidence': 'Later retained issue.'}
    third = apply(case, issues=[*issues, new_issue])
    assert new_issue in third[0] and tool in third[0] and other in third[0]
    assert len(case.provider.calls) == 1


def test_explicit_retain_is_final_and_cannot_be_redrawn_on_retry(tmp_path):
    case = make_case(tmp_path, 'retain')
    first = apply(case)
    assert first[0] == case.issues and first[1] == case.assessment and first[2]
    case.provider.behavior = 'withdraw'
    assert apply(case) == first and len(case.provider.calls) == 1


@pytest.mark.parametrize('damage', ['missing_decision', 'wrong_hash', 'wrong_quote', 'no_body', 'no_origin', 'remaining_math'])
def test_invalid_completed_decision_remains_blocked_without_redraw(tmp_path, damage):
    case = make_case(tmp_path, damage)
    original = copy.deepcopy((case.issues, case.assessment))
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            apply(case)
        assert error.value.code == 'CALCULATION_PROVENANCE_REVIEW_BLOCKED'
        case.provider.behavior = 'withdraw'
    assert len(case.provider.calls) == 1
    assert original == (case.issues, case.assessment)


def test_tampered_cached_response_blocks_without_calling_another_reviewer(tmp_path):
    case = make_case(tmp_path)
    apply(case)
    folder = case.p.root / 'calculation-provenance-reviews' / case.guard.key[:24]
    (folder / 'response.json').write_bytes(b'{}')
    with pytest.raises(AgentError) as error:
        apply(case)
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'
    assert len(case.provider.calls) == 1


def test_without_verified_note_origin_no_one_shot_call_is_authorized(tmp_path):
    case = make_case(tmp_path)
    packet = copy.deepcopy(case.packet)
    for correction in packet['corrections']:
        correction.pop('declaration_origins', None)
    effective, assessment, audit = apply(case, packet=packet)
    assert effective == case.issues and assessment == case.assessment and audit is None
    assert not case.provider.calls


def test_started_slot_after_interruption_cannot_be_resampled(tmp_path, monkeypatch):
    case = make_case(tmp_path)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt('Injected interruption after slot was counted and frozen')
    generate = case.provider.generate
    monkeypatch.setattr(case.provider, 'generate', interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply(case)
    monkeypatch.setattr(case.provider, 'generate', generate)
    with pytest.raises(AgentError) as error:
        apply(case)
    assert error.value.code == 'CALCULATION_PROVENANCE_REVIEW_BLOCKED'
    assert not case.provider.calls


@pytest.mark.parametrize('code', ['PROVIDER_UNAVAILABLE', 'BUDGET_EXHAUSTED'])
def test_known_failure_resumes_identical_payload_without_schema_resampling(tmp_path, code):
    case = make_case(tmp_path)

    class RetryProvider(ProvenanceProvider):
        def __init__(self):
            super().__init__()
            self.settings = case.p.settings.model_copy(update={'max_schema_repair_attempts': 2})
            self.attempts = []

        def generate(self, role, context, schema):
            assert self.settings.max_schema_repair_attempts == 0
            self.attempts.append(copy.deepcopy(context))
            if len(self.attempts) == 1:
                raise AgentError(code, 'Injected known failure before any complete response')
            return super().generate(role, context, schema)

    provider = RetryProvider()
    case.p.provider = provider
    with pytest.raises(AgentError) as error:
        apply(case)
    assert error.value.code == ('BUDGET_EXHAUSTED' if code == 'BUDGET_EXHAUSTED'
                                else 'CALCULATION_PROVENANCE_REVIEW_BLOCKED')
    folder = case.p.root / 'calculation-provenance-reviews' / case.guard.key[:24]
    pending_state = json.loads((folder / 'state.json').read_bytes())
    assert pending_state['status'] == 'TRANSPORT_PENDING' and pending_state['calls'] == 1
    assert not (folder / 'response.json').exists()
    frozen = {name: (folder / name).read_bytes() for name in ('input.json', 'failure-1.json')}
    failure = json.loads(frozen['failure-1.json'])
    assert failure['code'] == code and failure['retryable_same_slot'] is True

    later_issue = {'unit_id': 'S03.U01', 'severity': 'review',
                   'message': '传输重试期间新增且未经来源裁定的独立问题。', 'evidence': 'Retain new issue.'}
    result = apply(case, issues=[*case.issues, later_issue])
    assert later_issue in result[0] and result[2]['semantic_verdicts'] == 1
    assert len(provider.attempts) == 2 and provider.attempts[0] == provider.attempts[1]
    assert len(provider.calls) == 1
    assert provider.settings.max_schema_repair_attempts == 2
    final_state = json.loads((folder / 'state.json').read_bytes())
    assert final_state['status'] == 'COMPLETE' and final_state['calls'] == 2
    assert final_state['identity_hash'] == pending_state['identity_hash']
    assert all((folder / name).read_bytes() == raw for name, raw in frozen.items())
    assert apply(case, issues=[*case.issues, later_issue]) == result
    assert len(provider.attempts) == 2 and len(provider.calls) == 1


def test_transport_pending_with_unregistered_response_cannot_request_again(tmp_path, monkeypatch):
    case = make_case(tmp_path)

    def unavailable(*args, **kwargs):
        raise AgentError('PROVIDER_UNAVAILABLE', 'Injected no-response transport failure')

    generate = case.provider.generate
    monkeypatch.setattr(case.provider, 'generate', unavailable)
    with pytest.raises(AgentError) as error:
        apply(case)
    assert error.value.code == 'CALCULATION_PROVENANCE_REVIEW_BLOCKED'
    folder = case.p.root / 'calculation-provenance-reviews' / case.guard.key[:24]
    state_before = (folder / 'state.json').read_bytes()
    (folder / 'response.json').write_bytes(b'{}')
    monkeypatch.setattr(case.provider, 'generate', generate)
    with pytest.raises(AgentError) as error:
        apply(case)
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'
    assert (folder / 'state.json').read_bytes() == state_before
    assert not case.provider.calls


def test_same_unit_mathematical_and_lookalike_calculation_issues_are_not_candidates(tmp_path):
    case = make_case(tmp_path)
    unrelated = {'unit_id': 'S03.U07', 'severity': 'review',
                 'message': '此单元的独立命题尚缺少秩条件，需要补充完整证明。',
                 'evidence': 'The separate rank assumption remains unsupported.'}
    lookalike = {'unit_id': 'S03.U07', 'severity': 'blocking',
                'message': 'S03.C010 的独立核算结果仍有矛盾。',
                'evidence': 'The concern refers to S03.C010, a different calculation.'}
    issues = [*case.issues, unrelated, lookalike]
    effective, _, audit = apply(case, issues=issues)
    assert [issue for issue in effective if issue.get('severity') in ('blocking', 'review')] == [unrelated, lookalike]
    assert all(issue in effective for issue in case.issues if issue.get('severity') == 'warning')
    assert audit
    candidates = [candidate['issue'] for candidate in case.provider.calls[0]['candidates']]
    assert unrelated not in candidates and lookalike not in candidates
    assert len(case.provider.calls) == 1
