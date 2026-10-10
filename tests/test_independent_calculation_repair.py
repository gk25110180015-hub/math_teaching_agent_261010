"""Offline regression for a real least-squares checker AST sign error.

An independent failed calculation can be corrected without rewriting already
correct prose. The strict local patch, real bounded checker, full new review,
unchanged doubts and original repair budgets all remain required.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from math_agent.local_patch import apply_local_patch
from math_agent.mathcheck import check_math
from math_agent.util import AgentError, digest, within
from test_local_recovery import setup, state


CAPTURE = Path(__file__).parent / 'fixtures' / 'independent_calculation_least_squares'
NOTE = 'S01.U2 原数学疑点仍需对照完整正文进行独立核查。'


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


def real_pair():
    before = captured('candidate.json')
    after, patch_evidence = apply_local_patch(before, ['S03.U07'], captured('patch.json'))
    report = captured('review.json')
    issues = [issue for issue in report['issues'] if issue.get('rule_id') == 'SYMBOLIC_COUNTERCHECK_FAILED']
    return before, after, issues, report['math'], patch_evidence


def verify(before, after, issues, tool):
    from math_agent.independent_calculation_repair import verify_independent_calculation_repair
    return verify_independent_calculation_repair(before, after, issues, tool)


def test_real_sign_correction_is_verified_without_changing_prose_expected_value_or_other_calculation():
    before, after, issues, tool, patch = real_pair()
    inputs = copy.deepcopy((before, after, issues, tool))
    evidence = verify(before, after, issues, tool)
    assert evidence is not None
    assert before['units'] == after['units']
    assert before['calculations'][1] == after['calculations'][1]
    assert before['calculations'][0]['rhs'] == after['calculations'][0]['rhs'] == {'op': 'Rational', 'p': 27, 'q': 28}
    assert patch['changed_unit_ids'] == [] and patch['calculation_updates'] == ['S03.C01']
    assert inputs == (before, after, issues, tool)
    assert evidence['changed_calculation_ids'] == ['S03.C01']
    assert evidence['target_unit_ids'] == ['S03.U07']
    assert evidence['requires_full_recheck'] is True and evidence['body_changed'] is False
    assert evidence['teacher_review'] == 'NOT_RUN'
    assert evidence['before_hash'] == digest(before) and evidence['after_hash'] == digest(after)
    checked = check_math(after)
    original = next(item for item in tool['evidence'] if item['calculation_id'] == 'S03.C01')
    corrected = next(item for item in checked['evidence'] if item['calculation_id'] == 'S03.C01')
    assert original['status'] == 'FAIL' and original['result'] == '29/28'
    assert corrected['status'] == 'PASS' and corrected['result'] == '27/28'
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in checked['issues'])


@pytest.mark.parametrize('damage', [
    'noop', 'addition', 'deletion', 'reordering', 'duplicate_id', 'changed_binding',
    'changed_kind', 'changed_rhs', 'changed_assumptions', 'nonfailed_calculation',
    'changed_metadata', 'notes', 'new_uncertainty', 'changed_body', 'changed_unit_metadata',
    'no_independent_issue', 'wrong_issue_binding', 'no_failed_evidence', 'still_fails',
])
def test_calculation_repair_gate_rejects_unjustified_or_broader_changes(damage):
    before, after, issues, tool, _ = real_pair()
    if damage == 'noop':
        after = copy.deepcopy(before)
    elif damage == 'addition':
        after['calculations'].append({**copy.deepcopy(after['calculations'][0]), 'id': 'S03.C03'})
    elif damage == 'deletion':
        after['calculations'].pop()
    elif damage == 'reordering':
        after['calculations'].reverse()
    elif damage == 'duplicate_id':
        after['calculations'][1]['id'] = after['calculations'][0]['id']
    elif damage == 'changed_binding':
        after['calculations'][0]['unit_id'] = 'S03.U08'
    elif damage == 'changed_kind':
        after['calculations'][0]['kind'] = 'numeric_spotcheck'
    elif damage == 'changed_rhs':
        after['calculations'][0]['rhs'] = {'op': 'Rational', 'p': 29, 'q': 28}
    elif damage == 'changed_assumptions':
        after['calculations'][0]['assumptions'] = {'x': {'positive': True}}
    elif damage == 'nonfailed_calculation':
        after['calculations'][1]['lhs'] = {'op': 'Add', 'args': [after['calculations'][1]['lhs'], {'op': 'Integer', 'value': 0}]}
    elif damage == 'changed_metadata':
        after['calculations'][0]['status'] = 'PASS'
    elif damage == 'notes':
        after['calculation_limitations'].append('仅追加一项说明，不能使原疑点重新抽取通过。')
    elif damage == 'new_uncertainty':
        after['uncertainties'].append('另一个新声明不能作为重抽审阅的理由。')
    elif damage == 'changed_body':
        after['units'][0]['tex'] += ' 正文已经发生变化。'
    elif damage == 'changed_unit_metadata':
        after['units'][0]['kind'] = 'explanation'
    elif damage == 'no_independent_issue':
        issues = []
    elif damage == 'wrong_issue_binding':
        issues[0]['location']['unit_id'] = 'S03.U08'
    elif damage == 'no_failed_evidence':
        tool['evidence'][0]['status'] = 'PASS'
        tool['evidence'][0]['evidence_type'] = 'symbolic_check_passed'
    elif damage == 'still_fails':
        after['calculations'][0]['lhs'] = {'op': 'Integer', 'value': 0}
    assert verify(before, after, issues, tool) is None


def sample_section():
    before = captured('candidate.json')
    calculations = copy.deepcopy(before['calculations'])
    for index, calculation in enumerate(calculations, 1):
        calculation.update(id=f'S01.C0{index}', unit_id='S01.U1')
    return {'section_id': 'S01', 'units': [
        {'id': 'S01.U1', 'kind': 'definition', 'tex': r'决定系数由已给平方和计算为 $1-(1/6)/(14/3)=27/28$。', 'relates_to': None},
        {'id': 'S01.U2', 'kind': 'explanation', 'tex': '原数学疑点必须在完整审阅后才能消解，核算不是最终数学验收。', 'relates_to': None},
    ], 'calculations': calculations, 'uncertainties': [NOTE], 'calculation_limitations': []}


def corrected_calculation():
    calculation = copy.deepcopy(captured('patch.json')['calculation_updates'][0])
    calculation.update(id='S01.C01', unit_id='S01.U1')
    return calculation


class CalculationProvider:
    def __init__(self, after='resolved_by_current_body', patch='correct'):
        self.after, self.patch = after, patch
        self.writes = 0
        self.ordinary, self.dispositions, self.patches = [], [], []

    def generate(self, role, context, schema):
        if role == 'writer_lecture_section':
            self.writes += 1
            return sample_section()
        if role == 'reviewer_math':
            if context.get('scope', {}).get('kind') != 'chapter_coverage':
                self.ordinary.append(copy.deepcopy(context))
            return {'issues': [], 'checked_unit_ids': [unit['id'] for unit in context['units']],
                    'limitations': ['Injected offline review; not teacher approval.']}
        if role == 'reviewer_uncertainty':
            self.dispositions.append(copy.deepcopy(context))
            fixed = context['section']['calculations'][0] == corrected_calculation()
            if not fixed or self.after == 'invalid':
                return {'items': [], 'limitations': ['Injected completed invalid disposition.']}
            source = next(source for source in context['sources'] if source['source_key'] == 'current:S01.U2')
            note = context['declared_doubts'][0]
            return {'items': [{'uncertainty_id': note['uncertainty_id'], 'unit_id': note['unit_id'],
                'disposition': self.after, 'reason': '这是离线受控裁定，仍须依据完整正文核对原数学疑点且不代表教师批准。',
                'evidence': [{'source_key': source['source_key'], 'source_sha256': source['source_sha256'], 'quote': source['tex']}],
                'remaining_dependency': self.after == 'open_dependency', 'repair_instruction': None}],
                'limitations': ['Injected offline judgment; no teacher approval.']}
        assert role == 'repair_local_patch'
        self.patches.append(copy.deepcopy(context))
        before = context['section']
        assert context['allowed_unit_ids'] == ['S01.U1']
        result = {'section_id': 'S01', 'replacements': [{'unit_id': 'S01.U1', 'tex': before['units'][0]['tex']}],
            'calculation_updates': [corrected_calculation()], 'calculation_additions': [],
            'uncertainties_append': [], 'calculation_limitations_append': []}
        if self.patch == 'noop':
            result['calculation_updates'] = []
        elif self.patch == 'notes':
            result['calculation_limitations_append'] = ['新说明不能消解原数学疑点。']
        elif self.patch == 'addition':
            result['calculation_additions'] = [{**corrected_calculation(), 'id': 'S01.C03'}]
        elif self.patch == 'nonfailed':
            calculation = copy.deepcopy(before['calculations'][1])
            calculation['lhs'] = {'op': 'Add', 'args': [calculation['lhs'], {'op': 'Integer', 'value': 0}]}
            result['calculation_updates'] = [calculation]
        return result


def test_pipeline_accepts_verified_calculation_only_patch_and_preserves_evidence_and_budget(tmp_path, monkeypatch):
    provider = CalculationProvider()
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert completed[0][1]['units'] == sample_section()['units']
    assert completed[0][1]['uncertainties'] == [NOTE]
    assert completed[0][1]['calculations'][0] == corrected_calculation()
    assert completed[0][1]['calculations'][1] == sample_section()['calculations'][1]
    assert provider.writes == len(provider.patches) == len(compiled) == 1
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    assert provider.dispositions[0]['section']['units'] == provider.dispositions[1]['section']['units']
    assert provider.dispositions[0]['tool_checks'] != provider.dispositions[1]['tool_checks']
    assert provider.dispositions[0]['declared_doubts'] == provider.dispositions[1]['declared_doubts']
    saved = state(pipeline)
    assert saved['unit_applied_counts'] == {'S01.U1': 1}
    assert saved['proposal_calls'] == saved['applied_rounds'] == 1 and saved['rejected_proposals'] == 0
    assert not saved['pending_issues'] and saved['phase'] == 'CHECKED'
    assert not reports[0]['issues']
    archived = [json.loads(path.read_bytes()) for path in (pipeline.root / 'local-repair/S01').glob('review-*.json')]
    original = next(record for record in archived if record['report']['uncertainty_review'].get('status') == 'INVALID')
    assert any(issue['rule_id'] == 'SYMBOLIC_COUNTERCHECK_FAILED' for issue in original['retained_issues'])
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in original['retained_issues'])
    assert original['report']['math']['evidence'][0]['result'] == '29/28'
    receipts = list(pipeline.build_root.glob('sS01*/repair-*-calculation-recovery.json'))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_bytes())['requires_full_recheck'] is True
    receipt_key = receipts[0].relative_to(pipeline.settings.workspace).as_posix()
    receipt_dependency = next(item for item in saved['evidence_dependencies'] if item['key'] == receipt_key)
    assert receipt_dependency['hash'] == digest(receipts[0].read_bytes())
    assert service.store.get_run(pipeline.run['id'])['approval'] == approval
    assert not service.store.get_run(pipeline.run['id'])['reviews']


@pytest.mark.parametrize('after,code', [('invalid', 'UNCERTAINTY_REVIEW_BLOCKED'), ('open_dependency', 'UNCERTAINTY_DEPENDENCY_BLOCKED')])
def test_corrected_calculation_does_not_clear_invalid_or_unresolved_mathematical_judgment(tmp_path, monkeypatch, after, code):
    provider = CalculationProvider(after=after)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == code
    assert len(provider.patches) == 1 and not compiled
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    saved = state(pipeline)
    assert saved['unit_applied_counts'] == {'S01.U1': 1} and saved['proposal_calls'] == 1
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in saved['pending_issues'])
    assert not any(issue['rule_id'] == 'SYMBOLIC_COUNTERCHECK_FAILED' for issue in saved['pending_issues'])
    assert json.loads(within(pipeline.settings.workspace, saved['candidate_key']).read_bytes())['units'] == sample_section()['units']
    with pipeline.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM steps WHERE run_id=?', (pipeline.run['id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('patch', ['noop', 'notes', 'addition', 'nonfailed'])
def test_rejected_metadata_changes_keep_original_pending_and_do_not_redraw_or_reset_budget(tmp_path, monkeypatch, patch):
    provider = CalculationProvider(patch=patch)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for code in ('REPAIR_SCOPE_VIOLATION', 'REPAIR_SCOPE_VIOLATION', 'BUDGET_EXHAUSTED'):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == code
    assert provider.writes == len(provider.ordinary) == len(provider.dispositions) == 1
    assert len(provider.patches) == 2 and not compiled
    saved = state(pipeline)
    assert saved['proposal_calls'] == saved['rejected_proposals'] == 2
    assert saved['unit_applied_counts'] == {}
    assert json.loads(within(pipeline.settings.workspace, saved['candidate_key']).read_bytes()) == sample_section()
    assert any(issue['rule_id'] == 'SYMBOLIC_COUNTERCHECK_FAILED' for issue in saved['pending_issues'])
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in saved['pending_issues'])


@pytest.mark.parametrize('damage', ['tamper', 'delete'])
def test_accepted_calculation_repair_requires_its_unchanged_proof_on_resume(tmp_path, monkeypatch, damage):
    provider = CalculationProvider(after='open_dependency')
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'UNCERTAINTY_DEPENDENCY_BLOCKED'
    saved = copy.deepcopy(state(pipeline))
    dependency = next(item for item in saved['evidence_dependencies'] if item['key'].endswith('-calculation-recovery.json'))
    proof = within(pipeline.settings.workspace, dependency['key'])
    assert digest(proof.read_bytes()) == dependency['hash']
    calls = (provider.writes, len(provider.patches), len(provider.ordinary), len(provider.dispositions))
    if damage == 'tamper':
        proof.write_bytes(b'{}')
    else:
        proof.unlink()
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'LOCAL_REPAIR_CACHE_INVALID'
    assert calls == (provider.writes, len(provider.patches), len(provider.ordinary), len(provider.dispositions))
    assert state(pipeline) == saved and not compiled
    assert saved['unit_applied_counts'] == {'S01.U1': 1}
    assert any(issue['rule_id'] == 'DECLARED_MATH_UNCERTAINTY' for issue in saved['pending_issues'])
