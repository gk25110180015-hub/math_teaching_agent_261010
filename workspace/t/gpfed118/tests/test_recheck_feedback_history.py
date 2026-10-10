"""Feedback audit with real prior global rounds; mock models and compiler only."""
import copy
import json
from functools import partial

import pytest
from fastapi.testclient import TestClient

from math_agent.budget import BudgetIncrease
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError, digest
from math_agent.web.app import create_app
from test_automatic_recheck_api import payload, publish_synthetic
from test_teaching_quality_gate import TeachingProvider, teaching_setup
import test_teaching_quality_gate


pytestmark=pytest.mark.unit


class HistoryFeedbackProvider(TeachingProvider):
    def __init__(self):
        super().__init__(problem=False)
        self.active=None
        self.calls=[]
        self.interrupt_repair_once=False

    def generate(self, role, context, schema):
        self.calls.append((role,copy.deepcopy(context)))
        if self.active:
            self.active.store.count_request(self.active.job,60,
                {'role':role,'fixture':'OFFLINE_MOCK_NO_MODEL_HTTP'})
        if role=='repair_content_unit':
            self.repairs.append(copy.deepcopy(context))
            if self.interrupt_repair_once:
                self.interrupt_repair_once=False
                raise AgentError('PROVIDER_TIMEOUT','Synthetic pending repair interruption')
            result=copy.deepcopy(context['section'])
            target=result['units'][0]
            marker=' 反馈缺口已修订。' if context['issues'][0]['message']=='feedback-gap' else ' 历史缺口修订。'
            target['tex']+=marker
            return result
        result=super().generate(role,context,schema)
        if role=='reviewer_math' and context['scope']['kind']=='chapter_coverage':
            target=next(u for u in context['units'] if u['id']=='S02.U01')
            message=None
            if target['tex'].count('历史缺口修订。')<2:
                message='historical-gap'
            elif context.get('recheck_feedback') and '反馈缺口已修订。' not in target['tex']:
                message='feedback-gap'
            result['issues']=[] if message is None else [{'unit_id':'S02.U01','severity':'review',
                'message':message,'evidence':'Synthetic judgment after reading supplied actual body.'}]
        return result


def history_fixture(tmp_path,monkeypatch,limit=6):
    provider=HistoryFeedbackProvider()
    # Higher effective budgets are obtained through a real block/increase/retry;
    # startup Settings intentionally caps the default at two global rounds.
    monkeypatch.setattr(test_teaching_quality_gate,'Settings',
        partial(test_teaching_quality_gate.Settings,max_global_repair_rounds=1 if limit>2 else limit))
    service,pipeline,plan,compiles=teaching_setup(tmp_path,monkeypatch,provider)
    provider.active=pipeline
    if limit>2:
        with pytest.raises(AgentError) as caught:
            pipeline.lecture(plan)
        assert caught.value.code=='BUDGET_EXHAUSTED'
        service.store.finish(pipeline.job,'BLOCKED','math.global_interfaces',{'code':'BUDGET_EXHAUSTED'})
        increase(service,pipeline,plan)
        service.retry(pipeline.run['id'])
        pipeline=Pipeline(pipeline.settings,service.store,service.store.claim('history-initial-budget-resume'))
        pipeline.provider=provider;provider.active=pipeline
    pipeline.lecture(plan)
    state=json.loads((pipeline.root/'global-repair-state.json').read_bytes())
    assert state['phase']=='validated' and state['rounds_used']==2
    assert len(provider.repairs)==2
    publish_synthetic(service.store,pipeline.settings,pipeline.job,'history-initial-delivery')
    service.store.finish(pipeline.job,'AWAITING_USER_REVIEW','review.pages_and_quality')
    return service,pipeline,plan,provider,compiles


def increase(service,pipeline,plan):
    service.increase_budget(pipeline.run['id'],BudgetIncrease(
        expected_version=service.get_budget(pipeline.run['id'])['version'],
        expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],
        action_id='history-explicit-global-increase',global_repair_rounds=6,
        note='Offline explicit budget increase preserving the existing two rounds.'))


def client_for(pipeline):
    client=TestClient(create_app(pipeline.settings),base_url='http://127.0.0.1:8765')
    client.headers['X-CSRF-Token']=client.get('/api/session').json()['csrf_token']
    return client


