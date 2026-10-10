"""Preserve reproducible old/new calculation inputs in actual review contexts.

Frozen S03 history demonstrates that 29/28 was the old malformed checker input;
the corrected input produces 27/28. Provenance is evidence for the reviewers,
never an automatic instruction to clear their original mathematical concerns.
"""
import copy
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_agent.mathcheck import check_math
from math_agent.util import AgentError, digest, write_json
from test_independent_calculation_repair import CalculationProvider, corrected_calculation
from test_local_recovery import setup, state


CAPTURE = Path(__file__).parent / 'fixtures' / 'calculation_review_context'
OLD_GUARD = 'cf1e230123a5d63e68ee10bb'
SECOND_OLD_GUARD = '6cf90e694a11780fdcf7e11b'


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


def copy_guard(recovery, guard_id):
    destination = recovery.p.root / 'uncertainty-reviews' / guard_id
    destination.mkdir(parents=True)
    for name in ('input.json', 'state.json'):
        shutil.copyfile(CAPTURE / guard_id / name, destination / name)
    return destination


def fixture_recovery(tmp_path, *, history=True, current=False):
    workspace = tmp_path / 'isolated'
    context = captured(OLD_GUARD + '/input.json')
    pipeline = SimpleNamespace(root=workspace / 'runs/frozen-run', settings=SimpleNamespace(workspace=workspace),
                               run={'id': 'frozen-run', 'plan': context['plan']})
    recovery = SimpleNamespace(p=pipeline, identity={'plan_hash': context['plan']['hash'], 'section_id': 'S03'},
                               spec={'id': 'S03'}, state={'pending_issues': [{'message': '原历史核算问题仍需复核。'}]})
    if history:
        copy_guard(recovery, OLD_GUARD)
    section = captured('current-candidate.json')
    math = check_math(section)
    if current:
        register_current_input(recovery, section, math)
    return recovery, section, math


def build(recovery, section, math):
    from math_agent.calculation_review_context import build_calculation_review_context
    return build_calculation_review_context(recovery, section, math)


def registered_source(recovery, context, *, state_override=None):
    """Create a coherent alternate archived source; never mutate production."""
    state = captured(OLD_GUARD + '/state.json')
    state['identity']['plan_hash'] = context['plan']['hash']
    state['identity']['plan_revision'] = context['plan']['revision']
    state['identity']['context_hash'] = digest(context)
    state['identity_hash'] = digest(state['identity'])
    folder = recovery.p.root / 'uncertainty-reviews' / state['identity_hash'][:24]
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / 'input.json', context)
    state['dependencies']['input.json'] = digest((folder / 'input.json').read_bytes())
    state.update(state_override or {})
    write_json(folder / 'state.json', state)
    return folder


def register_current_input(recovery, section, math):
    from math_agent.uncertainty_review import build_uncertainty_context
    previous = captured(OLD_GUARD + '/input.json')
    context = build_uncertainty_context(previous['plan'], section, previous['prior_sections'], math, math['issues'])
    return registered_source(recovery, context)


