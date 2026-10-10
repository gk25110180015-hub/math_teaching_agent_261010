"""Offline strict local-patch recovery, with actual captured failure chains."""
import copy
import json
from pathlib import Path

import pytest

from math_agent.local_patch import apply_local_patch
from math_agent.local_recovery import LocalRecovery
from math_agent.lecture_fragments import normalize_written_section
from math_agent.pipeline import Pipeline
from math_agent.util import AgentError,digest,write_json,within
from test_draft_recovery import setup_pipeline


class Provider:
    def __init__(self,fail_after=False,bad=False,noop=False):
        self.writes=self.patches=self.reviews=0
        self.fail_after=fail_after;self.bad=bad;self.noop=noop;self.contexts=[]

    def generate(self,role,context,schema):
        if role=='writer_lecture_section':
            self.writes+=1
            return {'section_id':'S01','units':[
                {'id':'S01.U1','kind':'definition','tex':'数列是正整数集上的实值函数。','relates_to':None},
                {'id':'S01.U2','kind':'explanation','tex':'本单元原样保留。','relates_to':None}],
                'calculations':[],'calculation_limitations':[],'uncertainties':[]}
        if role=='repair_local_patch':
            self.patches+=1
            assert context['allowed_unit_ids']==['S01.U1']
            value={'section_id':'S01','replacements':[{'unit_id':'S01.U1','tex':context['section']['units'][0]['tex']+('' if self.noop else ' 已明示前提。')}],
                'calculation_updates':[],'calculation_additions':[],'uncertainties_append':[],'calculation_limitations_append':[]}
            if self.bad:
                self.bad=False;value['replacements'].append({'unit_id':'S01.U2','tex':'非法变更。'})
            return value
        assert role=='reviewer_math'
        if context.get('scope',{}).get('kind')=='chapter_coverage':
            return {'issues':[],'checked_unit_ids':[u['id'] for u in context['units']],
                    'limitations':['Neutral chapter fixture; this provider tests local repair.']}
        self.reviews+=1;self.contexts.append(copy.deepcopy(context))
        fixed='已明示前提' in context['units'][0]['tex']
        if fixed and self.fail_after:
            self.fail_after=False;raise AgentError('PROVIDER_TIMEOUT','synthetic repaired-candidate review failure')
        issues=[] if fixed else [{'unit_id':'S01.U1','severity':'review','message':'请明示前提','evidence':'offline synthetic'}]
        return {'issues':issues,'checked_unit_ids':[u['id'] for u in context['units']], 'limitations':['MOCK; not teacher acceptance']}


def setup(tmp_path,monkeypatch,provider,real_compile=False,**settings):
    service,p,plan=setup_pipeline(tmp_path,provider,**settings)
    p.run['input']['provider']='live'  # Injectable fake provider only; no API.
    compiled=[]
    def compile(self,source,entry,build):
        build.mkdir();compiled.append((source/entry).read_bytes())
        return {'status':'PASS','issues':[],'passes':2,'page_count':1,'fixture':'MOCK_COMPILER'}
    if not real_compile:monkeypatch.setattr(Pipeline,'compile',compile)
    return service,p,plan,compiled


def state(p,sid='S01'):
    return json.loads((p.root/'local-repair'/f'{sid}.json').read_bytes())


def test_accepted_patch_is_unchecked_and_reused_after_review_failure(tmp_path,monkeypatch):
    provider=Provider(fail_after=True);service,p,plan,compiled=setup(tmp_path,monkeypatch,provider)
    approval=copy.deepcopy(service.store.get_run(p.run['id'])['approval'])
    with pytest.raises(AgentError,match='repaired-candidate'):p.lecture(plan)
    saved=state(p)
    assert saved['phase']=='UNCHECKED_REPAIRED' and saved['pending_issues']
    assert saved['unit_applied_counts']=={'S01.U1':1} and not compiled
    service.store.finish(p.job,'FAILED','review.section.S01',{'code':'PROVIDER_TIMEOUT'})
    service.retry(p.run['id'])
    resumed=Pipeline(p.settings,service.store,service.store.claim('resume-local-repair'))
    resumed.provider=provider;resumed.run['input']['provider']='live';p=resumed
    completed,_=p.lecture(plan)
    assert provider.writes==provider.patches==1 and provider.reviews==3 and len(compiled)==1
    assert completed[0][1]['units'][1]['tex']=='本单元原样保留。'
    assert state(p)['phase']=='CHECKED'
    assert approval==service.store.get_run(p.run['id'])['approval']
    assert not service.store.get_run(p.run['id'])['reviews']


