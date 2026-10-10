"""Offline global-repair lifecycle using actual SQLite and synthetic providers/compiler."""
import copy
import json

import pytest

from math_agent.domain import NewRun,ConfirmRequest,ExecuteRequest
from math_agent.pipeline import Pipeline
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import AgentError


@pytest.mark.unit
@pytest.mark.parametrize('invalid',['none','unknown_unit','changed_hash','source_hash','checkpoint_hash'])
def test_legacy_failure_is_repaired_before_any_new_global_review(tmp_path,monkeypatch,invalid):
    from math_agent.util import write_json,digest
    provider=GlobalRepairProvider();_,p,plan,_=setup(tmp_path,provider,monkeypatch)
    completed,_=p._lecture_sections(plan)
    with p.store.transaction() as c:
        c.execute('UPDATE steps SET input_hash=? WHERE run_id=?',('old-normalizer-version',p.run['id']))
        if invalid=='checkpoint_hash':c.execute('UPDATE steps SET output_hash=? WHERE run_id=?',('corrupt',p.run['id']))
    if invalid=='source_hash':next(p.build_root.glob('sS01*/source/lecture.tex')).write_bytes(b'changed source')
    issue={'unit_id':'S01.U01','severity':'review','message':'Persisted integer existence concern','evidence':'old review'}
    failure={'issues':[issue],'checked_unit_ids':[u['id'] for _,s in completed for u in s['units']]}
    if invalid=='unknown_unit':issue['unit_id']='OTHER.U01'
    if invalid=='changed_hash':failure['unit_hashes']={'S01.U01':digest('different old unit')}
    write_json(p.root/'global_review_failure.json',failure)
    original=(p.root/'global_review_failure.json').read_bytes()
    original_generate=provider.generate
    def generate(role,context,schema):
        if role=='reviewer_math' and context['scope']['kind']=='adjacent_interface':
            assert provider.repairs, 'Persisted issue must be repaired before another reviewer roll'
        return original_generate(role,context,schema)
    provider.generate=generate
    if invalid!='none':
        with pytest.raises(AgentError) as error:p.lecture(plan)
        assert error.value.code=='GLOBAL_REPAIR_LEGACY_UNVERIFIED'
        assert not provider.repairs and not provider.global_calls
    else:
        sections,_=p.lecture(plan)
        assert len(provider.repairs)==1 and provider.global_calls==1
        assert provider.writes==['S01','S02'] and provider.locals==['S01','S02','S01','S02']
        assert '阿基米德' in sections[0][1]['units'][0]['tex']
        evidence=json.loads((p.root/'global-repairs/legacy-failure-import.json').read_text(encoding='utf-8'))
        assert evidence['source_hash']==digest(original)
        assert evidence['body_hashes_available'] is False
    assert (p.root/'global_review_failure.json').read_bytes()==original


@pytest.mark.unit
def test_legacy_failure_respects_zero_global_repair_budget(tmp_path,monkeypatch):
    from math_agent.util import write_json
    provider=GlobalRepairProvider();_,p,plan,_=setup(tmp_path,provider,monkeypatch,limit=0)
    p._lecture_sections(plan)
    write_json(p.root/'global_review_failure.json',{'issues':[{'unit_id':'S01.U01',
        'severity':'review','message':'Unresolved premise','evidence':'old review'}]})
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='BUDGET_EXHAUSTED'
    assert not provider.repairs and not provider.global_calls
    state=json.loads((p.root/'global-repair-state.json').read_text(encoding='utf-8'))
    assert state['rounds_used']==0 and state['phase']=='budget_exhausted'


@pytest.mark.unit
def test_legacy_nontarget_equation_is_normalized_before_scoped_repair(tmp_path,monkeypatch):
    from math_agent.pipeline import render_lecture
    from math_agent.util import write_json,within,digest
    provider=GlobalRepairProvider();_,p,plan,_=setup(tmp_path,provider,monkeypatch)
    p._lecture_sections(plan)
    with p.store.connect() as c:
        row=c.execute('SELECT * FROM steps WHERE run_id=? AND step_key=?',(p.run['id'],'section.S01')).fetchone()
    old=json.loads(row['output_json'])
    old['generated']['units'][1]['tex']=r'\[1=1\label{eq:old-unchecked}\]'
    source=within(p.settings.workspace,old['source_key'])
    source.write_bytes(render_lecture(plan['title'],[(plan['sections'][0],old['generated'])],plan).encode('utf-8'))
    old['source_hash']=digest(source.read_bytes())
    p.store.checkpoint(p.job,'section.S01','legacy-version',old)
    write_json(p.root/'global_review_failure.json',{'issues':[{'unit_id':'S01.U01',
        'severity':'review','message':'Unresolved premise','evidence':'old review'}]})
    completed,_=p.lecture(plan)
    assert provider.repairs[0]['allowed_unit_ids']==['S01.U01']
    assert provider.repairs[0]['section']['units'][1]['tex']==completed[0][1]['units'][1]['tex']
    assert r'\begin{equation}' in completed[0][1]['units'][1]['tex']
    assert len(provider.repairs)==1 and provider.writes==['S01','S02']
    evidence=json.loads((p.root/'global-repairs/legacy-failure-import.json').read_text(encoding='utf-8'))
    s01=evidence['checkpoint_evidence'][0]
    assert within(p.settings.workspace,s01['raw_seed_key']).is_file()
    assert s01['generated_hash']!=s01['normalized_seed_hash']