def test_real_history_explains_old_and_current_ast_with_immutable_registered_source(tmp_path):
    recovery, section, math = fixture_recovery(tmp_path, current=True)
    copy_guard(recovery, SECOND_OLD_GUARD)
    before = {path: path.read_bytes() for path in recovery.p.root.rglob('*.json')}
    pending = copy.deepcopy(recovery.state['pending_issues'])
    result = build(recovery, section, math)
    assert result is not None and result['status'] == 'HISTORICAL_FAILURE_REPRODUCED_CURRENT_CHECK_PASSED'
    assert result['section_id'] == 'S03' and result['teacher_review'] == 'NOT_RUN'
    assert len(result['corrections']) == 1
    correction = result['corrections'][0]
    assert correction['calculation_id'] == 'S03.C01' and correction['unit_id'] == 'S03.U07'
    assert correction['expression_field'] == 'lhs'
    assert correction['previous_request']['lhs'] != correction['current_request']['lhs']
    assert correction['previous_request']['rhs'] == correction['current_request']['rhs'] == {'op': 'Rational', 'p': 27, 'q': 28}
    assert correction['previous_evidence']['result'] == correction['reproduced_previous_evidence']['result'] == '29/28'
    assert correction['current_evidence']['result'] == '27/28'
    assert correction['reproduced_previous_evidence']['status'] == 'FAIL'
    assert correction['current_evidence']['status'] == 'PASS'
    source = correction['source']
    assert source['input_sha256'] == digest((recovery.p.settings.workspace / source['input_key']).read_bytes())
    assert source['identity_hash'].startswith((OLD_GUARD, SECOND_OLD_GUARD))
    assert recovery.state['pending_issues'] == pending
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_package_stays_stable_when_retry_state_changes_and_current_guard_is_added(tmp_path):
    recovery, section, math = fixture_recovery(tmp_path)
    initial = build(recovery, section, math)
    assert initial
    recovery.state.update(phase='PROPOSAL_REJECTED', proposal_calls=99,
                          pending_issues=[{'message': '保留疑点', 'prior_calculation_context': copy.deepcopy(initial)}])
    register_current_input(recovery, section, math)
    again = build(recovery, section, math)
    assert again == initial
    serialized = json.dumps(again)
    assert 'prior_calculation_context' not in serialized and 'proposal_calls' not in serialized
    assert 'state_sha256' not in serialized and 'created_at' not in serialized


def test_duplicate_old_failure_inputs_form_one_correction(tmp_path):
    recovery, section, math = fixture_recovery(tmp_path)
    context = captured(OLD_GUARD + '/input.json')
    context['deterministic_issues'].append({'severity': 'warning', 'message': 'Same failure, different archived review context.'})
    registered_source(recovery, context)
    result = build(recovery, section, math)
    assert len(result['corrections']) == 1
    assert result == build(recovery, section, math)


@pytest.mark.parametrize('mode', ['no_history', 'current_only', 'changed_rhs', 'changed_assumptions', 'changed_binding', 'not_current_pass'])
def test_unrelated_or_unverified_history_never_becomes_recovery_evidence(tmp_path, mode):
    recovery, section, math = fixture_recovery(tmp_path, history=mode not in ('no_history', 'current_only'), current=mode == 'current_only')
    if mode == 'changed_rhs':
        section['calculations'][0]['lhs'] = {'op': 'Integer', 'value': 20}
        section['calculations'][0]['rhs'] = {'op': 'Integer', 'value': 20}
        math = check_math(section)
    elif mode == 'changed_assumptions':
        section['calculations'][0]['assumptions'] = {'z': {'real': True}}
        math = check_math(section)
    elif mode == 'changed_binding':
        section['calculations'][0]['unit_id'] = 'S03.U08'
        math = check_math(section)
    elif mode == 'not_current_pass':
        current = next(item for item in math['evidence'] if item['calculation_id'] == 'S03.C01')
        current.update(status='UNKNOWN', evidence_type='not_checked')
    assert build(recovery, section, math) is None


@pytest.mark.parametrize('damage', ['input_bytes', 'input_registration', 'identity_hash', 'context_hash', 'folder_name', 'wrong_old_result'])
def test_corrupted_registered_source_blocks_instead_of_erasing_provenance(tmp_path, damage):
    recovery, section, math = fixture_recovery(tmp_path)
    folder = recovery.p.root / 'uncertainty-reviews' / OLD_GUARD
    state = json.loads((folder / 'state.json').read_bytes())
    if damage == 'input_bytes':
        (folder / 'input.json').write_bytes(b'{}')
    elif damage == 'input_registration':
        state['dependencies'].pop('input.json')
        write_json(folder / 'state.json', state)
    elif damage == 'identity_hash':
        state['identity_hash'] = '0' * 64
        write_json(folder / 'state.json', state)
    elif damage == 'context_hash':
        context = json.loads((folder / 'input.json').read_bytes())
        context['mock'] = not context['mock']
        write_json(folder / 'input.json', context)
        state['dependencies']['input.json'] = digest((folder / 'input.json').read_bytes())
        write_json(folder / 'state.json', state)
    elif damage == 'folder_name':
        folder.rename(folder.with_name('0' * 24))
    elif damage == 'wrong_old_result':
        context = captured(OLD_GUARD + '/input.json')
        next(item for item in context['tool_checks']['evidence'] if item['calculation_id'] == 'S03.C01')['result'] = '99/28'
        registered_source(recovery, context)
    with pytest.raises(AgentError) as error:
        build(recovery, section, math)
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'