def test_rejected_patch_is_never_seed_and_retry_retains_same_evidence_doubt(tmp_path,monkeypatch):
    provider=Provider(bad=True);_,p,plan,_=setup(tmp_path,monkeypatch,provider)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='REPAIR_SCOPE_VIOLATION'
    saved=state(p);candidate=json.loads(within(p.settings.workspace,saved['candidate_key']).read_bytes())
    assert '已明示前提' not in candidate['units'][0]['tex']
    assert saved['proposal_calls']==1 and saved['rejected_proposals']==1 and saved['unit_applied_counts']=={}
    assert not list(p.build_root.glob('sS01*/repair-1.json'))
    p.lecture(plan)
    assert provider.writes==1 and provider.patches==2
    assert state(p)['unit_applied_counts']=={'S01.U1':1}
    assert provider.contexts[1]['local_recovery']['unresolved_issues']


def test_noop_proposals_cannot_spin_forever_or_clear_persisted_doubt(tmp_path,monkeypatch):
    provider=Provider(noop=True);_,p,plan,compiled=setup(tmp_path,monkeypatch,provider)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='BUDGET_EXHAUSTED' and not compiled
    saved=state(p)
    assert saved['proposal_calls']==3 and saved['unit_applied_counts']=={} and saved['pending_issues']
    assert provider.patches==3


def test_noop_patch_and_restored_metadata_do_not_justify_review_roulette(tmp_path,monkeypatch):
    provider=Provider(noop=True);original=provider.generate
    def generate(role,context,schema):
        response=original(role,context,schema)
        if role=='reviewer_math' and provider.reviews>1:response['issues']=[]
        return response
    provider.generate=generate
    _,p,plan,compiled=setup(tmp_path,monkeypatch,provider)
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='BUDGET_EXHAUSTED' and not compiled
    assert state(p)['pending_issues'] and state(p)['unit_applied_counts']=={}
    assert provider.patches==3


@pytest.mark.parametrize('damage',['candidate','pointer','proposal'])
def test_corrupted_recovery_evidence_fails_closed(tmp_path,monkeypatch,damage):
    provider=Provider(fail_after=True);_,p,plan,_=setup(tmp_path,monkeypatch,provider)
    with pytest.raises(AgentError):p.lecture(plan)
    saved=state(p)
    path=(p.root/'local-repair/S01.json') if damage=='pointer' else within(p.settings.workspace,
        saved['candidate_key'] if damage=='candidate' else saved['evidence_dependencies'][0]['key'])
    if damage=='pointer':path.unlink()
    else:path.write_bytes(b'{}')
    with pytest.raises(AgentError) as error:p.lecture(plan)
    assert error.value.code=='LOCAL_REPAIR_CACHE_INVALID'
    assert provider.patches==1 and provider.reviews==2


def direct_recovery(tmp_path,section=None):
    provider=Provider();_,p,plan=setup_pipeline(tmp_path,provider)
    section=section or provider.generate('writer_lecture_section',{},None)
    spec={**plan['sections'][0],'id':section['section_id']}
    draft=p.build_root/'direct';draft.mkdir()
    recovery=LocalRecovery(p,spec,{'synthetic':'context'},section,plan,draft)
    return p,plan,recovery


def test_per_unit_budget_is_not_a_per_section_limit_and_counts_calculation_updates(tmp_path):
    p,_,r=direct_recovery(tmp_path)
    for unit_id in ('S01.U1','S01.U2'):
        for number in range(2):
            r.begin_proposal('patch',['unit:'+unit_id],[unit_id])
            value=r.candidate()
            next(u for u in value['units'] if u['id']==unit_id)['tex']+=str(number)
            r.accept(value)
    assert r.state['applied_rounds']==4 and r.state['unit_applied_counts']=={'S01.U1':2,'S01.U2':2}
    with pytest.raises(AgentError) as error:r.begin_proposal('patch',['unit:S01.U1'],['S01.U1'])
    assert error.value.code=='BUDGET_EXHAUSTED' and 'S01.U1' in str(error.value)
    assert p.store.get_run(p.run['id'])['request_count']==0