def recheck(client,service,pipeline,plan,provider,key,feedback):
    response=client.post(f'/api/runs/{pipeline.run["id"]}/recheck',json={**payload(plan,key),
        'feedback':feedback,'feedback_source':'agent_audit'})
    assert response.status_code==202,response.text
    claimed=service.store.claim('history-feedback-worker')
    assert claimed['id']==response.json()['id'] and claimed['id']!=pipeline.job['id']
    resumed=Pipeline(pipeline.settings,service.store,claimed)
    resumed.provider=provider;provider.active=resumed
    return resumed


@pytest.mark.parametrize('withdrawn',['',' \n\t '])
def test_two_validated_rounds_formal_recheck_reviews_new_feedback_then_latest_empty(tmp_path,monkeypatch,withdrawn):
    service,pipeline,plan,provider,_=history_fixture(tmp_path,monkeypatch)
    before=service.get(pipeline.run['id'])
    old_failure=(pipeline.root/'global_review_failure.json').read_bytes()
    old_history={p:digest(p.read_bytes()) for p in (pipeline.root/'global-repairs').rglob('*-candidate.json')}
    with client_for(pipeline) as client:
        start=len(provider.calls)
        resumed=recheck(client,service,pipeline,plan,provider,'history-feedback-1','请核查本轮新增观察。')
        completed,reports=resumed.lecture(plan)
        state=json.loads((pipeline.root/'global-repair-state.json').read_bytes())
        assert state['rounds_used']==3 and state['phase']=='validated'
        whole=[ctx for role,ctx in provider.calls[start:] if role=='reviewer_math' and ctx['scope']['kind']=='chapter_coverage']
        assert len(whole)==2 and all(c['recheck_feedback']['feedback']=='请核查本轮新增观察。' for c in whole)
        assert '反馈缺口已修订。' not in whole[0]['units'][1]['tex']
        assert '反馈缺口已修订。' in whole[1]['units'][1]['tex']
        assert all(c['recheck_feedback']['source_event']['job_id']==resumed.job['id'] for c in whole)
        assert provider.writes==['S01','S02'] and len(provider.repairs)==3
        assert all(digest(p.read_bytes())==value for p,value in old_history.items())
        assert any(p.read_bytes()==old_failure for p in (pipeline.root/'global-repairs/failures').glob('*.json'))
        coverage=next(item['chapter_coverage'] for item in reports if 'chapter_coverage' in item)
        evidence=resumed.settings.workspace/coverage['recheck_feedback_evidence']['storage_key']
        assert json.loads(evidence.read_bytes())['unit_hashes']=={u['id']:digest(u) for _,s in completed for u in s['units']}
        service.store.finish(resumed.job,'AWAITING_USER_REVIEW','review.pages_and_quality')
        start=len(provider.calls)
        empty=recheck(client,service,resumed,plan,provider,'history-feedback-withdraw',withdrawn)
        result,empty_reports=empty.lecture(plan)
        fresh=[ctx for role,ctx in provider.calls[start:] if role=='reviewer_math' and ctx['scope']['kind']=='chapter_coverage']
        assert len(fresh)==1 and 'recheck_feedback' not in fresh[0]
        assert result==completed and len(provider.repairs)==3
        assert not any('recheck_feedback_evidence' in r.get('chapter_coverage',{}) for r in empty_reports)
        assert json.loads((empty.root/'global-repair-state.json').read_bytes())['rounds_used']==3
        final=service.get(pipeline.run['id'])
        assert final['approval']==before['approval'] and final['reviews']==[]
        assert final['request_count']==len(provider.calls)>before['request_count']


