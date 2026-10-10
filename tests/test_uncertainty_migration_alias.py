"""Same verdict's audited migration is not a second model judgment; fully offline."""
import copy
import json
import shutil
import pytest
import math_agent.uncertainty_review as ur
from math_agent.util import AgentError,digest,write_json
from math_agent.uncertainty_protocol_recovery import LEGACY_CONTRACT
from test_uncertainty_protocol_recovery import replay_fixture,forbidden

def prepare(tmp_path,monkeypatch,chapter='CH02',provider='adaac69a8e12ff4956a8b251170176ab3cae80da787bd7f76bd729f116303685'):
    contract={**copy.deepcopy(LEGACY_CONTRACT),'version':2,
        'helper_sha256':'2014e3aec411c6aced3fe0f16e38323397bbd9b5a44e0841fe1a800157511187',
        'protocol_recovery_sha256':'fcb647c4ba2d5cfbda92485ba9a6d284eed9e4ab611f0117a76baf231d77cd15','provider_sha256':provider}
    with monkeypatch.context() as patch:
        patch.setattr(ur,'uncertainty_contract',lambda:copy.deepcopy(contract))
        p,alias,original,_=replay_fixture(tmp_path,chapter)
        alias.ordinary_review(forbidden,{})
        result,issues=alias.evaluate()
    current=ur.UncertaintyReview(p,alias.context)
    assert current.folder!=alias.folder
    return p,alias,current,original,result,issues

@pytest.mark.parametrize('chapter',['CH02','CH03'])
@pytest.mark.parametrize('provider',['adaac69a8e12ff4956a8b251170176ab3cae80da787bd7f76bd729f116303685','529a8c3baf3f660d503757302534caa0f89a3cdb18b7bd31b0ddf7a5dc124c79'])
def test_transport_upgrade_replays_same_verdict_and_keeps_old_ledgers(tmp_path,monkeypatch,chapter,provider):
    p,alias,current,original,old,issues=prepare(tmp_path,monkeypatch,chapter,provider)
    files={f:digest(f.read_bytes()) for folder in (alias.folder,original) for f in folder.iterdir()}
    before=p.store.get_run(p.run['id'])
    assert current.ordinary_review(forbidden,{})==alias._read('ordinary-review.json')
    result,new_issues=current.evaluate()
    assert result['assessment']==old['assessment'] and new_issues==issues
    assert current.state['migration_source']==alias.state['migration_source']
    assert current.state['calls']==1 and current.state['provider_calls_during_replay']==0
    restarted=ur.UncertaintyReview(p,alias.context)
    assert restarted.evaluate()==(result,new_issues)
    assert files=={f:digest(f.read_bytes()) for f in files}
    after=p.store.get_run(p.run['id'])
    for key in ('request_count','approval','reviews'):assert before[key]==after[key]

@pytest.mark.parametrize('damage',['missing_receipt','duplicate_receipt','changed_receipt','changed_response','changed_raw','missing_evidence',
    'extra_evidence','changed_source','unknown_contract','independent_verdict','wrong_origin','wrong_replay_count','wrong_calls','incomplete','missing_root'])
def test_alias_never_hides_conflicts_or_missing_evidence(tmp_path,monkeypatch,damage):
    p,alias,current,original,_,_=prepare(tmp_path,monkeypatch)
    state=json.loads(alias.path.read_bytes())
    if damage in ('missing_receipt','duplicate_receipt','changed_receipt'):
        with p.store.transaction() as c:
            row=c.execute("SELECT * FROM events WHERE run_id=? AND type='math.uncertainty_migrated'",(p.run['id'],)).fetchone()
            if damage=='missing_receipt':c.execute('DELETE FROM events WHERE sequence=?',(row['sequence'],))
            elif damage=='duplicate_receipt':c.execute('INSERT INTO events(run_id,type,payload_json,timestamp) VALUES(?,?,?,?)',(p.run['id'],row['type'],row['payload_json'],row['timestamp']))
            else:
                value=json.loads(row['payload_json']);value['provider_calls_during_replay']=1
                c.execute('UPDATE events SET payload_json=? WHERE sequence=?',(json.dumps(value),row['sequence']))
    elif damage in ('changed_response','changed_raw'):
        path=alias.folder/'response-1.json';data=json.loads(path.read_bytes());data['limitations'].append('unapproved reinterpretation')
        write_json(path,data)
        if damage=='changed_response':state['dependencies']['response-1.json']=digest(path.read_bytes())
    elif damage=='missing_evidence':(alias.folder/'assessment.json').unlink()
    elif damage=='extra_evidence':state['dependencies']['extra.json']='0'*64
    elif damage=='changed_source':state['migration_source']['state_sha256']='0'*64
    elif damage=='unknown_contract':state['identity']['contract']['provider_sha256']='0'*64
    elif damage=='independent_verdict':state.pop('migration_source')
    elif damage=='wrong_origin':state['origin_job_id']='unrelated-job'
    elif damage=='wrong_replay_count':state['provider_calls_during_replay']=1
    elif damage=='wrong_calls':state['calls']=2
    elif damage=='incomplete':state['status']='MIGRATING'
    else:(original/'state.json').unlink()
    write_json(alias.path,state)
    with pytest.raises(AgentError) as exc:current.ordinary_review(forbidden,{})
    assert exc.value.code=='UNCERTAINTY_EVIDENCE_BLOCKED'
    assert not current.path.exists()

def test_fresh_independent_duplicate_is_not_collapsed(tmp_path,monkeypatch):
    _,alias,current,_,_,_=prepare(tmp_path,monkeypatch)
    duplicate=alias.folder.with_name('a'*24);shutil.copytree(alias.folder,duplicate)
    with pytest.raises(AgentError):current.ordinary_review(forbidden,{})
    assert not current.path.exists()