def test_calculation_only_change_consumes_its_bound_unit_budget(tmp_path):
    _,_,r=direct_recovery(tmp_path)
    for n in range(2):
        r.begin_proposal('patch',['unit:S01.U1'],['S01.U1'])
        value=r.candidate();value['calculations']=[{'id':'C1','unit_id':'S01.U1','kind':'equivalence',
            'lhs':{'op':'Integer','value':n},'rhs':{'op':'Integer','value':n},'assumptions':{}}]
        r.accept(value)
    assert r.state['unit_applied_counts']=={'S01.U1':2}
    with pytest.raises(AgentError) as error:r.begin_proposal('patch',['unit:S01.U1'],['S01.U1'])
    assert error.value.code=='BUDGET_EXHAUSTED'


@pytest.mark.parametrize('chapter',['ch01_s04','ch02_s02','ch03_s03'])
def test_real_legacy_hash_chain_imports_only_legal_repair_and_preserves_requests(tmp_path,chapter):
    fixture=json.loads((Path(__file__).parent/'fixtures'/f'local_recovery_{chapter}.json').read_bytes())
    files=fixture['captured_files'];original=files['candidate.json'];sid=original['section_id']
    class CaptureProvider:
        def generate(self,*args):return copy.deepcopy(original)
    _,p,plan=setup_pipeline(tmp_path,CaptureProvider(),max_requests_per_run=60)
    spec={**plan['sections'][0],'id':sid};context={'section':spec,'captured':'fixture'}
    _,first=p.writer_draft(spec,context)
    for name,data in files.items():write_json(first/name,data)
    # writer cache hashes bytes: use the original writer-produced bytes, not reserialization changes.
    cache=json.loads((p.root/'draft-cache'/f'{sid}.json').read_bytes())
    cache['candidate_hash']=digest((first/'candidate.json').read_bytes())
    write_json(p.root/'draft-cache'/f'{sid}.json',cache)
    base,draft=p.writer_draft(spec,context);base=normalize_written_section(base)[0]
    with p.store.transaction() as c:c.execute('UPDATE runs SET request_count=26 WHERE id=?',(p.run['id'],))
    r=LocalRecovery(p,spec,context,base,plan,draft)
    assert r.state['proposal_calls']==2 and r.state['applied_rounds']==1 and r.state['rejected_proposals']==1
    assert r.candidate()==files['repair-1.json']['section']
    assert r.candidate()!=files['repair-2-raw.json']
    expected={'ch01_s04':{'S04.U04':1,'S04.U06':1},'ch02_s02':{'S02.U18':1,'S02.U19':1,'S02.U20':1},
        'ch03_s03':{'S03.U04':1,'S03.U06':1}}[chapter]
    assert r.state['unit_applied_counts']==expected
    assert p.store.get_run(p.run['id'])['request_count']==26 and r.state['pending_issues']
    assert p.effective_budget()['requests']==60
    assert len(r.state['evidence_dependencies'])>=8
    assert r.state['legacy_import']['old_reviewer_prompt_hash']=='UNKNOWN_NOT_ARCHIVED'
    if chapter=='ch02_s02':
        # Appended answer bodies have independent structural proposal keys; they must
        # not consume the exercise's final legal body-edit opportunity.
        before=r.candidate();questions=['S02.U18','S02.U19','S02.U20']
        r.begin_proposal('answers',['answer:'+i for i in questions])
        with_answers=copy.deepcopy(before)
        with_answers['units'] += [{'id':i+'.answer','kind':'solution','tex':'独立测试题解正文。','relates_to':i} for i in questions]
        r.accept(with_answers)
        assert all(r.state['unit_applied_counts'][i]==1 for i in questions)
        r.begin_proposal('strict_local_patch',['unit:'+i for i in questions],questions)
        fixed=copy.deepcopy(with_answers)
        for unit in fixed['units']:
            if unit['id'] in questions:unit['tex']+=' 题解已单列（仅离线预算验证）。'
        r.accept(fixed)
        assert all(r.state['unit_applied_counts'][i]==2 for i in questions)
        assert r.state['proposal_calls']==4 and r.state['rejected_proposals']==1
        assert p.store.get_run(p.run['id'])['request_count']==26
    # Corruption after import must not be hidden by the accepted candidate's own valid hash.
    (first/'repair-2-raw.json').write_bytes(b'{}')
    with pytest.raises(AgentError) as error:r.candidate()
    assert error.value.code=='LOCAL_REPAIR_LEGACY_UNVERIFIED'


