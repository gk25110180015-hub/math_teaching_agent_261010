"""Actual SQLite/fencing, captured rejected AST, controlled model/compiler only."""
import copy
import json
from pathlib import Path

import pytest

from math_agent import global_repair_contract as contract
from math_agent.pipeline import Pipeline
from math_agent.local_patch import LocalPatch
from math_agent.budget import BudgetIncrease
from math_agent.util import AgentError, digest, write_json
from test_global_repair import GlobalRepairProvider, setup


pytestmark = pytest.mark.unit


class PatchProvider(GlobalRepairProvider):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.active = None
        self.reply = None
        self.after_reply = None

    def generate(self, role, context, schema):
        if self.active:
            self.active.store.count_request(self.active.job,60,{'role':role,'fixture':'OFFLINE_NO_HTTP'})
        self.calls.append((role,copy.deepcopy(context)))
        if role == 'repair_local_patch':
            assert schema is LocalPatch
            self.repairs.append(copy.deepcopy(context))
            response = self.reply or {'section_id':context['section']['section_id'], 'replacements':[
                {'unit_id':unit['id'],'tex':unit['tex']+' 正整数无上界（阿基米德性质）。'}
                for unit in context['section']['units'] if unit['id'] in context['allowed_unit_ids']]}
            if self.after_reply:self.after_reply()
            return copy.deepcopy(response)
        assert role != 'repair_content_unit', 'Global repairs must request a strict patch, never a whole section'
        return super().generate(role,context,schema)


def setup_raised(tmp_path,provider,monkeypatch):
    service,p,plan,compiles=setup(tmp_path,provider,monkeypatch,limit=2)
    service.store.finish(p.job,'BLOCKED','offline.fixture',{'code':'BUDGET_EXHAUSTED'})
    service.increase_budget(p.run['id'],BudgetIncrease(expected_version=service.get_budget(p.run['id'])['version'],
        expected_plan_revision=plan['revision'],expected_plan_hash=plan['hash'],
        action_id='offline-explicit-global-six',global_repair_rounds=6,note='Offline authorized migration fixture'))
    service.retry(p.run['id'])
    resumed=Pipeline(p.settings,p.store,p.store.claim('offline-increased-migration-worker'))
    resumed.provider=provider
    return service,resumed,plan,compiles


def seed(tmp_path, monkeypatch, *, phase='repair_pending'):
    provider=PatchProvider()
    service,pipeline,plan,compiles=setup_raised(tmp_path,provider,monkeypatch)
    provider.active=pipeline
    completed,_=pipeline._lecture_sections(plan)
    state={'schema_version':1,'identity':contract.known_legacy_identity(pipeline,plan),'rounds_used':2,
        'phase':'validated','sections':{},'pending':[],'teacher_visual_review':'NOT_RUN'}
    issues=[{'unit_id':'S01.U01','severity':'review','message':'Preserved premise gap',
             'evidence':'Original bounded mock concern, not a live judgment'}]
    pipeline._start_global_repair(completed,issues,state)
    if phase in ('checking','validated','budget_exhausted'):
        state['pending']=[];state['phase']=phase
        # A genuinely accepted prior patch must not be rolled back by migration.
        old=pipeline._global_repair_sections(state)['S01']
        old['units'][0]['tex']+=' 正整数无上界（阿基米德性质）。'
        candidate=pipeline.settings.workspace/state['sections']['S01']['candidate_key']
        write_json(candidate,old);state['sections']['S01']['candidate_hash']=digest(candidate.read_bytes())
    write_json(pipeline.root/'global-repair-state.json',state)
    return service,pipeline,plan,provider,compiles,copy.deepcopy(state)


def events(pipeline):
    with pipeline.store.connect() as connection:
        return [json.loads(row[0]) for row in connection.execute(
            'SELECT payload_json FROM events WHERE run_id=? AND type=?', (pipeline.run['id'],contract.EVENT))]


