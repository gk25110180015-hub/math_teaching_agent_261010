"""SQLite/scoped repair feedback loop with explicit synthetic judgments and fake compiler."""
import copy
import json

import pytest

from math_agent.feedback_review import FeedbackReview
from math_agent.util import AgentError, digest
from test_recheck_feedback_pipeline import action
from test_teaching_quality_gate import TeachingProvider, teaching_setup


class ExplicitFeedbackProvider(TeachingProvider):
    def __init__(self, math_problem=False):
        super().__init__(problem=math_problem)
        self.feedback_calls = []
        self.feedback_fail_once = False
        self.feedback_order = []

    def generate(self, role, context, schema):
        if role == 'reviewer_feedback':
            self.feedback_calls.append(copy.deepcopy(context))
            self.feedback_order.append(len(self.repairs))
            if self.feedback_fail_once:
                self.feedback_fail_once = False
                raise AgentError('PROVIDER_ALL_UNAVAILABLE', 'Synthetic feedback-only unavailable')
            target = next(u for u in context['units'] if u['id'] == 'S02.U01')
            fixed = '模拟补全' in target['tex']
            return {'items': [{'id': f['id'], 'status': 'satisfied' if fixed else 'supported_improvement',
                'reason': '实际单元正文已具备所需参数域及边界说明。' if fixed else '现有正文只有固定例子，应按已批准目标补充一般参数域及边界说明。',
                'unit_ids': [target['id']], 'repair_unit_ids': [] if fixed else [target['id']],
                'unit_evidence': [{'unit_id': target['id'], 'quote': target['tex'], 'kind': 'statement'}],
                'objective_evidence': [{'section_id': 'S02', 'field': 'objectives',
                    'quote': context['plan']['sections'][1]['objectives'][0]}],
                'repair_instruction': None if fixed else '保留当前例子，在同一已有单元补足一般参数域及边界说明。'}
                for f in context['feedback_items']], 'limitations': ['Injected mock teaching judgments.']}
        result = super().generate(role, context, schema)
        if role == 'reviewer_math' and context['scope']['kind'] == 'chapter_coverage' and not result['issues']:
            result['issues'] = [{'unit_id': 'S02.U01', 'severity': 'warning',
                'message': '数学内容没有否决项，教学训练可能需要补充。', 'evidence': 'Synthetic warning retained.'}]
        return result


def test_warning_only_math_review_still_produces_scoped_feedback_improvement_and_receipts(tmp_path, monkeypatch):
    provider = ExplicitFeedbackProvider()
    service, pipeline, plan, compiles = teaching_setup(tmp_path, monkeypatch, provider)
    before, _ = pipeline.lecture(plan)
    approval = copy.deepcopy(service.store.get_run(pipeline.run['id'])['approval'])
    action(pipeline, plan)
    completed, reports = pipeline.lecture(plan)
    assert len(provider.repairs) == 1 and provider.repairs[0]['allowed_unit_ids'] == ['S02.U01']
    assert '反馈教学改进（不等于数学错误）' in provider.repairs[0]['issues'][0]['message']
    assert provider.feedback_order == [0, 1]
    assert completed[0] == before[0] and '模拟补全' in completed[1][1]['units'][0]['tex']
    assert len(compiles) == 3 and provider.writes == ['S01', 'S02']
    final = next(report['feedback_review'] for report in reports if 'feedback_review' in report)
    assert final['items'][0]['status'] == 'satisfied' and final['items'][0]['repair_unit_ids'] == []
    ordinary = next(report['review'] for report in reports if 'chapter_coverage' in report)
    assert ordinary['issues'][0]['severity'] == 'warning'
    with service.store.connect() as c:
        events = [json.loads(r[0]) for r in c.execute("SELECT payload_json FROM events WHERE run_id=? AND type='feedback.reviewed' ORDER BY sequence", (pipeline.run['id'],))]
    assert [e['items'][0]['status'] for e in events] == ['supported_improvement', 'satisfied']
    for event in events:
        path = pipeline.settings.workspace/event['evidence_key']
        assert digest(path.read_bytes()) == event['evidence_sha256']
        assert event['job_id'] == pipeline.job['id'] and event['teacher_review'] == 'NOT_RUN'
    state = json.loads((pipeline.root/'global-repair-state.json').read_bytes())
    assert state['rounds_used'] == 1
    current = service.store.get_run(pipeline.run['id'])
    assert current['approval'] == approval and current['reviews'] == []


def test_math_concern_is_repaired_before_feedback_failure_and_retry_preserves_rounds(tmp_path, monkeypatch):
    provider = ExplicitFeedbackProvider(math_problem=True)
    provider.feedback_fail_once = True
    _, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, provider)
    action(pipeline, plan)
    with pytest.raises(AgentError) as error: pipeline.lecture(plan)
    assert error.value.code == 'FEEDBACK_REVIEW_BLOCKED'
    assert len(provider.repairs) == 1 and provider.feedback_order == [1]
    # First ordinary review found a definite concern. It reached the original
    # repair state BEFORE any feedback call, never an in-memory discarded issue.
    failure = json.loads((pipeline.root/'global_review_failure.json').read_bytes())
    assert failure['issues'][0]['message'] == '批准目标的一般参数范围仅由单个特例代替。'
    state = json.loads((pipeline.root/'global-repair-state.json').read_bytes())
    assert state['rounds_used'] == 1
    completed, reports = pipeline.lecture(plan)
    assert provider.feedback_order == [1, 1] and len(provider.repairs) == 1
    assert provider.feedback_calls[0] == provider.feedback_calls[1]
    assert json.loads((pipeline.root/'global-repair-state.json').read_bytes())['rounds_used'] == 1
    assert any('feedback_review' in r for r in reports)


def test_feedback_evidence_write_is_fenced_by_actual_job_lease(tmp_path, monkeypatch):
    provider = ExplicitFeedbackProvider()
    _, pipeline, plan, _ = teaching_setup(tmp_path, monkeypatch, provider)
    completed, _ = pipeline._lecture_sections(plan)
    action(pipeline, plan)
    guard = FeedbackReview(pipeline, plan, [u for _, s in completed for u in s['units']], pipeline._recheck_feedback(plan))
    pipeline.store.finish(pipeline.job, 'FAILED', 'synthetic.lease_end', {'code': 'PROVIDER_TIMEOUT'})
    with pytest.raises(AgentError): guard.evaluate()
    assert not provider.feedback_calls and not guard.state_path.exists()
