"""Mock workflow tests; these do not evaluate a live reviewer's mathematical judgment."""
import copy
import json

import pytest

from math_agent.domain import ConfirmRequest, ExecuteRequest, NewRun
from math_agent.pipeline import Pipeline
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError
from test_global_repair import GlobalRepairProvider, setup


@pytest.mark.unit
@pytest.mark.parametrize('tex,blocked', [
    ('由 S03.U05 得到结论。', True),
    (r'参见 \textbf{S12-U09}。', True),
    (r'\label{S03.U05}实际定理正文。', False),
    (r'由定理\ref*{S03.U05}和公式\eqref{S12-U09}可知。', False),
    (r'\hyperref[S03.U05]{先前的商法则}', False),
    (r'\hyperref[S03.U05]{参见 S03.U05}', True),
    (r'\href{https://example.invalid/S03.U05}{参考资料}', False),
    (r'\hypertarget{S03.U05}{定理正文}', False),
    (r'\hypertarget{S03.U05}{内部编号 S03.U05}', True),
    ('% 内部处理备注 S03.U05\n正文无内部编号。', False),
    (r'\iffalse S03.U05\fi 有效正文。', False),
    (r'约定 $S_0=0$；变量 $S_{03}$ 与 $U_{05}$ 均已定义。', False),
    ('XS03.U05Z 是完整数据标识，并非单元引用。', False),
])
def test_only_visible_unambiguous_workflow_ids_block_student_prose(tex, blocked):
    section = {'section_id': 'S01', 'units': [
        {'id': 'S01.U01', 'kind': 'explanation', 'tex': tex, 'relates_to': None}]}
    issues = Pipeline.validate_written(None, {'id': 'S01', 'required_kinds': []}, section, {'lecture': {}})
    leaked = [issue for issue in issues if issue.get('rule_id') == 'INTERNAL_UNIT_ID_VISIBLE']
    assert bool(leaked) == blocked
    assert all(issue['unit_id'] == 'S01.U01' and issue['severity'] == 'blocking' for issue in leaked)


class TeachingProvider:
    def __init__(self, problem=True):
        self.problem = problem
        self.writes = []
        self.reviews = []
        self.repairs = []

    def generate(self, role, context, schema):
        if role == 'reviewer_feedback':
            from math_agent.feedback_review import mock_feedback_assessment
            return mock_feedback_assessment(context)
        if role == 'writer_lecture_section':
            sid = context['section']['id']
            self.writes.append(sid)
            return {'section_id': sid, 'units': [{'id': sid+'.U01', 'kind': 'explanation',
                'tex': r'约定 $A_0=0$，表示空和。' if sid == 'S01' else '本节当前只有一个具体参数例子。',
                'relates_to': None}], 'calculations': [], 'uncertainties': []}
        if role == 'repair_content_unit':
            self.repairs.append(copy.deepcopy(context))
            result = copy.deepcopy(context['section'])
            result['units'][0]['tex'] += ' 模拟补全已批准的参数域及边界说明；不代表真实数学验收。'
            self.problem = False
            return result
        assert role == 'reviewer_math'
        self.reviews.append(copy.deepcopy(context))
        issues = []
        if context['scope']['kind'] == 'chapter_coverage' and self.problem:
            issues = [{'unit_id': 'S02.U01', 'severity': 'review',
                'message': '批准目标的一般参数范围仅由单个特例代替。',
                'evidence': 'Synthetic fixture judgment; not an evaluation of model judgment.'}]
        return {'issues': issues, 'checked_unit_ids': [u['id'] for u in context['units']],
                'limitations': ['Mock review: no live semantic accuracy claim.']}


