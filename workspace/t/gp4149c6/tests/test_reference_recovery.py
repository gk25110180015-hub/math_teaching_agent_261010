"""Actual captured CH01 body, synthetic mapping/review, and separately marked XeLaTeX."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.reference_recovery import apply_label_proposal
from math_agent.util import AgentError,digest


def fixture():
    section=json.loads((Path(__file__).parent/'fixtures/live_ch01_missing_labels.json').read_text(encoding='utf-8'))
    spec={'id':'S01','title':'数列与极限定义','objectives':['理解数列、epsilon-N定义与唯一性'],
        'required_kinds':['definition','theorem','proof','example','solution','exercise'],'prerequisites':[],
        'reference_labels':['def:sequence','def:sequence-limit','def:epsilon-N','thm:limit-unique']}
    plan={'title':'Captured missing-label fixture','provider':'mock','sections':[spec],
        'lecture':{'exercises':'with_answers','proof_policy':'all','answers_location':'end'}}
    bindings=[{'label':label,'unit_id':section['units'][index]['id'],
        'quote':section['units'][index]['tex'],'rationale':'该引文给出此标签对应的正面定义及其条件。'}
        for label,index in [('def:sequence',0),('def:sequence-limit',1),('def:epsilon-N',1)]]
    return spec,section,plan,{'bindings':bindings,'unresolved_labels':[]}


def test_exact_recovery_allows_two_labels_on_same_definition_without_changing_math():
    spec,section,plan,proposal=fixture();original=copy.deepcopy(section)
    fixed,evidence=apply_label_proposal(spec,section,plan,proposal)
    assert fixed['units'][0]['tex']==r'\label{def:sequence}'+section['units'][0]['tex']
    assert fixed['units'][1]['tex']==r'\label{def:sequence-limit}\label{def:epsilon-N}'+section['units'][1]['tex']
    assert fixed['units'][2:]==section['units'][2:]
    for field in ('calculations','calculation_limitations','uncertainties'):assert fixed[field]==section[field]
    assert section==original and evidence['status']=='INSERTED_PENDING_RECHECK'
    assert evidence['teacher_visual_review']=='NOT_RUN'


@pytest.mark.parametrize('fault',['unknown_unit','wrong_kind','invented_quote','duplicate_label','missing_binding','extra_label','equation_label','comment_quote','ambiguous_quote','abstain'])
def test_unsafe_mapping_is_blocked_without_mutating_original(fault):
    spec,section,plan,proposal=fixture();original=copy.deepcopy(section)
    if fault=='unknown_unit':proposal['bindings'][0]['unit_id']='S99.U01'
    elif fault=='wrong_kind':proposal['bindings'][0]['unit_id']='S01.U05'
    elif fault=='invented_quote':proposal['bindings'][0]['quote']='This invented content does not occur anywhere'
    elif fault=='duplicate_label':proposal['bindings'].append(proposal['bindings'][0])
    elif fault=='missing_binding':proposal['bindings'].pop()
    elif fault=='extra_label':proposal['bindings'][0]['label']='def:unapproved'
    elif fault=='equation_label':
        spec['reference_labels'][0]='eq:unapproved';proposal['bindings'][0]['label']='eq:unapproved'
    elif fault=='comment_quote':
        section['units'][0]['tex']='% '+proposal['bindings'][0]['quote']+'\n正文不含完整引文。'
    elif fault=='ambiguous_quote':section['units'][2]['tex']=proposal['bindings'][0]['quote']
    else:
        removed=proposal['bindings'].pop();proposal['unresolved_labels']=[removed['label']]
    original=copy.deepcopy(section)
    with pytest.raises(AgentError):apply_label_proposal(spec,section,plan,proposal)
    assert section==original


def setup_recovery(tmp_path,monkeypatch,fail_after=False,bad_semantics=False,limit=1):
    from math_agent.domain import NewRun,ConfirmRequest,ExecuteRequest
    from math_agent.pipeline import Pipeline
    from math_agent.service import Service
    from math_agent.settings import Settings
    spec,section,_,proposal=fixture()
    class Provider:
        def __init__(self):self.writes=0;self.maps=0;self.reviews=0;self.fail=fail_after
        def generate(self,role,context,schema):
            if role=='writer_lecture_section':self.writes+=1;return copy.deepcopy(section)
            if role=='propose_reference_labels':
                self.maps+=1;value=copy.deepcopy(proposal)
                if bad_semantics:
                    for binding in value['bindings'][1:]:
                        binding.update(unit_id='S01.U03',quote=section['units'][2]['tex'])
                return value
            assert role=='reviewer_math'
            if context.get('scope',{}).get('kind')=='chapter_coverage':
                return {'issues':[],'checked_unit_ids':[u['id'] for u in context['units']],
                        'limitations':['Neutral chapter fixture; reference recovery counters are local only.']}
            self.reviews+=1
            evidence=context.get('reference_recovery')
            if evidence and self.fail:
                self.fail=False;raise AgentError('PROVIDER_TIMEOUT','Synthetic post-insertion review timeout')
            issues=[]
            if evidence and bad_semantics:issues=[{'unit_id':'S01.U03','severity':'review',
                'message':'否定形式不是正面收敛定义，标签定位不当','evidence':'mapping quote targets the negation'}]
            return {'issues':issues,'checked_unit_ids':[u['id'] for u in context['units']],'limitations':['Synthetic reviewer, not mathematical acceptance.']}
    provider=Provider();settings=Settings(workspace=tmp_path/'w',reference_root=tmp_path/'refs',max_local_repair_attempts=limit)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='Captured synthetic label recovery',trusted_input=True))
    plan=fixture()[2]
    plan.update(difficulty='synthetic',theme='default',questions=[],unresolved_blocking_questions=[],decisions=[],decision_ids=[])
    with service.store.transaction() as c:service.store.save_plan(c,run['id'],plan)
    plan=service.store.get_run(run['id'])['plan']
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='offline-label-test'))
    service.execute(run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='offline-label-test'))
    p=Pipeline(settings,service.store,service.store.claim('offline-label-worker'));p.provider=provider
    compiles=[]
    def compile(self,source,entry,build):
        compiles.append((source/entry).read_bytes());build.mkdir()
        return {'status':'PASS','issues':[],'passes':2,'page_count':1,'pdf_path':None,'fixture':'OFFLINE_FAKE_COMPILER'}
    monkeypatch.setattr(Pipeline,'compile',compile)
    return service,p,plan,provider,compiles


def test_pipeline_recovers_labels_then_repeats_checks_and_retains_raw_candidate(tmp_path,monkeypatch):
    service,p,plan,provider,compiles=setup_recovery(tmp_path,monkeypatch)
    approval=service.store.get_run(p.run['id'])['approval']
    completed,reports=p.lecture(plan)
    assert provider.writes==1 and provider.maps==1 and provider.reviews==2
    assert len(compiles)==1 and reports[0]['references']['status']=='PASS'
    draft=next(p.build_root.glob('sS01*'))
    assert json.loads((draft/'candidate.json').read_bytes())==fixture()[1]
    assert (draft/'review-0.json').exists() and (draft/'label-repair-1-evidence.json').exists()
    assert service.store.get_run(p.run['id'])['approval']==approval
    assert service.store.get_run(p.run['id'])['reviews']==[]
    assert completed[0][1]['units'][2]==fixture()[1]['units'][2]


def test_valid_mapping_survives_transient_review_failure_without_reproposal(tmp_path,monkeypatch):
    _,p,plan,provider,compiles=setup_recovery(tmp_path,monkeypatch,fail_after=True)
    with pytest.raises(AgentError,match='post-insertion'):p.lecture(plan)
    assert provider.maps==1 and not compiles
    p.lecture(plan)
    assert provider.writes==1 and provider.maps==1 and provider.reviews==3 and len(compiles)==1
    assert any(json.loads(f.read_bytes())['status']=='UNCHECKED_REPAIRED' for f in p.build_root.glob('sS01*/local-recovery.json'))


def test_semantically_bad_grounded_mapping_cannot_bypass_next_reviewer(tmp_path,monkeypatch):
    _,p,plan,provider,compiles=setup_recovery(tmp_path,monkeypatch,bad_semantics=True)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='MATH_REVIEW_BLOCKED' and not compiles
    assert provider.maps==1 and provider.reviews==2


def test_zero_budget_does_not_request_label_proposal(tmp_path,monkeypatch):
    _,p,plan,provider,compiles=setup_recovery(tmp_path,monkeypatch,limit=0)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='BUDGET_EXHAUSTED' and provider.maps==0 and not compiles


def test_corrupt_cached_mapping_blocks_without_replacing_evidence(tmp_path,monkeypatch):
    _,p,plan,provider,_=setup_recovery(tmp_path,monkeypatch,fail_after=True)
    with pytest.raises(AgentError):p.lecture(plan)
    path=next((p.root/'label-recovery').rglob('proposal.json'))
    path.write_bytes(b'{}')
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='LABEL_RECOVERY_CACHE_INVALID' and provider.maps==1
    assert path.read_bytes()==b'{}'


@pytest.mark.windows_compile
def test_actual_captured_section_labels_resolve_to_correct_numbered_definitions(tmp_path):
    from math_agent.compiler import TexCompiler
    from math_agent.pipeline import render_lecture
    spec,section,plan,proposal=fixture();fixed,_=apply_label_proposal(spec,section,plan,proposal)
    fixed['units'].append({'id':'S01.TESTREF','kind':'explanation','relates_to':None,
        'tex':r'数列定义\ref{def:sequence}，极限定义\ref{def:sequence-limit}与\ref{def:epsilon-N}，唯一性\ref{thm:limit-unique}。'})
    source=tmp_path/'source';source.mkdir()
    (source/'lecture.tex').write_bytes(render_lecture(plan['title'],[(spec,fixed)],plan).encode('utf-8'))
    result=TexCompiler().compile(source,'lecture.tex',tmp_path/'build',trusted=True)
    assert result['status']=='PASS',result
    aux=(tmp_path/'build/lecture.aux').read_text(encoding='utf-8')
    assert r'\newlabel{def:sequence}{{1.1}' in aux
    assert r'\newlabel{def:sequence-limit}{{1.2}' in aux and r'\newlabel{def:epsilon-N}{{1.2}' in aux
    assert r'\newlabel{thm:limit-unique}{{1.4}' in aux