def test_known_v1_pending_migrates_and_resumes_original_issue_before_any_new_review(tmp_path,monkeypatch):
    service,p,plan,provider,_,old=seed(tmp_path,monkeypatch)
    path=p.root/'global-repair-state.json';raw=path.read_bytes()
    run=service.store.get_run(p.run['id']);count=len(provider.calls)
    migrated=p._load_global_repair_state(plan)
    assert migrated['schema_version']==2 and migrated['identity']==p._global_repair_identity(plan)
    assert {k:v for k,v in migrated.items() if k not in ('identity','schema_version','contract_migration')} == {
        k:v for k,v in old.items() if k not in ('identity','schema_version')}
    assert service.store.get_run(p.run['id'])==run and len(provider.calls)==count
    assert migrated['rounds_used']==3 and migrated['pending']==old['pending']
    ev=events(p);assert len(ev)==1 and ev[0]['request_count_preserved']==run['request_count']
    assert (p.settings.workspace/ev[0]['before_key']).read_bytes()==raw
    assert p._load_global_repair_state(plan)==migrated and len(events(p))==1
    completed,_=p.lecture(plan)
    assert provider.calls[count][0]=='repair_local_patch'
    assert provider.calls[count][1]['issues']==old['pending'][0]['issues']
    assert len(provider.repairs)==1 and provider.writes==['S01','S02']
    assert '阿基米德' in completed[0][1]['units'][0]['tex']
    final=json.loads(path.read_bytes());assert final['phase']=='validated' and final['rounds_used']==3
    after=service.store.get_run(p.run['id'])
    assert after['approval']==run['approval'] and after['input_hash']==run['input_hash'] and after['reviews']==[]
    assert after['request_count']==len(provider.calls)>run['request_count']
    assert len(events(p))==1


@pytest.mark.parametrize('field',['repair_prompt_hash','written_schema_hash','normalizer_hash','extra','model','provider'])
def test_unknown_legacy_contract_is_not_migrated_or_reset(tmp_path,monkeypatch,field):
    _,p,plan,provider,_,state=seed(tmp_path,monkeypatch)
    state['identity'][field]='unknown-contract'
    path=p.root/'global-repair-state.json';write_json(path,state);raw=path.read_bytes()
    count=len(provider.calls)
    with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
    assert error.value.code=='GLOBAL_REPAIR_CONTRACT_CHANGED'
    assert path.read_bytes()==raw and len(provider.calls)==count and events(p)==[]


@pytest.mark.parametrize('corruption',['bool_round','negative_round','bad_phase','extra_target','duplicate_target',
    'issue_target','neighbor','candidate_hash','folder','bool_version'])
def test_malformed_legacy_state_is_preserved_and_blocked(tmp_path,monkeypatch,corruption):
    _,p,plan,_,_,state=seed(tmp_path,monkeypatch)
    if corruption=='bool_round':state['rounds_used']=True
    elif corruption=='negative_round':state['rounds_used']=-1
    elif corruption=='bad_phase':state['phase']='accepted_by_model'
    elif corruption=='extra_target':state['pending'][0]['allowed_unit_ids'].append('S01.U02')
    elif corruption=='duplicate_target':state['pending'][0]['allowed_unit_ids']*=2
    elif corruption=='issue_target':state['pending'][0]['issues'][0]['unit_id']='S01.U02'
    elif corruption=='neighbor':state['pending'][0]['neighbors'][0]['section']['title']='Unapproved changed context'
    elif corruption=='candidate_hash':state['sections']['S01']['candidate_hash']='0'*64
    elif corruption=='folder':state['round_directory']='runs/foreign-run/global-repairs/r3-forged'
    elif corruption=='bool_version':state['schema_version']=True
    path=p.root/'global-repair-state.json';write_json(path,state);raw=path.read_bytes()
    with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
    assert error.value.code in {'GLOBAL_REPAIR_MIGRATION_INVALID','GLOBAL_REPAIR_CACHE_INVALID','GLOBAL_REPAIR_CONTRACT_CHANGED'}
    assert path.read_bytes()==raw and events(p)==[]


