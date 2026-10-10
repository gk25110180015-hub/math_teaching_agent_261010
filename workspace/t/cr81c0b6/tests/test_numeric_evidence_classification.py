"""Real SymPy evidence; mocked provider/compiler, isolated SQLite, no live API."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.mathcheck import check_math
from math_agent.util import AgentError, digest
from test_local_recovery import direct_recovery, setup, state


FIXTURE = Path(__file__).parent / 'fixtures/numeric_evidence_ch02_s04.json'


def captured():
    return json.loads(FIXTURE.read_bytes())


def numeric_issue(result):
    return next(i for i in result['issues'] if i['rule_id'] == 'NUMERIC_IS_NOT_PROOF')


def test_actual_ch02_evidence_remains_numeric_and_review_required_but_not_repair_target(tmp_path, monkeypatch):
    import math_agent.mathcheck as module
    original_popen = module.subprocess.Popen
    child_diagnostics = []
    def traced_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        command = args[0] if args else kwargs.get('args', [])
        if isinstance(command, (list, tuple)) and 'math_agent.mathcheck' in command:
            original_communicate = process.communicate
            def communicate(*call_args, **call_kwargs):
                entry = {'command': list(command), 'timeout': call_kwargs.get('timeout')}
                payload = call_args[0] if call_args else call_kwargs.get('input')
                entry['input'] = payload.decode('utf-8', 'replace') if isinstance(payload, bytes) else payload
                try:
                    stdout, stderr = original_communicate(*call_args, **call_kwargs)
                    entry.update(returncode=process.returncode,
                        stdout=stdout.decode('utf-8', 'replace'), stderr=stderr.decode('utf-8', 'replace'))
                    return stdout, stderr
                except BaseException as exc:
                    entry.update(error_type=type(exc).__name__, returncode=process.returncode)
                    raise
                finally:
                    child_diagnostics.append(entry)
            process.communicate = communicate
        return process
    monkeypatch.setattr(module.subprocess, 'Popen', traced_popen)
    fixture = captured()
    section = fixture['section']
    original_hash = digest(section)
    result = check_math(section)
    diagnostic = {'result': result, 'child_diagnostics': child_diagnostics}
    (tmp_path/'math_child_diagnostic.json').write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding='utf-8')
    assert fixture['previous_math_report']['issues'][0]['severity'] == 'review'
    assert result['status'] == 'NEEDS_REVIEW'
    assert result['evidence'][0]['evidence_type'] == 'numeric_spotcheck_passed', json.dumps(diagnostic, ensure_ascii=False, indent=2)
    assert result['evidence'][0]['point_count'] == 1
    assert numeric_issue(result)['severity'] == 'warning'
    assert numeric_issue(result)['location'] == {'calculation_id':'S04.C01', 'unit_id':'S04.U05'}
    assert result['limitations'] and section['calculation_limitations']
    assert digest(section) == original_hash
    assert not any(e['evidence_type'] == 'symbolic_check_passed' for e in result['evidence'])


def test_numeric_counterexample_still_blocks():
    section = captured()['section']
    section['calculations'][0]['rhs'] = {'op':'Integer', 'value':2}
    result = check_math(section)
    assert result['status'] == 'FAIL'
    assert result['evidence'][0]['status'] == 'FAIL'
    assert any(i['rule_id'] == 'SYMBOLIC_COUNTERCHECK_FAILED' and i['severity'] == 'blocking'
               for i in result['issues'])
    assert not any(i['rule_id'] == 'NUMERIC_IS_NOT_PROOF' for i in result['issues'])


@pytest.mark.parametrize('change', ['unknown_ast', 'domain', 'uncertainty'])
def test_unknown_domains_and_declared_doubts_are_not_downgraded(change):
    section = captured()['section']
    calc = section['calculations'][0]
    if change == 'unknown_ast':
        calc['lhs'] = {'op':'UnsupportedOperation', 'args':[]}
    elif change == 'domain':
        # A point check at n=3 is defined even without a global nonzero assumption.
        # A claimed identity n/n=1 on all real n must retain its missing-domain doubt.
        section['calculations'] = [{'id':'S04.C01', 'unit_id':'S04.U05',
            'kind':'equivalence', 'assumptions':{'n':{'real':True}},
            'lhs':{'op':'Mul', 'args':[{'op':'Symbol', 'name':'n'},
                {'op':'Pow', 'args':[{'op':'Symbol', 'name':'n'}, {'op':'Integer', 'value':-1}]}]},
            'rhs':{'op':'Integer', 'value':1}}]
    else:
        section['uncertainties'] = ['该例的证明前提仍需核对。']
    result = check_math(section)
    assert result['status'] == 'NEEDS_REVIEW'
    assert any(i['severity'] == 'review' for i in result['issues'])
    if change != 'uncertainty':
        assert result['evidence'][0]['status'] == 'UNKNOWN'
        assert not any(i['rule_id'] == 'NUMERIC_IS_NOT_PROOF' for i in result['issues'])


class NumericProvider:
    """Captured math example, explicitly fake reviewer and no model networking."""
    def __init__(self, misuse=False):
        self.writes = self.reviews = self.patches = 0
        self.review_scopes = []
        self.misuse = misuse

    def generate(self, role, context, schema):
        if role == 'writer_lecture_section':
            self.writes += 1
            section = captured()['section']
            section['section_id'] = 'S01'
            for unit in section['units']:
                unit['id'] = unit['id'].replace('S04.', 'S01.')
                if unit['relates_to']:
                    unit['relates_to'] = unit['relates_to'].replace('S04.', 'S01.')
            section['calculations'][0]['unit_id'] = 'S01.U05'
            section['units'].insert(0, {'id':'S01.U00', 'kind':'definition',
                'tex':'正整数集上的实值函数称为实数列。', 'relates_to':None})
            if self.misuse:
                section['units'][1]['tex'] = '只检验第三项的数值，就已经证明整个无穷级数收敛。'
            return section
        if role == 'repair_local_patch':
            self.patches += 1
            raise AssertionError('A successful point sample must not itself request a content patch')
        assert role == 'reviewer_math'
        scope = context['scope']['kind']
        self.review_scopes.append(scope)
        if scope == 'chapter_coverage':
            return {'issues': [], 'checked_unit_ids': [u['id'] for u in context['units']],
                    'limitations': ['MOCK chapter reviewer; numeric evidence is checked in section_local scope.']}
        assert scope == 'section_local'
        self.reviews += 1
        assert context['tool_checks']['evidence'][0]['evidence_type'] == 'numeric_spotcheck_passed'
        return {'issues':[{'unit_id':'S01.U05', 'severity':'blocking',
                'message':'把单点数值抽查当作一般性证明，结论没有得到证明。',
                'evidence':'MOCK reviewer: actual source claims a finite sample proves the infinite series.'}]
                if self.misuse else [],
            'checked_unit_ids':[u['id'] for u in context['units']],
            'limitations':['MOCK reviewer; not teacher acceptance or formal proof.']}


def test_explicit_numeric_demo_with_independent_reasoning_never_consumes_repair_quota(tmp_path, monkeypatch):
    provider = NumericProvider()
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    completed, reports = pipeline.lecture(plan)
    assert len(completed) == 1 and len(compiled) == 1
    assert provider.writes == provider.reviews == 1 and provider.patches == 0
    assert provider.review_scopes == ['section_local', 'chapter_coverage']
    assert state(pipeline)['proposal_calls'] == 0
    assert state(pipeline)['unit_applied_counts'] == {}
    assert reports[0]['math']['status'] == 'NEEDS_REVIEW'
    assert numeric_issue(reports[0]['math'])['severity'] == 'warning'
    assert not service.store.get_run(pipeline.run['id'])['reviews']


def test_mock_reviewer_detected_misuse_still_blocks_despite_successful_sample(tmp_path, monkeypatch):
    provider = NumericProvider(misuse=True)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider, max_local_repair_attempts=0)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED'
    assert not compiled and provider.patches == 0
    saved = state(pipeline)
    assert any(i['severity'] == 'blocking' and i.get('unit_id') == 'S01.U05'
               for i in saved['pending_issues'])
    assert saved['proposal_calls'] == 0 and saved['unit_applied_counts'] == {}


def test_changed_tool_classification_reassesses_old_doubt_without_resetting_history_or_quota(tmp_path):
    section = captured()['section']
    _, _, recovery = direct_recovery(tmp_path, section)
    # Reproduce 3 legitimate proposals with only the first changing U05, in isolated state.
    for number in range(3):
        recovery.begin_proposal('strict_local_patch', ['unit:S04.U05'], ['S04.U05'])
        candidate = recovery.candidate()
        if number == 0:
            candidate['units'][0]['tex'] += '\n'
        recovery.accept(candidate)
    old_math = copy.deepcopy(captured()['previous_math_report'])
    old_identity, _ = recovery.review_context(candidate, old_math, {'issues':old_math['issues']})
    recovery.record_review(old_math['issues'], old_identity, {'math':old_math})
    historical_review = recovery.p.settings.workspace / recovery.state['last_review_key']
    historical_sha = digest(historical_review.read_bytes())
    old_counts = copy.deepcopy({k:recovery.state[k] for k in (
        'proposal_calls', 'applied_rounds', 'unit_applied_counts', 'proposal_counts_by_key')})
    new_math = check_math(candidate)
    identity, context = recovery.review_context(candidate, new_math, {'issues':new_math['issues']})
    assert context['unresolved_issues'] and identity != old_identity
    retained = recovery.record_review(new_math['issues'], identity, {'math':new_math})
    assert retained == []
    assert digest(historical_review.read_bytes()) == historical_sha
    assert {k:recovery.state[k] for k in old_counts} == old_counts
    assert old_counts['unit_applied_counts'] == {'S04.U05':1}
    assert old_counts['proposal_calls'] == 3
    assert recovery.state['teacher_visual_review'] == 'NOT_RUN'
    # The quota itself was not relaxed: requesting another U05 patch still fails.
    with pytest.raises(AgentError) as error:
        recovery.begin_proposal('strict_local_patch', ['unit:S04.U05'], ['S04.U05'])
    assert error.value.code == 'BUDGET_EXHAUSTED'
