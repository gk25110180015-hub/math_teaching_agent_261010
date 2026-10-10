"""Registered forward references are pending locally, never waived globally."""
import json
import pytest
from math_agent.crossrefs import inspect_section_references, local_reference_gate, reference_registry
from math_agent.util import AgentError


def test_only_registered_future_references_can_be_pending():
    result={'status':'FAIL','page_count':1,'passes':2,'issues':[
        {'rule_id':'UNRESOLVED_REFERENCE','severity':'blocking','message':"LaTeX Warning: Reference `thm:later' on page 1 undefined on input line 8."},
        {'rule_id':'UNRESOLVED_REFERENCE','severity':'blocking','message':'LaTeX Warning: There were undefined references.'}]}
    assert local_reference_gate(result,{'thm:later'})['status']=='PENDING_FULL_REFERENCE_CHECK'
    assert local_reference_gate(result,set())['status']=='FAIL'
    result['issues'].insert(0,{'rule_id':'UNRESOLVED_REFERENCE','severity':'blocking','message':"LaTeX Warning: Citation `MissingBook' undefined."})
    assert local_reference_gate(result,{'thm:later'})['status']=='FAIL'
    assert result['status']=='FAIL'  # Compiler truth must remain unchanged.


def test_registration_rejects_duplicate_labels():
    plan={'sections':[{'id':'S01','reference_labels':['thm:one']},{'id':'S02','reference_labels':['thm:one']}]}
    with pytest.raises(AgentError):reference_registry(plan)


def test_missing_promised_label_and_unplanned_reference_are_blocked():
    spec={'id':'S02','reference_labels':['thm:later']}
    plan={'sections':[{'id':'S01'},spec]}
    generated={'units':[{'tex':r'未知引用\ref{made-up}，不能冒称将来会补。'}]}
    result=inspect_section_references(spec,generated,[],plan)
    assert {i['rule_id'] for i in result['issues']}=={'PLANNED_LABEL_MISSING','UNREGISTERED_REFERENCE'}


@pytest.mark.windows_compile
@pytest.mark.integration
def test_T21_registered_forward_and_prior_references_full_workflow(tmp_path,monkeypatch):
    from math_agent import pipeline
    from math_agent.provider import MockProvider
    from math_agent.service import Service
    from math_agent.worker import Worker
    from math_agent.settings import Settings
    from math_agent.domain import NewRun,DecisionsRequest,ConfirmRequest,ExecuteRequest
    class CrossReferenceMock(MockProvider):
        def generate(self,role,context,schema):
            value=super().generate(role,context,schema)
            if role=='planner_lecture':value['sections'][1]['reference_labels']=['thm:later']
            if role=='writer_lecture_section':
                if value['section_id']=='S01':
                    value['units'].append({'id':'S01.XREF','kind':'explanation','tex':r'第\ref{sec:S02}节的定理\ref{thm:later}将给出加法法则。','relates_to':None})
                else:
                    value['units'][1]['tex']=r'\label{thm:later}'+value['units'][1]['tex']
                    value['units'].append({'id':'S02.XREF','kind':'explanation','tex':r'先修定义见第\ref{sec:S01}节。','relates_to':None})
            return value
    monkeypatch.setattr(pipeline,'MockProvider',CrossReferenceMock)
    settings=Settings(workspace=tmp_path)
    service=Service(settings);worker=Worker(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='数列极限',trusted_input=True));rid=run['id']
    service.propose(rid);worker.tick();plan=service.store.get_run(rid)['plan']
    choices=[{'question_id':q['id'],'question_revision':q['revision'],'selected_option_ids':[q['options'][0]['id']]} for q in plan['questions']]
    plan=service.decisions(rid,DecisionsRequest(expected_plan_revision=plan['revision'],decisions=choices))
    service.confirm(rid,ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='xref-test'))
    service.execute(rid,ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='xref-test'))
    worker.tick();run=service.store.get_run(rid)
    assert run['status']=='AWAITING_USER_REVIEW',run.get('error')
    with service.store.connect() as c:
        checkpoints=[json.loads(x[0]) for x in c.execute('SELECT output_json FROM steps WHERE run_id=?',(rid,))]
    first=next(x for x in checkpoints if x['generated']['section_id']=='S01')
    assert first['report']['compile']['status']=='FAIL'
    assert first['report']['references']['status']=='PENDING_FULL_REFERENCE_CHECK'
    assert set(first['report']['references']['pending_labels'])=={'thm:later','sec:S02'}
    auxes=list(tmp_path.glob('b/*/v*/build/lecture.aux'))
    assert len(auxes)==1
    aux=auxes[0].read_text(encoding='utf-8')
    assert r'\newlabel{thm:later}{{2.2}' in aux
    assert r'\newlabel{sec:S01}{{1}' in aux and r'\newlabel{sec:S02}{{2}' in aux
    assert not run['reviews']  # No teacher approval is fabricated.