def test_pipeline_supplies_same_history_and_current_requests_to_both_reviewers_without_clearing_doubt(tmp_path, monkeypatch):
    provider = CalculationProvider(after='open_dependency')
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    assert len(provider.patches) == 1 and not compiled
    ordinary, uncertainty = provider.ordinary[-1], provider.dispositions[-1]
    assert ordinary['calculation_requests'] == uncertainty['section']['calculations']
    assert ordinary['calculation_recovery_evidence'] == uncertainty['calculation_recovery_evidence']
    correction = ordinary['calculation_recovery_evidence']['corrections'][0]
    assert correction['previous_evidence']['result'] == '29/28'
    assert correction['current_evidence']['result'] == '27/28'
    assert any(issue.get('rule_id') == 'SYMBOLIC_COUNTERCHECK_FAILED' for issue in ordinary['local_recovery']['unresolved_issues'])
    assert any(issue.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY' for issue in state(pipeline)['pending_issues'])
    saved_guards = [json.loads(path.read_bytes()) for path in (pipeline.root / 'uncertainty-reviews').glob('*/state.json')]
    assert {saved['status'] for saved in saved_guards} == {'INVALID', 'REVIEWED'}
    before = {path: path.read_bytes() for path in (pipeline.root / 'uncertainty-reviews').glob('*/*.json')}
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_pipeline_can_resolve_old_provenance_only_after_explicit_new_review(tmp_path, monkeypatch):
    provider = CalculationProvider()
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    completed, reports = pipeline.lecture(plan)
    assert completed and len(compiled) == 1
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    assert provider.dispositions[0]['declared_doubts'] == provider.dispositions[1]['declared_doubts']
    assert 'calculation_recovery_evidence' not in provider.dispositions[0]
    assert provider.dispositions[1]['calculation_recovery_evidence']['corrections']
    assert reports[0]['uncertainty_review']['assessment']['items'][0]['disposition'] == 'resolved_by_current_body'


HISTORICAL_ISSUE = {'unit_id': 'S01.U1', 'severity': 'review',
    'message': '当前值27/28与历史29/28记录冲突，缺少旧表达式，不能确认。',
    'evidence': 'Current tool passed but the retained historical failure lacks its old expression.'}
UNRELATED_ISSUE = {'unit_id': 'S01.U2', 'severity': 'review',
    'message': '另一单元的证明前提仍缺少依据，不能由核算配置修复消解。', 'evidence': 'Unrelated independent proof concern.'}


class HistoryAwareProvider(CalculationProvider):
    def __init__(self, mode='resolve'):
        super().__init__()
        self.mode = mode

    def generate(self, role, context, schema):
        has_history = bool(context.get('calculation_recovery_evidence'))
        if role == 'reviewer_uncertainty':
            self.after = 'resolved_by_current_body' if has_history else 'open_dependency'
        value = super().generate(role, context, schema)
        if role == 'reviewer_math' and context.get('scope', {}).get('kind') != 'chapter_coverage':
            fixed = context['calculation_requests'][0] == corrected_calculation()
            if fixed and (not has_history or self.mode == 'still_reported'):
                value['issues'].append(copy.deepcopy(HISTORICAL_ISSUE))
            if fixed and not has_history and self.mode == 'other_unit':
                value['issues'].append(copy.deepcopy(UNRELATED_ISSUE))
        return value


def initially_missing_history(tmp_path, monkeypatch, *, mode='resolve'):
    import math_agent.calculation_review_context as module
    provider = HistoryAwareProvider(mode)
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    builder = module.build_calculation_review_context
    monkeypatch.setattr(module, 'build_calculation_review_context', lambda *args: None)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    assert HISTORICAL_ISSUE in state(pipeline)['pending_issues']
    assert len(provider.ordinary) == len(provider.dispositions) == 2 and len(provider.patches) == 1
    monkeypatch.setattr(module, 'build_calculation_review_context', builder)
    return service, pipeline, plan, provider, compiled


def test_new_provenance_packet_reopens_review_without_rewriting_body_or_erasing_frozen_judgment(tmp_path, monkeypatch):
    service, pipeline, plan, provider, compiled = initially_missing_history(tmp_path, monkeypatch)
    old_state = state(pipeline)
    old_candidate = json.loads((pipeline.settings.workspace / old_state['candidate_key']).read_bytes())
    old_judgments = {path: path.read_bytes() for path in (pipeline.root / 'uncertainty-reviews').glob('*/*.json')}
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert completed[0][1] == old_candidate and len(compiled) == 1
    assert len(provider.patches) == 1 and provider.writes == 1
    assert len(provider.ordinary) == len(provider.dispositions) == 3
    assert not reports[0]['issues'] and not state(pipeline)['pending_issues']
    assert HISTORICAL_ISSUE in provider.ordinary[-1]['local_recovery']['unresolved_issues']
    assert provider.ordinary[-1]['calculation_recovery_evidence'] == provider.dispositions[-1]['calculation_recovery_evidence']
    assert state(pipeline)['unit_applied_counts'] == old_state['unit_applied_counts']
    assert all(path.read_bytes() == raw for path, raw in old_judgments.items())
    assert service.store.get_run(pipeline.run['id'])['approval'] == approval
    assert not service.store.get_run(pipeline.run['id'])['reviews']


@pytest.mark.parametrize('mode,expected_issue', [('still_reported', HISTORICAL_ISSUE), ('other_unit', UNRELATED_ISSUE)])
def test_new_provenance_does_not_clear_repeated_or_unrelated_ordinary_issue(tmp_path, monkeypatch, mode, expected_issue):
    _, pipeline, plan, provider, compiled = initially_missing_history(tmp_path, monkeypatch, mode=mode)
    budget = pipeline.effective_budget()
    monkeypatch.setattr(pipeline, 'effective_budget', lambda: {**budget, 'local_repairs_per_unit': 0})
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == 'BUDGET_EXHAUSTED'
        assert expected_issue in state(pipeline)['pending_issues']
    assert not compiled and len(provider.patches) == 1
    assert len(provider.ordinary) == len(provider.dispositions) == 3


def test_prior_report_cannot_rebind_to_another_valid_guard_for_a_different_candidate(tmp_path, monkeypatch):
    from math_agent.uncertainty_review import UncertaintyReview, build_uncertainty_context
    from test_uncertainty_review import assessment
    _, pipeline, plan, provider, compiled = initially_missing_history(tmp_path, monkeypatch)
    saved = copy.deepcopy(state(pipeline))
    candidate = json.loads((pipeline.settings.workspace / saved['candidate_key']).read_bytes())
    other_candidate = copy.deepcopy(candidate)
    other_candidate['units'][1]['tex'] += ' 这属于同一批准计划下的另一份不同候选正文。'
    other_context = build_uncertainty_context(plan, other_candidate, [], check_math(other_candidate), [])
    other_guard = UncertaintyReview(pipeline, other_context)
    other_guard.ordinary_review(lambda _: {'issues': [], 'checked_unit_ids': [unit['id'] for unit in other_candidate['units']],
                                           'limitations': ['Separate valid offline guard.']}, {})
    pipeline.provider = SimpleNamespace(generate=lambda role, context, schema: assessment(context))
    try:
        other_guard.evaluate()
    finally:
        pipeline.provider = provider
    assert other_guard.state['status'] == 'REVIEWED'
    assert other_context['plan']['hash'] == plan['hash']
    assert other_context['section'] != candidate
    other_bytes = {path: path.read_bytes() for path in other_guard.folder.iterdir() if path.is_file()}
    # Keep the original review/candidate/pending hashes coherent, but point its
    # declared source at a real, SHA-valid guard for another candidate.
    prior_path = pipeline.settings.workspace / saved['last_review_key']
    prior_review = json.loads(prior_path.read_bytes())
    prior_review['report']['uncertainty_review']['source_identity_hash'] = other_guard.key
    write_json(prior_path, prior_review)
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'
    assert not compiled and len(provider.patches) == 1
    assert state(pipeline)['pending_issues'] == saved['pending_issues']
    assert len(provider.ordinary) == len(provider.dispositions) == 3
    assert all(path.read_bytes() == raw for path, raw in other_bytes.items())