def test_feedback_pending_round_retry_keeps_job_and_reviews_repaired_body(tmp_path,monkeypatch):
    service,pipeline,plan,provider,_=history_fixture(tmp_path,monkeypatch)
    approved=copy.deepcopy(service.get(pipeline.run['id'])['approval'])
    with client_for(pipeline) as client:
        resumed=recheck(client,service,pipeline,plan,provider,'history-feedback-pending','本轮观察请核查。')
        provider.interrupt_repair_once=True
        with pytest.raises(AgentError,match='pending repair interruption'):
            resumed.lecture(plan)
        state=json.loads((resumed.root/'global-repair-state.json').read_bytes())
        assert state['phase']=='repair_pending' and state['rounds_used']==3
        assert state['pending'][0]['issues'][0]['message']=='feedback-gap'
        service.store.finish(resumed.job,'FAILED','repair.global.S02',{'code':'PROVIDER_TIMEOUT'})
        rejected=client.post(f'/api/runs/{pipeline.run["id"]}/recheck',json={**payload(plan,'illegal-withdraw-pending'),
            'feedback':'','feedback_source':'agent_audit'})
        assert rejected.status_code==409 and rejected.json()['error']['code']=='NOT_RECHECKABLE'
        old_requests=service.get(pipeline.run['id'])['request_count']
        start=len(provider.calls)
        service.retry(pipeline.run['id'])
        retried=Pipeline(pipeline.settings,service.store,service.store.claim('history-pending-retry'))
        retried.provider=provider;provider.active=retried
        assert retried.job['id']==resumed.job['id']
        completed,_=retried.lecture(plan)
        assert provider.calls[start][0]=='repair_content_unit'
        whole=[ctx for role,ctx in provider.calls[start:] if role=='reviewer_math' and ctx['scope']['kind']=='chapter_coverage']
        assert len(whole)==1 and whole[0]['recheck_feedback']['feedback']=='本轮观察请核查。'
        assert whole[0]['recheck_feedback']['source_event']['job_id']==retried.job['id']
        assert whole[0]['units']==[u for _,s in completed for u in s['units']]
        final_state=json.loads((retried.root/'global-repair-state.json').read_bytes())
        assert final_state['rounds_used']==3 and final_state['phase']=='validated'
        assert service.get(pipeline.run['id'])['request_count']>old_requests
        assert service.get(pipeline.run['id'])['approval']==approved
        assert service.get(pipeline.run['id'])['reviews']==[]


def test_exhausted_old_rounds_review_feedback_then_block_and_explicitly_resume(tmp_path,monkeypatch):
    service,pipeline,plan,provider,_=history_fixture(tmp_path,monkeypatch,limit=2)
    with client_for(pipeline) as client:
        start=len(provider.calls)
        resumed=recheck(client,service,pipeline,plan,provider,'history-feedback-no-budget','请核查新观察并保留旧轮次。')
        with pytest.raises(AgentError) as caught:
            resumed.lecture(plan)
        assert caught.value.code=='BUDGET_EXHAUSTED'
        whole=[ctx for role,ctx in provider.calls[start:] if role=='reviewer_math' and ctx['scope']['kind']=='chapter_coverage']
        assert len(whole)==1 and whole[0]['recheck_feedback']['feedback']=='请核查新观察并保留旧轮次。'
        state=json.loads((resumed.root/'global-repair-state.json').read_bytes())
        assert state['rounds_used']==2 and state['phase']=='budget_exhausted'
        assert len(provider.repairs)==2
        failure=json.loads((resumed.root/'global_review_failure.json').read_bytes())
        assert failure['issues'][0]['message']=='feedback-gap' and failure['rounds_used']==2
        service.store.finish(resumed.job,'BLOCKED','math.global_interfaces',{'code':'BUDGET_EXHAUSTED'})
        increase(service,resumed,plan)
        service.retry(resumed.run['id'])
        retry=Pipeline(resumed.settings,service.store,service.store.claim('history-budget-retry'))
        retry.provider=provider;provider.active=retry
        start=len(provider.calls)
        retry.lecture(plan)
        assert provider.calls[start][0]=='repair_content_unit'
        assert provider.calls[start][1]['issues']==failure['issues']
        whole=[ctx for role,ctx in provider.calls[start:] if role=='reviewer_math' and ctx['scope']['kind']=='chapter_coverage']
        assert len(whole)==1 and whole[0]['recheck_feedback']['source_event']['job_id']==resumed.job['id']
        after=json.loads((retry.root/'global-repair-state.json').read_bytes())
        assert after['rounds_used']==3 and after['phase']=='validated'
        assert provider.writes==['S01','S02'] and len(provider.repairs)==3