def teaching_setup(tmp_path, monkeypatch, provider, count=2):
    settings = Settings(workspace=tmp_path/'w', reference_root=tmp_path/'refs')
    service = Service(settings)
    run = service.create(NewRun(workflow_id='lecture.generate', topic='Synthetic teaching coverage', trusted_input=True))
    plan = {'title': 'Synthetic teaching coverage', 'provider': 'mock', 'difficulty': 'synthetic',
        'theme': 'default', 'objectives': ['覆盖已批准目标并保持符号约定一致。'],
        'sections': [{'id': f'S{i:02d}', 'title': f'Section {i}', 'objectives':
            ['给出初值和空和约定。'] if i == 1 else ['陈述一般参数的合法域与边界，不能只给固定参数例子。'],
            'required_kinds': [], 'reference_labels': [],
            'prerequisites': [] if i == 1 else [f'S{i-1:02d}']} for i in range(1, count+1)],
        'lecture': {'exercises': 'none', 'proof_policy': 'key', 'answers_location': 'end'},
        'questions': [], 'unresolved_blocking_questions': [], 'decisions': [], 'decision_ids': []}
    with service.store.transaction() as connection:
        service.store.save_plan(connection, run['id'], plan)
    plan = service.store.get_run(run['id'])['plan']
    service.confirm(run['id'], ConfirmRequest(expected_plan_revision=plan['revision'],
        expected_plan_hash=plan['hash'], action_id='offline-teaching'))
    service.execute(run['id'], ExecuteRequest(expected_plan_revision=plan['revision'],
        expected_plan_hash=plan['hash'], idempotency_key='offline-teaching'))
    pipeline = Pipeline(settings, service.store, service.store.claim('offline-teaching-worker'))
    pipeline.provider = provider
    compiles = []

    def compile(self, source, entry, build):
        build.mkdir()
        compiles.append(str(source))
        return {'status': 'PASS', 'issues': [], 'passes': 2, 'page_count': 1, 'pdf_path': None,
                'fixture': 'OFFLINE_FAKE_COMPILER'}

    monkeypatch.setattr(Pipeline, 'compile', compile)
    return service, pipeline, plan, compiles


@pytest.mark.unit
def test_full_chapter_objective_gap_uses_existing_scoped_global_repair(tmp_path, monkeypatch):
    provider = TeachingProvider()
    service, pipeline, plan, compiles = teaching_setup(tmp_path, monkeypatch, provider)
    approved = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    completed, reports = pipeline.lecture(plan)
    assert provider.writes == ['S01', 'S02']
    assert len(provider.repairs) == 1 and provider.repairs[0]['allowed_unit_ids'] == ['S02.U01']
    whole = [context for context in provider.reviews if context['scope']['kind'] == 'chapter_coverage']
    assert len(whole) == 2 and whole[0]['scope']['pending_sections'] == []
    assert whole[0]['section_unit_map'][1]['objectives'] == plan['sections'][1]['objectives']
    assert whole[0]['actual_unit_ids'] == ['S01.U01', 'S02.U01']
    assert r'A_0=0' in whole[0]['units'][0]['tex']
    assert '模拟补全' in completed[1][1]['units'][0]['tex'] and len(compiles) == 3
    assert any('chapter_coverage' in report for report in reports)
    assert (pipeline.root/'global_review_failure.json').is_file()
    assert service.store.get_run(pipeline.run['id'])['approval'] == approved
    assert service.store.get_run(pipeline.run['id'])['reviews'] == []


@pytest.mark.unit
def test_adjacent_review_receives_actual_earlier_initial_value_context(tmp_path, monkeypatch):
    provider = TeachingProvider(problem=False)
    _, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, provider, count=3)
    pipeline.lecture(plan)
    adjacent = [context for context in provider.reviews if context['scope']['kind'] == 'adjacent_interface']
    assert len(adjacent) == 2
    assert adjacent[0]['prior_sections'] == []
    assert adjacent[1]['prior_sections'][0]['section_id'] == 'S01'
    assert r'A_0=0' in adjacent[1]['prior_sections'][0]['units'][0]['tex']
    whole = next(context for context in provider.reviews if context['scope']['kind'] == 'chapter_coverage')
    assert len(whole['section_unit_map']) == 3 and len(whole['units']) == 3