@pytest.mark.parametrize('phase',['checking','validated','budget_exhausted'])
def test_accepted_candidates_and_rounds_survive_phase_migration(tmp_path,monkeypatch,phase):
    _,p,plan,provider,_,old=seed(tmp_path,monkeypatch,phase=phase)
    before=p._global_repair_sections(old);count=len(provider.calls)
    state=p._load_global_repair_state(plan)
    assert state['phase']==phase and state['rounds_used']==3 and state['sections']==old['sections']
    assert p._global_repair_sections(state)==before and state['issues']==old['issues']
    assert len(provider.calls)==count


def test_reachable_validated_checkpoint_is_rechecked_without_rolling_back_accepted_body(tmp_path,monkeypatch):
    provider=PatchProvider();service,p,plan,compiles=setup_raised(tmp_path,provider,monkeypatch);provider.active=p
    before,_=p.lecture(plan)
    path=p.root/'global-repair-state.json';legacy=json.loads(path.read_bytes())
    assert legacy['phase']=='validated' and legacy['rounds_used']==1
    assert '阿基米德' in before[0][1]['units'][0]['tex'] and len(provider.repairs)==1
    legacy.update(schema_version=1,identity=contract.known_legacy_identity(p,plan));write_json(path,legacy)
    writes=list(provider.writes);repairs=len(provider.repairs);locals_before=len(provider.locals)
    prior_contract=p._section_check_contract()
    monkeypatch.setattr(p,'_section_check_contract',lambda:{**prior_contract,'offline_new_checker_contract':True})
    after,_=p.lecture(plan)
    assert after==before and provider.writes==writes and len(provider.repairs)==repairs
    assert len(provider.locals)>locals_before  # Actual refreshed review, not a fixture-return shortcut.
    saved=json.loads(path.read_bytes());assert saved['phase']=='validated' and saved['rounds_used']==1
    assert len(events(p))==1 and service.store.get_run(p.run['id'])['reviews']==[]


@pytest.mark.parametrize('point',['journal_before_state','state_before_event'])
def test_migration_crash_recovers_without_duplicate_event_or_new_calls(tmp_path,monkeypatch,point):
    service,p,plan,provider,_,_=seed(tmp_path,monkeypatch)
    path=p.root/'global-repair-state.json';raw=path.read_bytes();run=service.store.get_run(p.run['id'])
    original_event=p.store.event;original_replace=contract._replace_state
    def event(connection,rid,kind,payload=None):
        if kind==contract.EVENT:raise RuntimeError('Synthetic crash after state replace')
        return original_event(connection,rid,kind,payload)
    def replace(path,data):raise RuntimeError('Synthetic crash after immutable journal')
    monkeypatch.setattr(p.store,'event',event if point=='state_before_event' else original_event)
    monkeypatch.setattr(contract,'_replace_state',replace if point=='journal_before_state' else original_replace)
    with pytest.raises(RuntimeError):p._load_global_repair_state(plan)
    assert events(p)==[]
    if point=='journal_before_state':assert path.read_bytes()==raw
    else:assert json.loads(path.read_bytes())['schema_version']==2
    monkeypatch.setattr(p.store,'event',original_event);monkeypatch.setattr(contract,'_replace_state',original_replace)
    calls=len(provider.calls);state=p._load_global_repair_state(plan)
    assert state['rounds_used']==3 and state['phase']=='repair_pending'
    assert len(provider.calls)==calls and service.store.get_run(p.run['id'])==run
    assert len(events(p))==1
    assert (p.settings.workspace/events(p)[0]['before_key']).read_bytes()==raw
    p._load_global_repair_state(plan);assert len(events(p))==1


