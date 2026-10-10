"""Offline regression for malformed dispositions blocking valid independent repairs.

The captured least-squares response remains invalid. Only independently located
ordinary/tool findings may authorize a patch; a new body still needs a complete
new disposition. All providers and compilation in this module are injected.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from math_agent.pipeline import Pipeline
from math_agent.uncertainty_review import (
    UncertaintyReview, declared_doubts, validate_uncertainty_assessment,
)
from math_agent.util import AgentError, digest, within
from test_local_recovery import direct_recovery, setup, state


CAPTURE = Path(__file__).parent / 'fixtures' / 'uncertainty_least_squares'
ORIGINAL_NOTE = '练习答案的分数计算仍需核查；请确认所有结果一致。'
INDEPENDENT = [
    {'unit_id': 'S01.U10', 'severity': 'blocking',
     'message': '独立普通审阅：练习答案算术错误。', 'evidence': '受控离线正文核对。'},
    {'unit_id': 'S01.U04', 'severity': 'review',
     'message': '独立普通审阅：正规方程验证缺失。', 'evidence': '受控离线证明核对。'},
]


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.startswith(('MATH_AGENT_', 'OPENAI_', 'DEEPSEEK_')):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')


def captured(name):
    return json.loads((CAPTURE / name).read_bytes())


def sample_section():
    return {'section_id': 'S01', 'units': [
        {'id': 'S01.U01', 'kind': 'definition',
         'tex': '最小二乘法以残差平方和作为待最小化的目标函数。', 'relates_to': None},
        {'id': 'S01.U04', 'kind': 'proof',
         'tex': '本证明需要将给定候选参数代入两条正规方程验证。', 'relates_to': None},
        {'id': 'S01.U10', 'kind': 'solution',
         'tex': '本练习答案的有限求和及相应分数结果需要重新核对。', 'relates_to': None},
    ], 'calculations': [], 'calculation_limitations': [], 'uncertainties': [ORIGINAL_NOTE]}


class IndependentProvider:
    def __init__(self, *, issues=True, patch='correct', after='resolved_by_current_body',
                 invalid_target='S01.U01', failure=None):
        self.issues = issues
        self.patch = patch
        self.after = after
        self.invalid_target = invalid_target
        self.failure = failure
        self.writes = 0
        self.ordinary = []
        self.dispositions = []
        self.patches = []
        self.chapter_calls = 0

    def generate(self, role, context, schema):
        if role == 'writer_lecture_section':
            self.writes += 1
            return sample_section()
        if role == 'reviewer_math':
            if context.get('scope', {}).get('kind') == 'chapter_coverage':
                self.chapter_calls += 1
                issues = []
            else:
                self.ordinary.append(copy.deepcopy(context))
                fixed = any('已完成独立修复' in u['tex'] for u in context['units'])
                issues = copy.deepcopy(INDEPENDENT) if self.issues and not fixed else []
            return {'issues': issues, 'checked_unit_ids': [u['id'] for u in context['units']],
                    'limitations': ['Offline injected review; no teacher acceptance.']}
        if role == 'reviewer_uncertainty':
            self.dispositions.append(copy.deepcopy(context))
            if self.failure:
                failure, self.failure = self.failure, None
                raise AgentError(failure, 'Injected completed/transport failure')
            fixed = any('已完成独立修复' in u['tex'] for u in context['section']['units'])
            status = self.after if fixed else 'invalid'
            target = self.invalid_target if status == 'invalid' else None
            source = next(s for s in context['sources'] if s['source_key'] == 'current:' + (target or 'S01.U10'))
            return {'items': [{
                'uncertainty_id': note['uncertainty_id'], 'unit_id': target,
                'disposition': 'open_actionable' if status == 'invalid' else status,
                'reason': '离线受控裁定：保留数学疑点，并依据实际提供正文进行独立核查。',
                'evidence': [{'source_key': source['source_key'], 'source_sha256': source['source_sha256'],
                              'quote': source['tex']}],
                'remaining_dependency': status == 'open_dependency',
                'repair_instruction': 'INVALID_ONLY：强制修改该未授权单元的全部内容。' if status == 'invalid' else None,
            } for note in context['declared_doubts']], 'limitations': ['Offline injected disposition.']}
        assert role == 'repair_local_patch'
        self.patches.append(copy.deepcopy(context))
        units = {unit['id']: unit for unit in context['section']['units']}
        replacements = [{'unit_id': key, 'tex': units[key]['tex'] + ' 已完成独立修复并逐项核验。'}
                        for key in context['allowed_unit_ids']]
        result = {'section_id': 'S01', 'replacements': replacements, 'calculation_updates': [],
                  'calculation_additions': [], 'uncertainties_append': [], 'calculation_limitations_append': []}
        patch = self.patch
        if patch == 'outside_once':
            self.patch = 'correct'
            result['replacements'].append({'unit_id': 'S01.U01', 'tex': '非法扩大范围的正文。'})
        elif patch in ('noop', 'notes', 'calculation', 'whitespace', 'comment'):
            suffix = {'whitespace': ' \n ', 'comment': '\n% 无数学内容的注释\n'}.get(patch, '')
            result['replacements'] = [{'unit_id': key, 'tex': units[key]['tex'] + suffix}
                                      for key in context['allowed_unit_ids']]
            if patch == 'notes':
                result['calculation_limitations_append'] = ['仅增加核算覆盖说明，正文没有改变。']
            elif patch == 'calculation':
                result['calculation_additions'] = [{'id': 'C1', 'unit_id': 'S01.U10', 'kind': 'equivalence',
                    'lhs': {'op': 'Integer', 'value': 1}, 'rhs': {'op': 'Integer', 'value': 1}, 'assumptions': {}}]
        return result


def latest_report(pipeline):
    saved = state(pipeline)
    return json.loads(within(pipeline.settings.workspace, saved['last_review_key']).read_bytes())['report']


def review_states(pipeline):
    return [json.loads(path.read_bytes()) for path in (pipeline.root / 'uncertainty-reviews').glob('*/state.json')]


def assert_no_checkpoint(pipeline):
    with pipeline.store.connect() as connection:
        assert connection.execute('SELECT count(*) FROM steps WHERE run_id=?', (pipeline.run['id'],)).fetchone()[0] == 0


def test_real_least_squares_invalid_owner_replays_without_redrawing(tmp_path):
    context, response = captured('input.json'), captured('response-1.json')
    ordinary = captured('ordinary-review.json')
    assert declared_doubts(context['section'])[0]['unit_id'] is None
    assert response['items'][0]['unit_id'] == 'S01.U10'
    assert {issue['unit_id'] for issue in ordinary['issues']} == {'S01.U04', 'S01.U10'}
    failure = captured('failure-1.json')
    assert failure['message'] == 'Disposition cannot guess or change the declared owner'
    with pytest.raises(ValueError, match='cannot guess or change'):
        validate_uncertainty_assessment(response, context)
    pipeline, _, _ = direct_recovery(tmp_path)
    calls = []
    class CapturedProvider:
        def generate(self, role, ctx, schema):
            assert role == 'reviewer_uncertainty'
            calls.append(copy.deepcopy(ctx))
            return copy.deepcopy(response)
    pipeline.provider = CapturedProvider()
    guard = UncertaintyReview(pipeline, context)
    guard.ordinary_review(lambda _: copy.deepcopy(ordinary), {})
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            guard.evaluate()
        assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'
    assert len(calls) == 1
    assert guard.state['status'] == 'INVALID'
    assert guard._read('ordinary-review.json') == ordinary
    assert guard._read('response-1.json') == response
    assert guard._read('failure-1.json')['message'] == failure['message']


@pytest.mark.parametrize('failure', [None, 'INVALID_MODEL_JSON'])
def test_independent_repair_survives_invalid_disposition_and_rechecks_every_doubt(tmp_path, monkeypatch, failure):
    provider = IndependentProvider(failure=failure)
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert len(completed) == len(compiled) == 1
    assert provider.writes == len(provider.patches) == 1
    assert len(provider.ordinary) == len(provider.dispositions) == 2
    assert provider.chapter_calls == 1
    assert provider.patches[0]['allowed_unit_ids'] == ['S01.U04', 'S01.U10']
    assert provider.patches[0]['issues'] == INDEPENDENT
    assert 'INVALID_ONLY' not in json.dumps(provider.patches[0], ensure_ascii=False)
    assert completed[0][1]['units'][0] == sample_section()['units'][0]
    assert completed[0][1]['uncertainties'] == [ORIGINAL_NOTE]
    assert state(pipeline)['unit_applied_counts'] == {'S01.U04': 1, 'S01.U10': 1}
    assert not state(pipeline)['pending_issues']
    assert {saved['status'] for saved in review_states(pipeline)} == {'INVALID', 'REVIEWED'}
    assert reports[0]['uncertainty_review']['assessment']['items'][0]['unit_id'] is None
    assert service.store.get_run(pipeline.run['id'])['approval'] == approval
    assert not service.store.get_run(pipeline.run['id'])['reviews']
    assert provider.dispositions[0]['section']['uncertainties'] == provider.dispositions[1]['section']['uncertainties']
    prior_reports = [json.loads(path.read_bytes()) for path in (pipeline.root / 'local-repair/S01').glob('review-*.json')]
    invalid_report = next(record for record in prior_reports if record['report']['uncertainty_review'].get('status') == 'INVALID')
    assert {digest(issue) for issue in INDEPENDENT}.issubset({digest(issue) for issue in invalid_report['retained_issues']})
    assert any(issue.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY' for issue in invalid_report['retained_issues'])
    assert 'assessment' not in invalid_report['report']['uncertainty_review']


def test_invalid_disposition_without_independent_issue_keeps_doubt_and_does_not_patch(tmp_path, monkeypatch):
    provider = IndependentProvider(issues=False)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == 'UNCERTAINTY_REVIEW_BLOCKED'
        assert latest_report(pipeline)['uncertainty_review']['failure']['message'] == 'Disposition cannot guess or change the declared owner'
    assert not provider.patches and not compiled
    assert provider.writes == len(provider.ordinary) == len(provider.dispositions) == 1
    assert state(pipeline)['pending_issues'][0]['message'] == ORIGINAL_NOTE
    assert latest_report(pipeline)['uncertainty_review']['status'] == 'INVALID'
    assert_no_checkpoint(pipeline)


def test_deterministically_located_defect_alone_can_authorize_independent_repair(tmp_path, monkeypatch):
    class DeterministicProvider(IndependentProvider):
        def generate(self, role, context, schema):
            result = super().generate(role, context, schema)
            if role == 'writer_lecture_section':
                result['units'][2]['tex'] = 'S01.U10：' + result['units'][2]['tex']
            elif role == 'repair_local_patch':
                for replacement in result['replacements']:
                    replacement['tex'] = replacement['tex'].replace('S01.U10：', '')
            return result
    provider = DeterministicProvider(issues=False)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    completed, _ = pipeline.lecture(plan)
    assert len(compiled) == len(provider.patches) == 1
    assert provider.patches[0]['allowed_unit_ids'] == ['S01.U10']
    assert {issue['rule_id'] for issue in provider.patches[0]['issues']} == {'INTERNAL_UNIT_ID_VISIBLE'}
    assert state(pipeline)['unit_applied_counts'] == {'S01.U10': 1}
    assert completed[0][1]['units'][:2] == sample_section()['units'][:2]
    assert len(provider.dispositions) == 2


def test_every_original_doubt_survives_invalid_report_and_is_reassessed_after_patch(tmp_path, monkeypatch):
    provider = IndependentProvider()
    generate = provider.generate
    extra_note = '正规方程候选解满足最优性条件的完整论证仍需核查。'
    def with_two_doubts(role, context, schema):
        result = generate(role, context, schema)
        if role == 'writer_lecture_section':
            result['uncertainties'].append(extra_note)
        return result
    provider.generate = with_two_doubts
    _, pipeline, plan, _ = setup(tmp_path, monkeypatch, provider)
    completed, reports = pipeline.lecture(plan)
    assert completed[0][1]['uncertainties'] == [ORIGINAL_NOTE, extra_note]
    assert provider.dispositions[0]['declared_doubts'] == provider.dispositions[1]['declared_doubts']
    assert len(reports[0]['uncertainty_review']['assessment']['items']) == 2
    saved = [json.loads(path.read_bytes()) for path in (pipeline.root / 'local-repair/S01').glob('review-*.json')]
    invalid = next(record for record in saved if record['report']['uncertainty_review'].get('status') == 'INVALID')
    preserved = [issue for issue in invalid['retained_issues'] if issue.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY']
    assert {issue['message'] for issue in preserved} == {ORIGINAL_NOTE, extra_note}


def test_rejected_expansion_retains_frozen_ordinary_issues_through_formal_retry(tmp_path, monkeypatch):
    provider = IndependentProvider(patch='outside_once')
    service, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == 'REPAIR_SCOPE_VIOLATION'
    saved = state(pipeline)
    assert saved['proposal_calls'] == saved['rejected_proposals'] == 1
    assert saved['unit_applied_counts'] == {} and not compiled
    assert json.loads(within(pipeline.settings.workspace, saved['candidate_key']).read_bytes()) == sample_section()
    assert {digest(i) for i in INDEPENDENT}.issubset({digest(i) for i in saved['pending_issues']})
    old_evidence = {path: digest(path.read_bytes()) for path in (pipeline.root / 'uncertainty-reviews').glob('*/*.json')}
    service.store.finish(pipeline.job, 'BLOCKED', 'review.section.S01', {'code': error.value.code})
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, service.store, service.store.claim('offline-independent-retry'))
    resumed.provider = provider
    resumed.run['input']['provider'] = 'live'
    completed, _ = resumed.lecture(plan)
    assert completed and len(compiled) == 1
    assert provider.writes == 1 and len(provider.patches) == len(provider.ordinary) == len(provider.dispositions) == 2
    assert provider.patches[0]['issues'] == provider.patches[1]['issues'] == INDEPENDENT
    assert all(provider.patches[index]['allowed_unit_ids'] == ['S01.U04', 'S01.U10'] for index in range(2))
    assert all(digest(path.read_bytes()) == sha for path, sha in old_evidence.items())
    assert state(resumed)['proposal_calls'] == 2 and state(resumed)['rejected_proposals'] == 1
    assert state(resumed)['unit_applied_counts'] == {'S01.U04': 1, 'S01.U10': 1}


@pytest.mark.parametrize('patch', ['noop', 'notes', 'calculation', 'whitespace', 'comment'])
def test_nonbody_proposals_cannot_redraw_invalid_judgment_or_reset_budget(tmp_path, monkeypatch, patch):
    provider = IndependentProvider(patch=patch)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for expected_code in ['REPAIR_SCOPE_VIOLATION', 'REPAIR_SCOPE_VIOLATION', 'BUDGET_EXHAUSTED', 'BUDGET_EXHAUSTED']:
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == expected_code
    assert provider.writes == len(provider.ordinary) == len(provider.dispositions) == 1
    assert len(provider.patches) == 2 and not compiled
    saved = state(pipeline)
    assert saved['proposal_calls'] == saved['rejected_proposals'] == 2
    assert saved['unit_applied_counts'] == {}
    assert json.loads(within(pipeline.settings.workspace, saved['candidate_key']).read_bytes()) == sample_section()
    assert {digest(i) for i in INDEPENDENT}.issubset({digest(i) for i in saved['pending_issues']})
    assert any(i.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY' for i in saved['pending_issues'])
    assert len(review_states(pipeline)) == 1
    assert_no_checkpoint(pipeline)


@pytest.mark.parametrize('after,code', [('invalid', 'UNCERTAINTY_REVIEW_BLOCKED'),
                                     ('open_dependency', 'UNCERTAINTY_DEPENDENCY_BLOCKED')])
def test_changed_body_still_cannot_compile_with_unresolved_original_doubt(tmp_path, monkeypatch, after, code):
    provider = IndependentProvider(after=after)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    for _ in range(2):
        with pytest.raises(AgentError) as error:
            pipeline.lecture(plan)
        assert error.value.code == code
    assert not compiled and not provider.chapter_calls
    assert len(provider.patches) == 1
    assert len(provider.dispositions) == len(provider.ordinary) == 2
    assert state(pipeline)['unit_applied_counts'] == {'S01.U04': 1, 'S01.U10': 1}
    assert any(i.get('rule_id') == 'DECLARED_MATH_UNCERTAINTY' for i in state(pipeline)['pending_issues'])
    assert_no_checkpoint(pipeline)


@pytest.mark.parametrize('failure', ['PROVIDER_ALL_UNAVAILABLE', 'PROVIDER_EMPTY_RESPONSE', 'BUDGET_EXHAUSTED'])
def test_transport_failure_does_not_authorize_independent_patch(tmp_path, monkeypatch, failure):
    provider = IndependentProvider(failure=failure)
    _, pipeline, plan, compiled = setup(tmp_path, monkeypatch, provider)
    with pytest.raises(AgentError) as error:
        pipeline.lecture(plan)
    assert error.value.code == ('BUDGET_EXHAUSTED' if failure == 'BUDGET_EXHAUSTED' else 'UNCERTAINTY_REVIEW_BLOCKED')
    assert not provider.patches and not compiled
    assert review_states(pipeline)[0]['status'] == 'TRANSPORT_PENDING'
    assert_no_checkpoint(pipeline)
    completed, _ = pipeline.lecture(plan)
    assert completed and len(compiled) == 1
    assert len(provider.dispositions) == 3 and len(provider.ordinary) == 2
    assert provider.dispositions[0] == provider.dispositions[1]
    assert provider.patches[0]['issues'] == INDEPENDENT