@pytest.mark.unit
def test_incomplete_chapter_cannot_be_reviewed_as_full_coverage(tmp_path, monkeypatch):
    provider = TeachingProvider(problem=False)
    _, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, provider)
    completed, _ = pipeline._lecture_sections(plan)
    before = len(provider.reviews)
    with pytest.raises(AgentError) as error:
        pipeline._global_interfaces(completed[:1], plan)
    assert error.value.code == 'INCOMPLETE_CHAPTER_REVIEW'
    assert len(provider.reviews) == before


@pytest.mark.unit
@pytest.mark.parametrize('interrupt_recheck', [False, True])
def test_accepted_uncheckpointed_section_survives_upstream_change_after_compile_failure(tmp_path, monkeypatch, interrupt_recheck):
    provider = GlobalRepairProvider()
    service, pipeline, plan, _ = setup(tmp_path, provider, monkeypatch)
    normal_compile = Pipeline.compile
    fail_once = [True]

    def interrupted_compile(self, source, entry, build):
        if 'sS02_' in str(source) and fail_once[0]:
            fail_once[0] = False
            raise AgentError('COMPILE_FAILED', 'Synthetic compile interruption after successful local review')
        return normal_compile(self, source, entry, build)

    monkeypatch.setattr(Pipeline, 'compile', interrupted_compile)
    with pytest.raises(AgentError, match='compile interruption'):
        pipeline._lecture_sections(plan)
    with pipeline.store.connect() as connection:
        row = connection.execute('SELECT output_json FROM steps WHERE run_id=? AND step_key=?',
            (pipeline.run['id'], 'section.S01')).fetchone()
        assert connection.execute('SELECT count(*) FROM steps WHERE run_id=? AND step_key=?',
            (pipeline.run['id'], 'section.S02')).fetchone()[0] == 0
    upstream = json.loads(row[0])['generated']
    upstream['units'][0]['tex'] += ' 新增明确的前提。'
    state_path = pipeline.root/'local-repair/S02.json'
    state_before = json.loads(state_path.read_bytes())
    assert state_before['phase'] == 'LOCAL_CHECKS_PENDING_COMPILE'
    original_candidate = (pipeline.settings.workspace/state_before['candidate_key']).read_bytes()
    service.store.finish(pipeline.job, 'FAILED', 'compile.section.S02', {'code': 'COMPILE_FAILED'})
    service.retry(pipeline.run['id'])
    resumed = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-resumed-teaching'))
    resumed.provider = provider
    if interrupt_recheck:
        provider.fail_following_once = True
        with pytest.raises(AgentError, match='following-section'):
            resumed._lecture_sections(plan, {'S01': upstream})
        service.store.finish(resumed.job, 'FAILED', 'review.section.S02', {'code': 'PROVIDER_TIMEOUT'})
        service.retry(resumed.run['id'])
        resumed = Pipeline(pipeline.settings, pipeline.store, pipeline.store.claim('offline-third-attempt'))
        resumed.provider = provider
        completed, _ = resumed._lecture_sections(plan)
    else:
        completed, _ = resumed._lecture_sections(plan, {'S01': upstream})
    assert provider.writes == ['S01', 'S02']
    assert provider.locals == ['S01', 'S02', 'S01', 'S02'] + (['S02'] if interrupt_recheck else [])
    assert completed[1][1] == json.loads(original_candidate)
    state_after = json.loads(state_path.read_bytes())
    assert state_after['phase'] == 'CHECKED'
    for field in ('proposal_calls', 'applied_rounds', 'unit_applied_counts', 'rejected_proposals'):
        assert state_after[field] == state_before[field]
    assert list(resumed.build_root.glob('sS02_*/unchecked-local-recheck.json'))


@pytest.mark.unit
def test_single_completed_section_still_has_explicit_whole_document_review(tmp_path, monkeypatch):
    provider = TeachingProvider(problem=False)
    _, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, provider, count=1)
    pipeline.lecture(plan)
    whole = [context for context in provider.reviews if context['scope']['kind'] == 'chapter_coverage']
    assert len(whole) == 1 and len(whole[0]['section_unit_map']) == 1