def test_identical_review_identity_cannot_erase_unresolved_issue(tmp_path):
    _,_,r=direct_recovery(tmp_path);identity,_=r.review_context(r.candidate(),{'status':'PASS'})
    issue={'unit_id':'S01.U1','severity':'review','message':'未决前提','evidence':'fixture'}
    r.record_review([issue],identity,{'issues':[issue]})
    assert r.record_review([],identity,{'issues':[]})==[issue]
    changed={**identity,'reviewer_prompt_hash':'explicit-new-policy'}
    assert r.record_review([],changed,{'issues':[]})==[]
    assert list((r.folder).glob('review-*.json'))


def test_parser_result_change_reopens_explicit_review_without_erasing_history(tmp_path):
    _,_,r=direct_recovery(tmp_path)
    issue={'unit_id':'S01.U1','rule_id':'LECTURE_FRAGMENT_AMBIGUOUS','severity':'blocking','message':'old parser failure'}
    before,_=r.review_context(r.candidate(),{'status':'PASS'}, {'normalization':'BLOCKED','issues':[issue]})
    r.record_review([issue],before,{'issues':[issue]})
    assert r.record_review([],before,{'issues':[]})==[issue]
    after,context=r.review_context(r.candidate(),{'status':'PASS'},{'normalization':'PASS','issues':[]})
    assert before['candidate_hash']==after['candidate_hash']
    assert before['tool_checks_hash']==after['tool_checks_hash']
    assert before['deterministic_checks_hash']!=after['deterministic_checks_hash']
    assert context['unresolved_issues']==[issue]
    assert r.record_review([],after,{'issues':[]})==[]
    records=[json.loads(p.read_bytes()) for p in r.folder.glob('review-*.json')]
    assert any(record['prior_issues']==[issue] and record['retained_issues']==[] for record in records)
    assert r.state['proposal_calls']==0 and r.state['unit_applied_counts']=={}


@pytest.mark.windows_compile
def test_strict_local_patch_is_rechecked_then_actually_compiled_on_windows(tmp_path,monkeypatch):
    provider=Provider();service,p,plan,_=setup(tmp_path,monkeypatch,provider,real_compile=True)
    completed,reports=p.lecture(plan)
    assert provider.writes==provider.patches==1 and provider.reviews==2
    assert reports[0]['compile']['status']=='PASS'
    assert Path(reports[0]['compile']['pdf_path']).is_file()
    assert '已明示前提' in completed[0][1]['units'][0]['tex']
    assert state(p)['phase']=='CHECKED'
    assert service.store.get_run(p.run['id'])['reviews']==[]


def test_real_ch03_patch_repairs_ast_without_changing_unapproved_punctuation():
    from math_agent.mathcheck import check_math
    captured=json.loads((Path(__file__).parent/'fixtures/local_recovery_ch03_s03.json').read_bytes())['captured_files']
    before=captured['repair-1.json']['section'];rejected=captured['repair-2-raw.json']
    allowed={'S03.U03','S03.U06'};units={u['id']:u for u in rejected['units']}
    patch={'section_id':'S03','replacements':[{'unit_id':i,'tex':units[i]['tex']} for i in sorted(allowed)],
        'calculation_updates':[c for c in rejected['calculations'] if c['unit_id'] in allowed],
        'calculation_additions':[],'uncertainties_append':[],'calculation_limitations_append':[]}
    after,evidence=apply_local_patch(before,allowed,patch)
    assert after['units'][9]==before['units'][9] and after['units'][9]!=rejected['units'][9]
    assert evidence['status']=='APPLIED_UNCHECKED'
    assert check_math(before)['status']=='NEEDS_REVIEW'
    checked=check_math(after)
    assert checked['status']=='PASS',checked