def test_lost_lease_before_migration_leaves_original_bytes_and_no_journal(tmp_path,monkeypatch):
    service,p,plan,_,_,_=seed(tmp_path,monkeypatch)
    path=p.root/'global-repair-state.json';raw=path.read_bytes()
    service.cancel(p.run['id'])
    with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
    assert error.value.code=='LEASE_LOST' and path.read_bytes()==raw
    assert not (p.root/'global-repairs/contract-migrations').exists() and events(p)==[]


@pytest.mark.parametrize('rounds,blocked',[(0,True),(2,True),(4,False)])
def test_migrated_current_rounds_cannot_fall_below_preserved_history(tmp_path,monkeypatch,rounds,blocked):
    _,p,plan,provider,_,_=seed(tmp_path,monkeypatch)
    state=p._load_global_repair_state(plan)
    state['rounds_used']=rounds
    path=p.root/'global-repair-state.json';write_json(path,state);raw=path.read_bytes()
    count=len(provider.calls)
    if blocked:
        with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
        assert error.value.code=='GLOBAL_REPAIR_MIGRATION_INVALID'
    else:assert p._load_global_repair_state(plan)['rounds_used']==4
    assert path.read_bytes()==raw and len(events(p))==1 and len(provider.calls)==count


@pytest.mark.parametrize('field',['approval_hash','input_hash','request_count_preserved','negative_count','pending_scope'])
def test_reused_precommit_journal_must_match_current_approval_and_counters(tmp_path,monkeypatch,field):
    _,p,plan,_,_,_=seed(tmp_path,monkeypatch)
    path=p.root/'global-repair-state.json';raw=path.read_bytes()
    original=contract._replace_state
    def interrupted(*args):raise RuntimeError('Synthetic journal before state interruption')
    monkeypatch.setattr(contract,'_replace_state',interrupted)
    with pytest.raises(RuntimeError):p._load_global_repair_state(plan)
    journal=next((p.root/'global-repairs/contract-migrations').glob('*/evidence.json'))
    evidence=json.loads(journal.read_bytes())
    if field=='negative_count':evidence['request_count_preserved']=-1
    elif field=='pending_scope':evidence['pending_scope']=[]
    else:evidence[field]=999999 if field=='request_count_preserved' else 'corrupted'
    write_json(journal,evidence);monkeypatch.setattr(contract,'_replace_state',original)
    with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
    assert error.value.code=='GLOBAL_REPAIR_MIGRATION_INVALID'
    assert path.read_bytes()==raw and events(p)==[]


@pytest.mark.parametrize('file',['before.json','after.json','evidence.json'])
def test_migration_evidence_corruption_never_reuses_old_pass(tmp_path,monkeypatch,file):
    _,p,plan,provider,_,_=seed(tmp_path,monkeypatch)
    state=p._load_global_repair_state(plan);path=p.root/'global-repair-state.json';raw=path.read_bytes()
    folder=(p.settings.workspace/state['contract_migration']['evidence_key']).parent
    (folder/file).write_bytes(b'{}')
    count=len(provider.calls)
    with pytest.raises(AgentError) as error:p._load_global_repair_state(plan)
    assert error.value.code=='GLOBAL_REPAIR_MIGRATION_INVALID'
    assert path.read_bytes()==raw and len(provider.calls)==count


def test_request_budget_blocks_pending_patch_without_losing_migration_or_scope(tmp_path,monkeypatch):
    service,p,plan,provider,_,_=seed(tmp_path,monkeypatch)
    state=p._load_global_repair_state(plan)
    limit=p.effective_budget()['requests']
    while service.store.get_run(p.run['id'])['request_count']<limit:
        p.store.count_request(p.job,60,{'role':'offline-count-fixture'})
    path=p.root/'global-repair-state.json';raw=path.read_bytes();count=len(provider.calls)
    with pytest.raises(AgentError) as error:p._continue_global_repairs(plan,state)
    assert error.value.code=='BUDGET_EXHAUSTED' and path.read_bytes()==raw
    assert len(provider.calls)==count and service.store.get_run(p.run['id'])['request_count']==limit


