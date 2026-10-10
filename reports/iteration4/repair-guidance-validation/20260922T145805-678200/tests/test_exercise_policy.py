import copy

import pytest

from math_agent.domain import NewRun, ConfirmRequest, DecisionsRequest, ExecuteRequest, Selection
from math_agent.pipeline import Pipeline, question
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError


def planned_service(tmp_path):
    service=Service(Settings(workspace=tmp_path/'workspace'))
    run=service.create(NewRun(workflow_id='lecture.generate',topic='Offline policy fixture',trusted_input=True))
    sections=[{'id':'S01','title':'Example and practice','required_kinds':['definition','theorem','proof','example','solution','exercise'],
               'objectives':['理解极限定义；安排例题和练习。'],'prerequisites':[]},
              {'id':'S02','title':'Practice','required_kinds':['definition','exercise','solution'],
               'objectives':['应用前文定义。'],'prerequisites':['S01']}]
    plan={'title':'Exercise policy','theme':'default','sections':sections,'lecture':{'proof_policy':'key'},
        'questions':[question('Q-EXERCISE','Exercise policy','lecture.exercises',[('WITH','with','with_answers'),('NONE','none','none')])],
        'decisions':[],'decision_ids':[],'unresolved_blocking_questions':['Q-EXERCISE'],'omissions':[],'additions':[]}
    with service.store.transaction() as c: service.store.save_plan(c,run['id'],plan)
    return service,run['id']


def choose(service,rid,option,custom=''):
    plan=service.store.get_run(rid)['plan']
    return service.decisions(rid,DecisionsRequest(expected_plan_revision=plan['revision'],decisions=[Selection(
        question_id='Q-EXERCISE',question_revision=1,selected_option_ids=[option],custom_input=custom)]))


@pytest.mark.unit
def test_none_removes_required_exercises_but_preserves_example_solutions_and_math_objectives(tmp_path):
    service,rid=planned_service(tmp_path)
    before=copy.deepcopy(service.store.get_run(rid)['plan'])
    plan=choose(service,rid,'NONE')
    assert plan['lecture']['exercises']=='none'
    assert plan['sections'][0]['required_kinds']==['definition','theorem','proof','example','solution']
    assert plan['sections'][1]['required_kinds']==['definition']
    assert [s['objectives'] for s in plan['sections']]==[s['objectives'] for s in before['sections']]
    assert any(d['field']=='sections' for d in plan['diff'])
    assert plan['decisions'][-1]['derived_section_requirements'][0]['section_id']=='S01'
    # Same existing content validator must no longer demand an excluded exercise.
    data={'section_id':'S01','units':[{'id':'D','kind':'definition','tex':'Definition.'},
        {'id':'T','kind':'theorem','tex':'Theorem.'},{'id':'P','kind':'proof','tex':'Proof.','relates_to':'T'},
        {'id':'E','kind':'example','tex':'Example.'},{'id':'A','kind':'solution','tex':'Solution.','relates_to':'E'}]}
    assert Pipeline.validate_written(None,plan['sections'][0],data,plan)==[]


@pytest.mark.unit
def test_with_answers_after_none_restores_required_exercises_and_answers_without_duplicates(tmp_path):
    service,rid=planned_service(tmp_path)
    choose(service,rid,'NONE')
    plan=choose(service,rid,'WITH')
    for section in plan['sections']:
        assert section['required_kinds'].count('exercise')==1
        assert section['required_kinds'].count('solution')==1
    repeated=choose(service,rid,'WITH')
    assert [s['required_kinds'] for s in repeated['sections']]==[s['required_kinds'] for s in plan['sections']]


@pytest.mark.unit
def test_policy_revision_invalidates_old_confirmation_and_preserves_prior_plan(tmp_path):
    service,rid=planned_service(tmp_path)
    old=choose(service,rid,'WITH')
    service.confirm(rid,ConfirmRequest(expected_plan_revision=old['revision'],expected_plan_hash=old['hash'],action_id='offline-plan-confirmation'))
    new=choose(service,rid,'NONE')
    assert new['revision']==old['revision']+1 and new['hash']!=old['hash']
    assert service.store.get_run(rid)['approval'] is None
    with pytest.raises(AgentError) as stale:
        service.execute(rid,ExecuteRequest(expected_plan_revision=old['revision'],expected_plan_hash=old['hash'],idempotency_key='old'))
    assert stale.value.code=='REVISION_CONFLICT'
    with pytest.raises(AgentError) as unapproved:
        service.execute(rid,ExecuteRequest(expected_plan_revision=new['revision'],expected_plan_hash=new['hash'],idempotency_key='new'))
    assert unapproved.value.code=='APPROVAL_REQUIRED'
    import json
    with service.store.connect() as c:
        prior=json.loads(c.execute('SELECT canonical_json FROM plans WHERE run_id=? AND revision=?',(rid,old['revision'])).fetchone()[0])
    assert all('exercise' in s['required_kinds'] for s in prior['sections'])


@pytest.mark.unit
def test_custom_exercise_policy_is_not_guessed_or_used_to_delete_existing_requirements(tmp_path):
    service,rid=planned_service(tmp_path)
    old=service.store.get_run(rid)['plan']
    plan=choose(service,rid,'CUSTOM','每章末尾安排综合练习，具体范围需要教师复核。')
    assert plan['sections']==old['sections']
    assert plan['lecture']['exercises']=={'custom':'每章末尾安排综合练习，具体范围需要教师复核。'}