class GlobalRepairProvider:
    def __init__(self,mode='fix',fail_following_once=False):
        self.mode=mode;self.fail_following_once=fail_following_once
        self.writes=[];self.locals=[];self.global_calls=0;self.repairs=[]

    def generate(self,role,context,schema):
        if role=='writer_lecture_section':
            sid=context['section']['id'];self.writes.append(sid)
            calculations=([{'id':'C1','unit_id':sid+'.U02','kind':'equivalence','assumptions':{},
                'lhs':{'op':'Integer','value':1},'rhs':{'op':'Integer','value':1}}]
                if self.mode=='drop_other_calculation' else [])
            return {'section_id':sid,'units':[{'id':sid+'.U01','kind':'explanation','tex':'取足够大的正整数 N。','relates_to':None},
                {'id':sid+'.U02','kind':'explanation','tex':'保留本单元所有内容。','relates_to':None}], 'calculations':calculations, 'uncertainties':[]}
        if role=='repair_local_patch':
            self.repairs.append(copy.deepcopy(context))
            result=copy.deepcopy(context['section'])
            if self.mode!='no_progress':result['units'][0]['tex']+=' 正整数无上界（阿基米德性质），因此这样的 N 存在。'
            if self.mode=='mutate_other':result['units'][1]['tex']='Unauthorized changed content'
            if self.mode=='add_unit':result['units'].append({'id':'NEW','kind':'explanation','tex':'Extra','relates_to':None})
            if self.mode=='drop_other_calculation':result['calculations']=[]
            if self.mode=='mutate_uncertainties':result['uncertainties']=['Unrelated metadata changed']
            # Deliberately invalid full-section responses remain rejected, never sanitized.
            if self.mode in ('mutate_other','add_unit','drop_other_calculation','mutate_uncertainties'):
                return result
            return {'section_id':result['section_id'],'replacements':[
                {'unit_id':unit['id'],'tex':unit['tex']} for unit in result['units']
                if unit['id'] in context['allowed_unit_ids']]}
        assert role=='reviewer_math'
        scope=context['scope']
        if scope['kind']=='chapter_coverage':
            # This fixture models an adjacent proof gap only. Whole-chapter
            # coverage outcomes have separate focused tests.
            issues=[]
        elif scope['kind']=='section_local':
            sid=scope['current_section']['id'];self.locals.append(sid)
            if self.fail_following_once and sid=='S02' and self.locals.count('S02')==2:
                self.fail_following_once=False
                raise AgentError('PROVIDER_TIMEOUT','Synthetic following-section review timeout')
            issues=[]
        else:
            self.global_calls+=1
            target=next(u for u in context['units'] if u['id']=='S01.U01')
            issues=[] if '阿基米德' in target['tex'] else [{'unit_id':'S01.U01','severity':'review','message':'补充正整数无上界这一存在性依据。','evidence':'取N而未说明存在基础。'}]
        return {'issues':issues,'checked_unit_ids':[u['id'] for u in context['units']], 'limitations':['Offline fixture; not teacher or formal acceptance.']}


def setup(tmp_path,provider,monkeypatch,limit=2):
    settings=Settings(workspace=tmp_path/'w',reference_root=tmp_path/'refs',max_global_repair_rounds=limit)
    service=Service(settings)
    run=service.create(NewRun(workflow_id='lecture.generate',topic='Offline fixture',trusted_input=True))
    plan={'title':'Global repair','provider':'mock','difficulty':'synthetic','theme':'default',
        'sections':[{'id':sid,'title':sid,'objectives':[],'required_kinds':[],'reference_labels':[],
                     'prerequisites':[] if sid=='S01' else ['S01']} for sid in ('S01','S02')],
        'lecture':{'exercises':'none','proof_policy':'key','answers_location':'end'},'questions':[],
        'unresolved_blocking_questions':[],'decisions':[],'decision_ids':[]}
    with service.store.transaction() as c:service.store.save_plan(c,run['id'],plan)
    plan=service.store.get_run(run['id'])['plan']
    service.confirm(run['id'],ConfirmRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],action_id='offline-test'))
    service.execute(run['id'],ExecuteRequest(expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],idempotency_key='offline-test'))
    job=service.store.claim('offline-worker')
    pipeline=Pipeline(settings,service.store,job);pipeline.provider=provider
    compiles=[]
    def compile(self,source,entry,build):
        build.mkdir();compiles.append(str(source))
        return {'status':'PASS','issues':[],'passes':2,'page_count':1,'pdf_path':None,'fixture':'OFFLINE_FAKE_COMPILER'}
    monkeypatch.setattr(Pipeline,'compile',compile)
    return service,pipeline,plan,compiles