def test_late_patch_after_cancel_is_archived_but_not_accepted(tmp_path,monkeypatch):
    service,p,plan,provider,_,_=seed(tmp_path,monkeypatch)
    state=p._load_global_repair_state(plan);before=copy.deepcopy(state)
    path=p.root/'global-repair-state.json';raw=path.read_bytes()
    provider.after_reply=lambda:service.cancel(p.run['id'])
    with pytest.raises(AgentError) as error:p._continue_global_repairs(plan,state)
    assert error.value.code=='LEASE_LOST' and path.read_bytes()==raw and state==before
    assert list((p.root/'global-repairs').rglob('*-raw.json'))


def captured():
    return json.loads((Path(__file__).parent/'fixtures/global_patch_ch02_rejected.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('response_kind',['valid_sparse','whole_section','forbidden_calculation'])
def test_real_ch02_proposal_cannot_modify_unrelated_c03_ast(tmp_path,monkeypatch,response_kind):
    fixture=captured();before=fixture['before'];bad=fixture['rejected']
    original=next(c for c in before['calculations'] if c['id']=='S02.C03')
    changed=next(c for c in bad['calculations'] if c['id']=='S02.C03')
    assert original['unit_id']==changed['unit_id']=='S02.U16' and original['lhs']!=changed['lhs']
    from math_agent.mathcheck import _calculate
    assert _calculate({**original,'kind':'numeric_spotcheck','points':[{'n':1}]})['status']=='PASS'
    assert _calculate({**changed,'kind':'numeric_spotcheck','points':[{'n':1}]})['status']=='FAIL'
    provider=PatchProvider();_,p,plan,_=setup_raised(tmp_path,provider,monkeypatch);provider.active=p
    section1=provider.generate('writer_lecture_section',{'section':plan['sections'][0]},None)
    old={'schema_version':2,'identity':p._global_repair_identity(plan),'rounds_used':2,
         'phase':'validated','sections':{},'pending':[],'teacher_visual_review':'NOT_RUN'}
    p._start_global_repair([(plan['sections'][0],section1),(plan['sections'][1],before)],
        [{'unit_id':'S02.U14','severity':'review','message':'Preserved old concern; no mathematical verdict here'}],old)
    assert set(old['sections'])=={'S02'} and old['pending'][0]['neighbors'][0]['section']['id']=='S01'
    replacement=next(u['tex'] for u in bad['units'] if u['id']=='S02.U14')
    provider.reply={'section_id':'S02','replacements':[{'unit_id':'S02.U14','tex':replacement}]}
    if response_kind=='whole_section':provider.reply=bad
    elif response_kind=='forbidden_calculation':provider.reply['calculation_updates']=[changed]
    path=p.root/'global-repair-state.json';raw=path.read_bytes()
    if response_kind!='valid_sparse':
        with pytest.raises(AgentError) as error:p._continue_global_repairs(plan,old)
        assert error.value.code=='GLOBAL_REPAIR_SCOPE_VIOLATION' and path.read_bytes()==raw
        assert old['pending'] and list((p.root/'global-repairs').rglob('*-rejected.json'))
    else:
        p._continue_global_repairs(plan,old)
        after=p._global_repair_sections(old)['S02']
        assert after['calculations']==before['calculations']
        assert [u for u in after['units'] if u['id']!='S02.U14']==[u for u in before['units'] if u['id']!='S02.U14']
        assert old['rounds_used']==3 and old['phase']=='checking' and not old['pending']
        assert _calculate({**next(c for c in after['calculations'] if c['id']=='S02.C03'),
                           'kind':'numeric_spotcheck','points':[{'n':1}]})['status']=='PASS'
