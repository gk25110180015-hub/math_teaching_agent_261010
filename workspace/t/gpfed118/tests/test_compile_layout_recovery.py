"""Local compile repair must identify its scope and recheck the amended candidate."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.pipeline import Pipeline, render_lecture
from math_agent.util import AgentError, digest, within
from test_draft_recovery import setup_pipeline


def helper():
    from math_agent.compile_recovery import locate_overfull_units
    return locate_overfull_units


def fixture_tex():
    return '\\begin{document}\n% UNIT A\nfirst\nsecond\n% UNIT B\nthird\n\\end{document}\n'


def overfull(first=3, last=4, **location):
    return {'rule_id': 'OVERFULL_BOX', 'severity': 'blocking',
            'message': f'Overfull \\hbox (0.5104pt too wide) in paragraph at lines {first}--{last}',
            'location': {'log_line': 1, **location}}


@pytest.mark.unit
def test_precise_interval_maps_to_one_current_unit():
    result = helper()(fixture_tex(), [overfull()], {'A'}, {'A', 'B'})
    assert result['status'] == 'MAPPED'
    assert result['unit_ids'] == ['A']
    assert result['issues'][0]['location']['source_line'] == 3
    assert result['issues'][0]['evidence']['source_excerpt'] == 'first\nsecond'


@pytest.mark.unit
@pytest.mark.parametrize('tex,issue,current', [
    (fixture_tex(), overfull(4, 6), {'A', 'B'}),
    (fixture_tex(), overfull(1, 1), {'A'}),
    (fixture_tex(), overfull(), {'B'}),
    (fixture_tex(), overfull(file='theme.sty'), {'A'}),
    (fixture_tex(), overfull(file='other/lecture.tex'), {'A'}),
    (fixture_tex().replace('first', r'\input{extra.tex}'), overfull(), {'A'}),
    (fixture_tex().replace('second', '% UNIT A'), overfull(), {'A'}),
    (fixture_tex(), {**overfull(), 'message': 'Overfull \\vbox detected while output is active'}, {'A'}),
    (fixture_tex(), {**overfull(), 'rule_id': 'MISSING_GLYPH'}, {'A'}),
])
def test_ambiguous_or_nonlocal_failure_is_never_expanded(tex, issue, current):
    result = helper()(tex, [issue], current, {'A', 'B'})
    assert result['status'] == 'UNMAPPED'
    assert result['issues'] == []


@pytest.mark.unit
@pytest.mark.parametrize('replacement', [r'\small readable', r'\hfuzz=9pt readable',
    r'\hbadness=10000 readable', r'\resizebox{\textwidth}{!}{readable}'])
def test_layout_patch_cannot_suppress_diagnostics(replacement):
    from math_agent.compile_recovery import reject_layout_suppression
    before = {'units': [{'id': 'A', 'tex': 'readable'}]}
    with pytest.raises(AgentError) as error:
        reject_layout_suppression(before, {'units': [{'id': 'A', 'tex': replacement}]}, {'A'})
    assert error.value.code == 'REPAIR_SCOPE_VIOLATION'


class Provider:
    def __init__(self, *, no_change=False, escape_scope=False, real_tex=False):
        self.writes = self.reviews = self.patches = 0
        self.no_change, self.escape_scope, self.real_tex = no_change, escape_scope, real_tex
        self.inputs = []
        words = ' '.join(['Alpha beta gamma delta epsilon'] * 9)
        self.before = r'\mbox{' + words + '}' if real_tex else 'Long explanation before line reorganization.'
        self.after = words if real_tex else 'Long explanation before line reorganization.\n\nSPLIT_DONE'

    def generate(self, role, context, schema):
        self.inputs.append((role, copy.deepcopy(context)))
        if role == 'writer_lecture_section':
            self.writes += 1
            return {'section_id': 'S01', 'units': [
                {'id': 'S01.U1', 'kind': 'definition', 'tex': self.before, 'relates_to': None},
                {'id': 'S01.U2', 'kind': 'explanation', 'tex': 'Preserve this complete unit unchanged.', 'relates_to': None}],
                'calculations': [], 'calculation_limitations': [], 'uncertainties': []}
        if role == 'reviewer_math':
            self.reviews += 1
            return {'checked_unit_ids': [unit['id'] for unit in context['units']], 'issues': [], 'limitations': ['MOCK reviewer']}
        assert role == 'repair_local_patch'
        self.patches += 1
        assert context['allowed_unit_ids'] == ['S01.U1']
        replacements = [{'unit_id': 'S01.U1', 'tex': self.before if self.no_change else self.after}]
        if self.escape_scope:
            replacements.append({'unit_id': 'S01.U2', 'tex': 'Unauthorized change'})
        return {'section_id': 'S01', 'replacements': replacements, 'calculation_updates': [],
                'calculation_additions': [], 'uncertainties_append': [], 'calculation_limitations_append': []}


def fake_compiler(calls):
    def compile(self, source, entry, build):
        build.mkdir(parents=True)
        tex = (source / entry).read_text(encoding='utf-8')
        calls.append((source, build, tex))
        if 'SPLIT_DONE' in tex:
            return {'status': 'PASS', 'issues': [], 'log_paths': [], 'pdf_path': None, 'passes': 2, 'page_count': 1}
        first = tex[:tex.index('Long explanation')].count('\n') + 1
        issue = overfull(first, first)
        log = build / 'pass-2.tex.log'
        log.write_text(issue['message'] + '\n', encoding='utf-8')
        return {'status': 'FAIL', 'issues': [issue], 'log_paths': [str(log)], 'pdf_path': None, 'passes': 2}
    return compile


@pytest.mark.unit
def test_layout_fix_reuses_strict_patch_rechecks_math_and_preserves_both_builds(tmp_path, monkeypatch):
    from math_agent import mathcheck
    provider = Provider()
    _, pipeline, plan = setup_pipeline(tmp_path, provider)
    pipeline.run['input']['provider'] = 'live'  # Injected fake provider only; zero API calls.
    calls = []
    monkeypatch.setattr(Pipeline, 'compile', fake_compiler(calls))
    math_calls = []
    original = mathcheck.check_math
    monkeypatch.setattr(mathcheck, 'check_math', lambda section: (math_calls.append(copy.deepcopy(section)), original(section))[1])
    completed, reports = pipeline.lecture(plan)
    assert provider.writes == provider.patches == 1
    review_scopes = [context['scope']['kind'] for role, context in provider.inputs if role == 'reviewer_math']
    assert review_scopes == ['section_local', 'section_local', 'chapter_coverage']
    assert provider.reviews == len(review_scopes) == 3
    assert len(math_calls) == len(calls) == 2
    assert calls[0][0] != calls[1][0] and calls[0][1] != calls[1][1]
    assert 'SPLIT_DONE' not in (calls[0][0] / 'lecture.tex').read_text(encoding='utf-8')
    assert completed[0][1]['units'][1]['tex'] == 'Preserve this complete unit unchanged.'
    assert [item['compile_status'] for item in reports[0]['compile_attempts']] == ['FAIL', 'PASS']
    state = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
    assert state['unit_applied_counts'] == {'S01.U1': 1} and state['phase'] == 'CHECKED'
    assert state['evidence_dependencies']


@pytest.mark.unit
@pytest.mark.parametrize('escape_scope', [False, True])
def test_noop_or_out_of_scope_layout_proposal_retains_failure(tmp_path, monkeypatch, escape_scope):
    provider = Provider(no_change=not escape_scope, escape_scope=escape_scope)
    _, pipeline, plan = setup_pipeline(tmp_path, provider)
    pipeline.run['input']['provider'] = 'live'
    calls = []
    monkeypatch.setattr(Pipeline, 'compile', fake_compiler(calls))
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == ('REPAIR_SCOPE_VIOLATION' if escape_scope else 'BUDGET_EXHAUSTED')
    state = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
    candidate = json.loads(within(pipeline.settings.workspace, state['candidate_key']).read_bytes())
    assert candidate['units'][1]['tex'] == 'Preserve this complete unit unchanged.'
    assert state['pending_issues'] and state['phase'] != 'CHECKED'
    assert all((source / 'lecture.tex').exists() for source, _, _ in calls)


@pytest.mark.unit
@pytest.mark.parametrize('interruptions', [1, 2])
def test_resumed_layout_failure_cannot_bypass_suppression_guard(tmp_path, monkeypatch, interruptions):
    class InterruptedProvider(Provider):
        def generate(self, role, context, schema):
            if role == 'reviewer_math' and self.patches:
                self.reviews += 1
                return {'checked_unit_ids': [unit['id'] for unit in context['units']],
                    'issues': [{'unit_id': 'S01.U1', 'severity': 'review',
                                'message': 'The preserved formatting problem needs a local repair.',
                                'evidence': 'MOCK review after interrupted patch request'}], 'limitations': []}
            if role == 'repair_local_patch':
                self.patches += 1
                if self.patches <= interruptions:
                    raise AgentError('PROVIDER_TIMEOUT', 'MOCK interrupted layout patch')
                return {'section_id': 'S01', 'replacements': [{'unit_id': 'S01.U1',
                    'tex': r'\hfuzz=100pt ' + self.before}], 'calculation_updates': [],
                    'calculation_additions': [], 'uncertainties_append': [], 'calculation_limitations_append': []}
            return super().generate(role, context, schema)

    provider = InterruptedProvider()
    service, pipeline, plan = setup_pipeline(tmp_path, provider)
    pipeline.run['input']['provider'] = 'live'
    calls = []
    monkeypatch.setattr(Pipeline, 'compile', fake_compiler(calls))
    for number in range(interruptions):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == 'PROVIDER_TIMEOUT'
        saved = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
        assert saved['pending_compile_layout']['source_hash']
        service.store.finish(pipeline.job, 'FAILED', 'repair.section.S01', {'code': 'PROVIDER_TIMEOUT'})
        service.retry(pipeline.run['id'])
        pipeline = Pipeline(pipeline.settings, service.store, service.store.claim(f'resume-layout-{number}'))
        pipeline.provider = provider
        pipeline.run['input']['provider'] = 'live'
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'REPAIR_SCOPE_VIOLATION'
    saved = json.loads((pipeline.root / 'local-repair/S01.json').read_bytes())
    assert saved['pending_compile_layout'] and saved['rejected_proposals'] == 1
    candidate = json.loads(within(pipeline.settings.workspace, saved['candidate_key']).read_bytes())
    assert all(r'\hfuzz' not in unit['tex'] for unit in candidate['units'])
    assert len(calls) == 1  # Recovery cannot recompile and approve a tolerance-suppressed candidate.


@pytest.mark.windows_compile
def test_actual_overfull_is_locally_repaired_and_recompiled_without_smaller_font(tmp_path):
    from math_agent.compiler import resolve_xelatex
    engine = resolve_xelatex()
    if engine is None:
        pytest.skip('XeLaTeX unavailable; actual Windows compile NOT_RUN')
    provider = Provider(real_tex=True)
    _, pipeline, plan = setup_pipeline(tmp_path, provider, xelatex_path=str(engine))
    pipeline.run['input']['provider'] = 'live'  # Same injected provider, no real API.
    completed, reports = pipeline.lecture(plan)
    assert provider.writes == provider.patches == 1
    review_scopes = [context['scope']['kind'] for role, context in provider.inputs if role == 'reviewer_math']
    assert review_scopes == ['section_local', 'section_local', 'chapter_coverage']
    assert provider.reviews == len(review_scopes) == 3
    attempts = reports[0]['compile_attempts']
    assert [attempt['compile_status'] for attempt in attempts] == ['FAIL', 'PASS']
    assert attempts[0]['mapping']['unit_ids'] == ['S01.U1']
    assert completed[0][1]['units'][0]['tex'] == provider.after
    for attempt in attempts:
        source = within(pipeline.settings.workspace, attempt['source_key'])
        assert digest(source.read_bytes()) == attempt['source_hash']
        assert Path(json.loads(within(pipeline.settings.workspace, attempt['compile_key']).read_bytes())['pdf_path']).is_file()