@pytest.mark.unit
def test_global_issue_repairs_only_target_and_rechecks_affected_and_following_sections(tmp_path,monkeypatch):
    provider=GlobalRepairProvider();service,p,plan,compiles=setup(tmp_path,provider,monkeypatch)
    sections,reports=p.lecture(plan)
    assert provider.writes==['S01','S02'] and len(provider.repairs)==1
    assert provider.repairs[0]['allowed_unit_ids']==['S01.U01']
    assert provider.locals==['S01','S02','S01','S02'] and len(compiles)==4
    assert provider.global_calls==2 and '阿基米德' in sections[0][1]['units'][0]['tex']
    assert sections[0][1]['units'][1]['tex']=='保留本单元所有内容。'
    state=json.loads((p.root/'global-repair-state.json').read_text(encoding='utf-8'))
    assert state['rounds_used']==1 and state['phase']=='validated'
    assert service.store.get_run(p.run['id'])['approval']['hash']==plan['hash']
    assert service.store.get_run(p.run['id'])['reviews']==[]
    assert list((p.root/'global-repairs').rglob('*-raw.json'))
    assert list((p.root/'global-repairs').rglob('*-normalization.json'))
    assert (p.root/'global_review_failure.json').exists() # Original detected concern retained.


@pytest.mark.unit
@pytest.mark.parametrize('mode',['mutate_other','add_unit','drop_other_calculation','mutate_uncertainties'])
def test_global_repair_cannot_change_other_units_or_ids(tmp_path,monkeypatch,mode):
    provider=GlobalRepairProvider(mode);_,p,plan,compiles=setup(tmp_path,provider,monkeypatch)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='GLOBAL_REPAIR_SCOPE_VIOLATION'
    assert len(provider.repairs)==1 and len(compiles)==2
    assert list((p.root/'global-repairs').rglob('*-raw.json'))


@pytest.mark.unit
def test_global_round_budget_blocks_unresolved_issue_without_unbounded_recursion(tmp_path,monkeypatch):
    provider=GlobalRepairProvider('no_progress');_,p,plan,_=setup(tmp_path,provider,monkeypatch,limit=2)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='BUDGET_EXHAUSTED'
    assert len(provider.repairs)==2 and provider.global_calls==3
    assert json.loads((p.root/'global-repair-state.json').read_text(encoding='utf-8'))['rounds_used']==2
    with pytest.raises(AgentError):p.lecture(plan)
    assert len(provider.repairs)==2 and provider.global_calls==3


@pytest.mark.unit
def test_repair_is_persisted_before_following_review_timeout_and_resume_reuses_it(tmp_path,monkeypatch):
    provider=GlobalRepairProvider(fail_following_once=True);service,p,plan,compiles=setup(tmp_path,provider,monkeypatch)
    with pytest.raises(AgentError,match='following-section'):p.lecture(plan)
    assert len(provider.repairs)==1
    service.store.finish(p.job,'FAILED','review.section.S02',{'code':'PROVIDER_TIMEOUT'})
    service.retry(p.run['id']);job=service.store.claim('resumed-worker')
    resumed=Pipeline(p.settings,service.store,job);resumed.provider=provider
    sections,_=resumed.lecture(plan)
    assert provider.writes==['S01','S02'] and len(provider.repairs)==1
    assert '阿基米德' in sections[0][1]['units'][0]['tex']
    assert provider.locals.count('S02')==3
    assert service.store.get_run(p.run['id'])['approval']['hash']==plan['hash']


@pytest.mark.unit
def test_corrupt_persisted_global_candidate_fails_before_model_call(tmp_path,monkeypatch):
    provider=GlobalRepairProvider(fail_following_once=True);_,p,plan,_=setup(tmp_path,provider,monkeypatch)
    with pytest.raises(AgentError):p.lecture(plan)
    state=json.loads((p.root/'global-repair-state.json').read_text(encoding='utf-8'))
    path=p.settings.workspace/state['sections']['S01']['candidate_key']
    path.write_text('{}',encoding='utf-8')
    count=len(provider.repairs)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='GLOBAL_REPAIR_CACHE_INVALID'
    assert len(provider.repairs)==count