@pytest.mark.parametrize('field',['candidate_hash','before_hash','raw_body'])
def test_legacy_chain_mismatch_does_not_start_fresh_and_reset_counters(tmp_path,field):
    captured=json.loads((Path(__file__).parent/'fixtures/local_recovery_ch01_s04.json').read_bytes())['captured_files']
    original=captured['candidate.json'];sid=original['section_id']
    class CaptureProvider:
        def generate(self,*args):return copy.deepcopy(original)
    _,p,plan=setup_pipeline(tmp_path,CaptureProvider())
    spec={**plan['sections'][0],'id':sid};context={'section':spec}
    _,first=p.writer_draft(spec,context)
    for name,data in captured.items():write_json(first/name,data)
    cache=json.loads((p.root/'draft-cache'/f'{sid}.json').read_bytes())
    cache['candidate_hash']=digest((first/'candidate.json').read_bytes());write_json(p.root/'draft-cache'/f'{sid}.json',cache)
    if field=='candidate_hash':
        data=captured['candidate-normalization.json'];data['normalized_hash']='corrupt';write_json(first/'candidate-normalization.json',data)
    elif field=='before_hash':
        data=captured['repair-1.json'];data['before_hash']='corrupt';write_json(first/'repair-1.json',data)
    else:
        data=captured['repair-1-raw.json'];data['units'][0]['tex']+=' changed';write_json(first/'repair-1-raw.json',data)
    base,draft=p.writer_draft(spec,context);base=normalize_written_section(base)[0]
    with pytest.raises(AgentError) as error:LocalRecovery(p,spec,context,base,plan,draft)
    assert error.value.code=='LOCAL_REPAIR_LEGACY_UNVERIFIED'
    assert state(p,sid)['phase']=='LEGACY_IMPORT_BLOCKED'
    with pytest.raises(AgentError) as error:LocalRecovery(p,spec,context,base,plan,draft)
    assert error.value.code=='LOCAL_REPAIR_LEGACY_UNVERIFIED'


def test_explicit_user_budget_increase_preserves_local_counts_and_allows_one_more_edit(tmp_path):
    from math_agent.budget import BudgetIncrease
    from math_agent.service import Service
    p,plan,r=direct_recovery(tmp_path)
    for number in range(2):
        r.begin_proposal('patch',['unit:S01.U1'],['S01.U1'])
        data=r.candidate();data['units'][0]['tex']+=str(number);r.accept(data)
    p.store.finish(p.job,'BLOCKED','repair.section.S01',{'code':'BUDGET_EXHAUSTED','message':'synthetic cap'})
    service=Service(p.settings)
    service.increase_budget(p.run['id'],BudgetIncrease(expected_version=p.effective_budget()['version'],
        expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],local_repairs_per_unit=3,
        action_id='synthetic-explicit-user',note='Offline test of explicit user action, not an actual benchmark increase'))
    service.retry(p.run['id']);job=service.store.claim('budget-resume')
    new=Pipeline(p.settings,service.store,job)
    draft=new.build_root/'resumed';draft.mkdir()
    base=Provider().generate('writer_lecture_section',{},None)
    resumed=LocalRecovery(new,plan['sections'][0],{'synthetic':'context'},base,plan,draft)
    assert resumed.state['unit_applied_counts']=={'S01.U1':2}
    resumed.begin_proposal('patch',['unit:S01.U1'],['S01.U1'])
    data=resumed.candidate();data['units'][0]['tex']+='third';resumed.accept(data)
    assert resumed.state['unit_applied_counts']=={'S01.U1':3}
    assert new.effective_budget()['global_repair_rounds']==2


def test_pipeline_before_request_retains_independent_hard_cap(tmp_path,monkeypatch):
    import math_agent.pipeline as module
    from math_agent.domain import NewRun
    from math_agent.service import Service
    from math_agent.settings import Settings
    class CallbackProvider:
        def __init__(self,settings,**kwargs):self.before=kwargs['before_request']
    monkeypatch.setattr(module,'CompatibleChatProvider',CallbackProvider)
    settings=Settings(workspace=tmp_path/'w',reference_root=tmp_path/'refs',max_requests_per_run=60,request_budget_hard_cap=1)
    service=Service(settings);run=service.create(NewRun(workflow_id='lecture.generate',topic='MOCK transport',provider='live'))
    service.propose(run['id']);p=Pipeline(settings,service.store,service.store.claim('fake-transport'))
    p.provider.before({'fixture':'no_network'})
    with pytest.raises(AgentError) as error:p.provider.before({'fixture':'no_network'})
    assert error.value.code=='BUDGET_EXHAUSTED'
    assert service.store.get_run(run['id'])['request_count']==1
    assert p.effective_budget()['requests']==60
