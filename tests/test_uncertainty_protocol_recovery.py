"""Frozen live responses; offline SQLite replay only, no API or teacher review."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from math_agent.uncertainty_review import UncertaintyReview, validate_uncertainty_assessment, effective_uncertainty_issues
from math_agent.uncertainty_protocol_recovery import decode_uncertainty_json, LEGACY_CONTRACT
from math_agent.util import AgentError, digest, write_json
from test_uncertainty_review import context, assessment, direct_guard

FIXTURES = Path(__file__).parent / 'fixtures' / 'uncertainty_protocol'
if not FIXTURES.exists():
    FIXTURES = Path(__file__).parent / 'fixtures'


def forbidden(*args, **kwargs):
    raise AssertionError('A frozen verdict must not trigger another model call')


@pytest.mark.parametrize('text', [
    '{"x":1}]}', '{"x":[1,{"y":2}]} }', '{"x":"literal ]} in text"}]]}}',
])
def test_only_complete_object_and_bounded_trailing_closers_recover(text):
    parsed, recovery = decode_uncertainty_json(text)
    assert recovery and recovery['original_sha256'] == digest(text)
    assert parsed == json.JSONDecoder().raw_decode(text)[0]


@pytest.mark.parametrize('text', [
    '{"x":1}{"y":2}', '{"x":1} null', '{"x":1} verdict', '{"x":1},',
    '{"x":1}////', '{"x":1}]]]]]', '{"x":1}'+' '*33+']',
    '{"x":1', '{"x":', '{"x":"unterminated}', '[{"x":1}]',
    '{"x":1,"x":2}]}', '{"x":{"a":1,"a":2}}]}', '{"x":NaN}', '{"x":Infinity}',
])
def test_ambiguous_truncated_duplicate_or_nonfinite_json_rejected(text):
    with pytest.raises(ValueError): decode_uncertainty_json(text)


def test_exact_json_is_not_reported_as_syntax_recovery():
    assert decode_uncertainty_json('{"x":1}') == ({'x': 1}, None)


def unlocated_context():
    ctx = context()
    ctx['section']['uncertainties'] = ['旧声明没有绑定任何单元，但实际证据可以消解这条声明。']
    from math_agent.uncertainty_review import build_uncertainty_context
    return build_uncertainty_context(ctx['plan'], ctx['section'], [], ctx['tool_checks'], [], False)


def null_resolution(ctx):
    result = assessment(ctx)
    source = ctx['sources'][0]
    result['items'][0]['evidence'] = [{key: source[key] for key in ('source_key', 'source_sha256')} | {'quote': source['tex']}]
    return result


def test_null_owner_resolution_preserves_null_and_never_grants_repair_authority():
    ctx = unlocated_context(); result = null_resolution(ctx)
    verified = validate_uncertainty_assessment(result, ctx)
    assert verified['items'][0]['unit_id'] is None
    assert not effective_uncertainty_issues(ctx['section'], verified)
    assert ctx['section']['uncertainties']
    result['items'][0].update(disposition='open_actionable', repair_instruction='请仅修改引用所涉及的那个单元以补充证明。')
    with pytest.raises(ValueError): validate_uncertainty_assessment(result, ctx)


@pytest.mark.parametrize('damage', ['no_evidence','prior_only','guess_owner','wrong_quote','wrong_hash','remaining_dependency'])
def test_null_resolution_rejects_unsupported_or_rebound_evidence(damage):
    ctx = unlocated_context(); result = null_resolution(ctx); item = result['items'][0]
    if damage == 'no_evidence': item['evidence'] = []
    elif damage == 'prior_only':
        src = copy.deepcopy(ctx['sources'][0]); src['source_key'] = 'prior:' + src['unit_id'];ctx['sources'].append(src)
        item['evidence'][0]['source_key'] = src['source_key']
    elif damage == 'guess_owner': item['unit_id'] = ctx['sources'][0]['unit_id']
    elif damage == 'wrong_quote': item['evidence'][0]['quote'] = '这是一段并不存在的引文证据。'
    elif damage == 'wrong_hash': item['evidence'][0]['source_sha256'] = '0'*64
    else: item['remaining_dependency'] = True
    with pytest.raises(ValueError): validate_uncertainty_assessment(result, ctx)


def replay_fixture(tmp_path, chapter):
    p, _, _ = direct_guard(tmp_path)
    fixture = FIXTURES/chapter
    old = json.loads((fixture/'state.json').read_bytes())
    folder = p.root/'uncertainty-reviews'/old['identity_hash'][:24]
    folder.mkdir(parents=True)
    for name in ['state.json', *old['dependencies']]: shutil.copyfile(fixture/name, folder/name)
    archive = p.build_root/'provider-failures'/'frozen-invalid.txt'
    if (fixture/'invalid.txt').exists():
        archive.parent.mkdir(parents=True);shutil.copyfile(fixture/'invalid.txt', archive)
    events = json.loads((fixture/'events.json').read_bytes())
    with p.store.transaction() as c:
        for row in events:
            if row['type'] not in ('provider.request','provider.result','math.uncertainty_reviewed'):continue
            value = json.loads(row['payload_json'])
            if row['type'] == 'math.uncertainty_reviewed':value['evidence_key'] = (folder/'state.json').relative_to(p.settings.workspace).as_posix()
            if value.get('invalid_response_archive'):value['invalid_response_archive'] = str(archive)
            c.execute('INSERT INTO events(run_id,type,payload_json,timestamp) VALUES(?,?,?,?)',
                (p.run['id'],row['type'],json.dumps(value,ensure_ascii=False),row['timestamp']))
    p.provider.generate = forbidden
    ctx = json.loads((fixture/'input.json').read_bytes())
    return p, UncertaintyReview(p, ctx), folder, archive


@pytest.mark.parametrize('chapter,expected', [('CH02','resolved_by_current_body'),('CH03','open_dependency')])
def test_real_frozen_responses_replay_with_no_calls_and_preserve_originals(tmp_path, chapter, expected):
    p, guard, old, archive = replay_fixture(tmp_path, chapter)
    hashes = {f.name:digest(f.read_bytes()) for f in old.iterdir()}
    approval = copy.deepcopy(p.store.get_run(p.run['id'])['approval'])
    ordinary = guard.ordinary_review(forbidden,{})
    result, issues = guard.evaluate()
    assert result['assessment']['items'][0]['disposition'] == expected
    assert bool(issues) == (chapter == 'CH03')
    assert ordinary == json.loads((old/'ordinary-review.json').read_bytes())
    assert hashes == {f.name:digest(f.read_bytes()) for f in old.iterdir()}
    assert p.store.get_run(p.run['id'])['approval'] == approval
    assert guard.state['calls'] == 1 and guard.state['provider_calls_during_replay'] == 0
    assert guard.state['status'] == 'REVIEWED'
    assert UncertaintyReview(p, guard.context).evaluate() == (result, issues)
    with p.store.connect() as c:
        assert c.execute("SELECT count(*) FROM events WHERE run_id=? AND type='math.uncertainty_migrated'",(p.run['id'],)).fetchone()[0] == 1
    if chapter == 'CH02':assert result['assessment']['items'][0]['unit_id'] is None
    else:assert result['assessment']['items'][0]['remaining_dependency'] is True


@pytest.mark.parametrize('damage', ['unknown_contract','source_bytes','state_hash','source_context','ordinary_review','no_receipt','no_call','wrong_input_hash','archive_bytes','ambiguous_archive','orphan_state'])
def test_changed_or_unbound_legacy_evidence_blocks_without_model_calls(tmp_path, damage):
    p, guard, old, archive = replay_fixture(tmp_path, 'CH03')
    state = json.loads((old/'state.json').read_bytes())
    if damage == 'unknown_contract': state['identity']['contract']['helper_sha256']='0'*64;write_json(old/'state.json',state)
    elif damage == 'source_bytes': (old/'input.json').write_text('{}')
    elif damage == 'state_hash': state['identity_hash']='0'*64;write_json(old/'state.json',state)
    elif damage == 'source_context':
        value=json.loads((old/'input.json').read_bytes());value['section']['units'][0]['tex']+=' changed';write_json(old/'input.json',value)
    elif damage == 'ordinary_review': (old/'ordinary-review.json').write_text('{}')
    elif damage in ('no_receipt','no_call'):
        with p.store.transaction() as c:c.execute('DELETE FROM events WHERE run_id=? AND type=?',(p.run['id'],'math.uncertainty_reviewed' if damage=='no_receipt' else 'provider.request'))
    elif damage == 'wrong_input_hash':
        with p.store.transaction() as c:
            for row in c.execute("SELECT sequence,payload_json FROM events WHERE run_id=? AND type='provider.request'",(p.run['id'],)).fetchall():
                value=json.loads(row['payload_json']);value['input_hash']='0'*64;c.execute('UPDATE events SET payload_json=? WHERE sequence=?',(json.dumps(value),row['sequence']))
    elif damage == 'archive_bytes': archive.write_text('{}')
    elif damage == 'ambiguous_archive':archive.write_text('{"x":1}{"y":2}')
    elif damage == 'orphan_state':(old/'state.json').unlink()
    with pytest.raises(AgentError) as error:guard.ordinary_review(forbidden,{})
    assert error.value.code == 'UNCERTAINTY_EVIDENCE_BLOCKED'
    assert not guard.path.exists()


@pytest.mark.parametrize('stage', ['state_created','evidence_written','state_reviewed','receipt_written'])
def test_migration_crash_resumes_same_frozen_verdict_without_model_calls(tmp_path, monkeypatch, stage):
    p, guard, old, _ = replay_fixture(tmp_path, 'CH03')
    original_write=guard._write; armed=True
    def crash(path,value):
        nonlocal armed
        original_write(path,value)
        match=(stage=='state_created' and path==guard.path and value.get('status')=='MIGRATING' and not value['dependencies']) or (stage=='evidence_written' and path.name=='response-1.json') or (stage=='state_reviewed' and path==guard.path and value.get('status')=='REVIEWED')
        if armed and match:armed=False;raise KeyboardInterrupt('Injected migration crash')
    monkeypatch.setattr(guard,'_write',crash)
    if stage=='receipt_written':
        original_event=p.store.event
        def event(c,rid,kind,payload=None):
            original_event(c,rid,kind,payload)
            if kind=='math.uncertainty_migrated':raise KeyboardInterrupt('Injected receipt transaction crash')
        monkeypatch.setattr(p.store,'event',event)
    with pytest.raises(KeyboardInterrupt):guard.ordinary_review(forbidden,{})
    if stage=='receipt_written':monkeypatch.setattr(p.store,'event',original_event)
    resumed=UncertaintyReview(p,guard.context)
    resumed.ordinary_review(forbidden,{})
    result,issues=resumed.evaluate()
    assert issues and result['assessment']['items'][0]['disposition']=='open_dependency'


def test_changed_body_is_not_a_legacy_replay(tmp_path):
    p, guard, _, _ = replay_fixture(tmp_path, 'CH03')
    ctx=copy.deepcopy(guard.context);ctx['section']['units'][0]['tex']+=' 新的实际正文。'
    new=UncertaintyReview(p,ctx);new._load()
    assert new.state['status']=='CREATED' and 'migration_source' not in new.state


def test_replayed_source_mutation_after_success_is_detected(tmp_path):
    p,guard,old,_=replay_fixture(tmp_path,'CH03');guard.ordinary_review(forbidden,{})
    (old/'ordinary-review.json').write_text('{}')
    with pytest.raises(AgentError):UncertaintyReview(p,guard.context).evaluate()


def test_replay_cannot_write_after_lease_ends(tmp_path):
    p,guard,_,_=replay_fixture(tmp_path,'CH02')
    p.store.finish(p.job,'FAILED','test',{'code':'PROVIDER_TIMEOUT'})
    with pytest.raises(AgentError):guard.ordinary_review(forbidden,{})
    assert not guard.path.exists()


def test_changed_ordinary_policy_is_not_silently_replayed(tmp_path):
    p,guard,_,_=replay_fixture(tmp_path,'CH03')
    guard.identity['contract']['ordinary_prompt_sha256']='changed'
    with pytest.raises(AgentError):guard.ordinary_review(forbidden,{})
    assert not guard.path.exists()


def test_provider_recovers_only_uncertainty_role_and_archives_original(tmp_path):
    from test_model_routing import make_provider, response
    from math_agent.uncertainty_review import UncertaintyAssessment
    value=assessment(context(),'open_dependency');raw=json.dumps(value,ensure_ascii=False)+']}'
    provider,calls,records,_=make_provider(tmp_path,lambda request:response(raw))
    provider.failure_dir=tmp_path/'archives'
    result=provider.generate('reviewer_uncertainty',context(),UncertaintyAssessment)
    assert result==value and len(calls)==1
    assert not any(x.get('event')=='model_fallback' for x in records)
    recovery=[x for x in records if 'syntax_recovery' in x]
    assert len(recovery)==1
    assert Path(recovery[0]['invalid_response_archive']).read_text(encoding='utf-8')==raw
    assert result['items'][0]['disposition']=='open_dependency'
    provider,calls,records,_=make_provider(tmp_path/'other',lambda request:response(raw),max_schema_repair_attempts=0)
    with pytest.raises(AgentError):provider.generate('reviewer_math',context(),UncertaintyAssessment)
    assert len(calls)==1 and not any('syntax_recovery' in x for x in records)


def test_provider_duplicate_dispositions_cannot_be_hidden_by_json_duplicate_keys(tmp_path):
    from test_model_routing import make_provider,response
    from math_agent.uncertainty_review import UncertaintyAssessment
    raw='{"items":[],"items":'+json.dumps(assessment(context())['items'])+',"limitations":[]}]} '
    provider,calls,records,_=make_provider(tmp_path,lambda request:response(raw))
    with pytest.raises(AgentError) as error:provider.generate('reviewer_uncertainty',context(),UncertaintyAssessment)
    assert error.value.code=='INVALID_MODEL_JSON' and len(calls)==1
    assert not any('syntax_recovery' in x for x in records)
