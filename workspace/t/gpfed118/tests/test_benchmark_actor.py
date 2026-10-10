import json
import pytest
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.worker import Worker
from math_agent.domain import NewRun,DecisionsRequest,ConfirmRequest,ReviewRequest
from math_agent.util import AgentError

def test_benchmark_approval_is_attributed_and_cannot_claim_teacher_review(tmp_path):
    settings=Settings(workspace=tmp_path)
    service=Service(settings,actor='benchmark_driver')
    run=service.create(NewRun(workflow_id='lecture.generate',topic='数列极限',trusted_input=True))
    rid=run['id'];service.propose(rid);Worker(settings).tick();plan=service.store.get_run(rid)['plan']
    choices=[{'question_id':q['id'],'question_revision':q['revision'],'selected_option_ids':[q['options'][0]['id']]} for q in plan['questions']]
    plan=service.decisions(rid,DecisionsRequest(expected_plan_revision=plan['revision'],decisions=choices))
    assert all(d['actor']=='benchmark_driver' for d in plan['decisions'])
    service.confirm(rid,ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='user-authorized-benchmark'))
    with service.store.connect() as c:
        event=json.loads(c.execute("SELECT payload_json FROM events WHERE run_id=? AND type='plan.confirmed'",(rid,)).fetchone()[0])
    assert event['actor']=='benchmark_driver'
    with pytest.raises(AgentError) as exc:
        service.review(rid,ReviewRequest(artifact_id='anything',sha256='anything',verdict='pass'))
    assert exc.value.code=='HUMAN_REVIEW_REQUIRED'

def test_unknown_internal_actor_rejected(tmp_path):
    with pytest.raises(ValueError):Service(Settings(workspace=tmp_path),actor='model')
