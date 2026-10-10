import copy
import json

import pytest

from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest, within
from test_draft_recovery import setup_pipeline


class Provider:
    def __init__(self, fail_once=False, wrong=False):
        self.writes = self.patches = self.reviews = 0
        self.fail_once, self.wrong = fail_once, wrong

    def generate(self, role, context, schema):
        if role == 'writer_lecture_section':
            self.writes += 1
            return {'section_id': 'S01', 'units': [
                {'id': 'S01.U1', 'kind': 'definition', 'tex': '这里讨论实数的加法。', 'relates_to': None},
                {'id': 'S01.U2', 'kind': 'exercise', 'tex': r'计算 $1+1$。', 'relates_to': None}],
                'calculations': [], 'calculation_limitations': [], 'uncertainties': []}
        if role == 'repair_missing_answers':
            self.patches += 1
            assert context['targets'][0]['target_id'] == 'S01.U2'
            return {'section_id': 'S01', 'answers': [{'target_id': 'S01.U2', 'tex': r'$1+1=2$。'}],
                    'calculations': [{'id': 'NEW.C1', 'unit_id': 'S01.U2.answer', 'kind': 'equivalence',
                                      'assumptions': {}, 'lhs': {'op': 'Add', 'args': [
                                          {'op': 'Integer', 'value': 1}, {'op': 'Integer', 'value': 1}]},
                                      'rhs': {'op': 'Integer', 'value': 3 if self.wrong else 2}}]}
        assert role == 'reviewer_math'
        if context.get('scope', {}).get('kind') == 'chapter_coverage':
            return {'issues': [], 'checked_unit_ids': [u['id'] for u in context['units']],
                    'limitations': ['Neutral chapter fixture; answer recovery counters are local only.']}
        self.reviews += 1
        if len(context['units']) == 3 and self.fail_once:
            self.fail_once = False
            raise AgentError('PROVIDER_TIMEOUT', 'synthetic answer reviewer interruption')
        return {'issues': [], 'checked_unit_ids': [u['id'] for u in context['units']],
                'limitations': ['Synthetic provider; not live or teacher acceptance.']}


def setup(tmp_path, monkeypatch, provider, real_compile=False):
    service, pipeline, plan = setup_pipeline(tmp_path, provider,max_local_repair_attempts=1)
    pipeline.run['input']['provider'] = 'live'  # Replace the provider with the fake above; no request.
    plan['lecture']['exercises'] = 'with_answers'
    compiles = []
    if not real_compile:
        def compile(self, source, entry, build):
            compiles.append(source); build.mkdir()
            return {'status': 'PASS', 'issues': [], 'passes': 2, 'page_count': 1}
        monkeypatch.setattr(Pipeline, 'compile', compile)
    return service, pipeline, plan, compiles


@pytest.mark.windows_compile
def test_completion_pipeline_compiles_answers_at_end_with_numbered_link(tmp_path, monkeypatch):
    provider = Provider()
    service, pipeline, plan, _ = setup(tmp_path, monkeypatch, provider, real_compile=True)
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert provider.writes == provider.patches == 1 and provider.reviews == 2
    assert reports[0]['compile']['status'] == 'PASS' and reports[0]['math']['status'] == 'PASS'
    assert reports[0]['answer_recovery']['original_units_preserved']
    final_compile = reports[0]['compile_attempts'][-1]
    source_bytes = within(pipeline.settings.workspace, final_compile['source_key']).read_bytes()
    assert digest(source_bytes) == final_compile['source_hash']
    source = source_bytes.decode('utf-8')
    assert source.index(r'\section*{练习答案}') < source.index('% UNIT S01.U2.answer')
    assert r'\hyperref[mathagent:exercise:' in source
    original = json.loads(next(pipeline.build_root.glob('sS01*/candidate.json')).read_bytes())
    assert completed[0][1]['units'][:2] == original['units']
    assert service.store.get_run(pipeline.run['id'])['approval'] == approval
    assert not service.store.get_run(pipeline.run['id'])['reviews']


def test_cached_answer_after_review_failure_is_rechecked_not_regenerated(tmp_path, monkeypatch):
    provider = Provider(fail_once=True)
    _, pipeline, plan, compiles = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError, match='interruption'):
        pipeline.lecture(plan)
    assert provider.patches == 1 and not compiles
    pipeline.lecture(plan)
    assert provider.writes == provider.patches == 1 and provider.reviews == 3 and len(compiles) == 1
    assert any(json.loads(p.read_bytes())['status']=='UNCHECKED_REPAIRED' for p in
               pipeline.build_root.glob('sS01*/local-recovery.json'))


def test_added_wrong_calculation_cannot_pass_even_if_model_review_is_empty(tmp_path, monkeypatch):
    provider = Provider(wrong=True)
    _, pipeline, plan, compiles = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'BUDGET_EXHAUSTED' and not compiles
    report = json.loads(next(pipeline.build_root.glob('sS01*/review-1.json')).read_bytes())
    assert report['math']['status'] == 'FAIL'
    assert any(i.get('location', {}).get('unit_id') == 'S01.U2.answer' for i in report['math']['issues'])


def test_capacity_preflight_is_blocked_and_archived_before_model_call(tmp_path):
    from math_agent.answer_recovery import recover_missing_answers
    section={'section_id':'S01','units':[
        {'id':f'U{i}', 'kind':'exercise' if i==0 else 'explanation', 'tex':'保留。', 'relates_to':None}
        for i in range(100)]}
    with pytest.raises(AgentError) as error:
        recover_missing_answers(None, {'id':'S01'}, section, [], {}, tmp_path, 1)
    assert error.value.code=='ANSWER_COMPLETION_BLOCKED'
    assert json.loads((tmp_path/'answer-repair-1-preflight-blocked.json').read_bytes())['model_called'] is False
