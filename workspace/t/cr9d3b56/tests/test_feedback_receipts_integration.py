"""Real local API -> Pipeline feedback assessment -> scoped repair -> receipt GET.

Provider and compiler are explicitly synthetic; no remote calls or teacher action.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest
from math_agent.web.app import create_app
from test_automatic_recheck_api import payload, publish_synthetic
from test_teaching_quality_gate import TeachingProvider, teaching_setup

pytestmark = pytest.mark.unit


class ExplicitFeedbackProvider(TeachingProvider):
    def __init__(self, incomplete=False):
        super().__init__(problem=False)
        self.feedback_contexts = []
        self.incomplete = incomplete

    def generate(self, role, context, schema):
        if role != 'reviewer_feedback':
            return super().generate(role, context, schema)
        self.feedback_contexts.append(copy.deepcopy(context))
        items = []
        for index, item in enumerate(context['feedback_items']):
            target = next(unit for unit in context['units'] if unit['id'] == ('S01.U01' if index == 0 else 'S02.U01'))
            missing = index == 1 and '模拟补全' not in target['tex']
            items.append({'id':item['id'], 'status':'supported_improvement' if missing else 'satisfied',
                'reason':'离线控制响应：此项在实际传入正文中仍待补充。' if missing else '离线控制响应：此项在实际传入的当前正文中已满足。',
                'unit_ids':[target['id']], 'repair_unit_ids':[target['id']] if missing else [],
                'unit_evidence':[{'unit_id':target['id'],'quote':target['tex'],'kind':'statement'}],
                'objective_evidence':[{'section_id':context['plan']['sections'][index]['id'],
                    'field':'objectives','quote':context['plan']['sections'][index]['objectives'][0]}],
                'repair_instruction':'请在现有单元内补全已批准的一般参数合法域与边界说明。' if missing else None})
        if self.incomplete:
            items = items[:1]
        return {'items':items,'limitations':['Offline controlled response; not real mathematical or teaching acceptance.']}


@pytest.mark.parametrize('incomplete', [False, True])
def test_actual_feedback_event_reaches_pipeline_and_latest_receipt_endpoint(tmp_path, monkeypatch, incomplete):
    provider = ExplicitFeedbackProvider(incomplete)
    service, pipeline, plan, compiles = teaching_setup(tmp_path, monkeypatch, provider)
    rid = pipeline.run['id']
    initial, _ = pipeline.lecture(plan)
    publish_synthetic(service.store, pipeline.settings, pipeline.job, 'initial-receipt-integration-delivery')
    service.store.finish(pipeline.job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
    before = service.get(rid)
    feedback = '1. 请核查已批准的初值与空和约定。\n2. 请补充已批准的一般参数合法域与边界说明。'
    with TestClient(create_app(pipeline.settings), base_url='http://127.0.0.1:8765') as client:
        client.headers['X-CSRF-Token'] = client.get('/api/session').json()['csrf_token']
        response = client.post(f'/api/runs/{rid}/recheck', json={**payload(plan), 'feedback':feedback, 'feedback_source':'agent_audit'})
        assert response.status_code == 202
        job = service.store.claim('offline-explicit-feedback-worker')
        assert job['id'] == response.json()['id']
        resumed = Pipeline(pipeline.settings, service.store, job)
        resumed.provider = provider
        if incomplete:
            with pytest.raises(AgentError) as error:
                resumed.lecture(plan)
            assert error.value.code == 'FEEDBACK_REVIEW_BLOCKED'
            service.store.finish(job, 'BLOCKED', 'feedback.assessment', {'code':error.value.code,'message':'Synthetic incomplete assessment'})
        else:
            completed, _ = resumed.lecture(plan)
            assert len(provider.repairs) == 1 and provider.repairs[0]['allowed_unit_ids'] == ['S02.U01']
            assert completed[0] == initial[0]
            assert '模拟补全' in completed[1][1]['units'][0]['tex']
            service.store.finish(job, 'AWAITING_USER_REVIEW', 'review.pages_and_quality')
        detail = client.get('/api/runs/'+rid).json()
        receipt = detail['feedback_review']
        assert receipt['job_id'] == job['id'] and receipt['feedback_hash'] == digest(feedback)
        assert receipt['teacher_review'] == 'NOT_RUN'
        assert [item['id'] for item in receipt['items']] == ['F1','F2']
        if incomplete:
            assert receipt['status'] == 'invalid'
            assert all(item['status']=='unresolved' for item in receipt['items'])
            assert provider.repairs == []
        else:
            assert receipt['status'] == 'reviewed'
            assert all(item['status']=='satisfied' for item in receipt['items'])
            assert len(provider.feedback_contexts) == 2
        actual_file = pipeline.settings.workspace / receipt['evidence_key']
        assert digest(actual_file.read_bytes()) == receipt['evidence_sha256']
        history = client.get('/api/runs/'+rid+'/events').json()
        recorded = [event['payload'] for event in history if event['type']=='feedback.reviewed']
        assert recorded and recorded[-1]['identity_hash'] == receipt['identity_hash']
        assert all(value['job_id']==job['id'] and value['plan_hash']==plan['hash'] for value in recorded)
        assert provider.feedback_contexts[0]['feedback_text'] == feedback
        assert provider.feedback_contexts[0]['source_event']['job_id'] == job['id']
        for key in ('approval','plan','input_hash','request_count','reviews'):
            assert detail[key] == before[key], key
        assert detail['reviews']==[]
        assert not any(event['type']=='human.review' for event in history)
