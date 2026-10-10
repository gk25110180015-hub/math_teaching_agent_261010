"""Two synthetic positive/negative archive groups, with every external call blocked."""
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
from types import SimpleNamespace
import uuid

for key in list(os.environ):
    if key.startswith('MATH_AGENT_') or key=='OPENAI_API_KEY':os.environ.pop(key)
ROOT=Path(__file__).resolve().parents[2];REPORTS=Path(__file__).resolve().parent
PACKAGE=REPORTS/'uncertainty-protocol-candidate/validation/package'
sys.path.insert(0,str(PACKAGE))
attempts=[]
def forbidden(*args,**kwargs):
    attempts.append('external or model call');raise AssertionError('No external/model calls in archival replay')
socket.socket.connect=forbidden;socket.create_connection=forbidden;socket.getaddrinfo=forbidden
from math_agent.provider import CompatibleChatProvider
CompatibleChatProvider.generate=forbidden
from math_agent.util import digest,write_json
from math_agent.domain import WrittenSection
from math_agent.uncertainty_review import uncertainty_contract
from math_agent.uncertainty_protocol_recovery import legacy_replay
from math_agent.local_patch import apply_local_patch
from math_agent.lecture_fragments import normalize_written_section
from workflow_recovery_archive import SnapshotEvents,inspect_uncertainty_migrations,inspect_guidance_ledgers

stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
output=REPORTS/'workflow-collector-validation'/stamp;output.mkdir(parents=True,exist_ok=False)
workspace=ROOT/'workspace/t'/('wrc'+stamp[-6:]);workspace.mkdir(parents=True,exist_ok=False)
run_id='synthetic-frozen-recovery-run';root=workspace/'runs'/run_id
fixture=REPORTS/'uncertainty-protocol-candidate/fixtures/CH03'
old=json.loads((fixture/'state.json').read_bytes())
old_folder=root/'uncertainty-reviews'/old['identity_hash'][:24];old_folder.mkdir(parents=True)
for name in ('state.json',*old['dependencies']):shutil.copyfile(fixture/name,old_folder/name)
response=workspace/'b'/run_id[:16]/'provider-failures/frozen-response.txt'
response.parent.mkdir(parents=True);shutil.copyfile(fixture/'invalid.txt',response)
context=json.loads((fixture/'input.json').read_bytes());events=json.loads((fixture/'events.json').read_bytes())
for event in events:
    value=json.loads(event['payload_json'])
    if value.get('invalid_response_archive'):value['invalid_response_archive']=str(response)
    if event['type']=='math.uncertainty_reviewed':value['evidence_key']=(old_folder/'state.json').relative_to(workspace).as_posix()
    event['payload_json']=json.dumps(value,ensure_ascii=False)
snapshot={'run':{'id':run_id,'request_count':153,'input_hash':'synthetic-input'},'plan':context['plan'],
    'approval':{'hash':context['plan']['hash'],'revision':context['plan']['revision']},'budget':{'version':3},
    'jobs':[{'id':'synthetic-guidance-job','kind':'build'}], 'events':events}
identity={'plan_hash':context['plan']['hash'],'plan_revision':context['plan']['revision'],
    'context_hash':digest(context),'contract':uncertainty_contract()}
identity_hash=digest(identity);new_folder=root/'uncertainty-reviews'/identity_hash[:24]
pipeline=SimpleNamespace(root=root,run=snapshot['run'],store=SnapshotEvents(snapshot),
    settings=SimpleNamespace(workspace=workspace),build_root=workspace/'b'/run_id[:16])
guard=SimpleNamespace(folder=new_folder,identity=identity,context=context,p=pipeline)
replay=legacy_replay(guard)
assert replay['assessment.json']['items'][0]['disposition']=='open_dependency'
values={'input.json':context,'migration.json':replay['provenance'],
    **{key:replay[key] for key in ('ordinary-context.json','ordinary-review.json','assessment-input.json','response-1.json','assessment.json')}}
deps={}
for name,value in values.items():
    write_json(new_folder/name,value);deps[name]=digest((new_folder/name).read_bytes())
state={'schema_version':1,'identity':identity,'identity_hash':identity_hash,'status':'REVIEWED',
    'origin_job_id':replay['origin_job_id'],'calls':1,'response_file':'response-1.json',
    'migration_source':replay['source'],'provider_calls_during_replay':0,'teacher_review':'NOT_RUN','dependencies':deps}
write_json(new_folder/'state.json',state)
sequence=max(row['sequence'] for row in events)+1
def event(kind,payload):
    global sequence
    snapshot['events'].append({'sequence':sequence,'type':kind,'timestamp':'2026-09-23T02:00:00+00:00',
                              'payload_json':json.dumps(payload,ensure_ascii=False)})
    sequence+=1
event('math.uncertainty_migrated',{'identity_hash':identity_hash,'source':replay['source'],
    'evidence_key':(new_folder/'state.json').relative_to(workspace).as_posix(),
    'migration_sha256':deps['migration.json'],'provider_calls_during_replay':0,'teacher_review':'NOT_RUN'})

before=WrittenSection.model_validate({'section_id':'S03','units':[
    {'id':'S03.U04','kind':'proof','tex':'原证明需要在本单元补充一条具体依据。'},
    {'id':'S03.U05','kind':'example','tex':'相邻例题保持不变。'}],
    'uncertainties':['S03.U04：原有的证明依据仍需独立检查。']}).model_dump()
candidate=root/'local-repair/S03/original.json';write_json(candidate,before)
global_candidate=root/'global-repairs/r4/s03.json';write_json(global_candidate,before)
global_state={'schema_version':2,'identity':{'plan_hash':context['plan']['hash']},'rounds_used':4,'phase':'checking',
    'pending':[],'sections':{'S03':{'candidate_key':global_candidate.relative_to(workspace).as_posix(),
                                 'candidate_hash':digest(global_candidate.read_bytes())}}}
global_path=root/'global-repair-state.json';global_raw=json.dumps(global_state,ensure_ascii=False,indent=1).encode();global_path.write_bytes(global_raw)
local={'identity':{'plan_hash':context['plan']['hash'],'section_id':'S03'},'pending_issues':[{'unit_id':'S03.U04','message':'Original concern'}],
    'candidate_key':candidate.relative_to(workspace).as_posix(),'candidate_hash':digest(candidate.read_bytes()),'evidence_dependencies':[]}
local_path=root/'local-repair/S03.json';local_raw=json.dumps(local,ensure_ascii=False,indent=1).encode();local_path.write_bytes(local_raw)
binding={'state_key':local_path.relative_to(workspace).as_posix(),'state_sha256':digest(local_raw),'identity':local['identity'],
    'pending_issues_sha256':digest(local['pending_issues']),'last_review_key':None,'last_review_sha256':None,
    'global_state_key':global_path.relative_to(workspace).as_posix(),'global_state_sha256':digest(global_raw)}
request={'expected_plan_revision':context['plan']['revision'],'expected_plan_hash':context['plan']['hash'],
    'action_id':'synthetic-guidance-action','section_id':'S03','expected_candidate_hash':digest(before),
    'unit_ids':['S03.U04'],'instructions':'合成测试：请只补充指定单元的论证，保留原数学疑点和其他单元，不代表正确性通过。','source':'user'}
action={'action_id':request['action_id'],'payload_hash':digest(request),'job_id':'synthetic-guidance-job',
    'plan_hash':context['plan']['hash'],'plan_revision':context['plan']['revision'],'section_id':'S03',
    'candidate_hash':digest(before),'candidate_key':candidate.relative_to(workspace).as_posix(),
    'candidate_file_hash':digest(candidate.read_bytes()),'recovery_binding':binding,'unit_ids':request['unit_ids'],
    'instructions':request['instructions'],'source':'user','actor':'local_user','request_count_preserved':153,
    'budget_version':3,'approval_preserved':True,'teacher_review':'NOT_RUN'}
event('repair.guidance_requested',action)
proposal={'section_id':'S03','replacements':[{'unit_id':'S03.U04','tex':'本单元补充一条待检查的具体论证；此合成内容不表示数学正确。'}]}
after,patch_evidence=apply_local_patch(before,request['unit_ids'],proposal)
normalized,normalization=normalize_written_section({**after,'units':[u for u in after['units'] if u['id'] in request['unit_ids']]})
texts={u['id']:u['tex'] for u in normalized['units']}
for unit in after['units']:
    if unit['id'] in texts:unit['tex']=texts[unit['id']]
guidance=root/'repair-guidance'/digest([action['job_id'],action['action_id']])[:24]
guide_values={'action.json':action,'before.json':before,'proposal.json':proposal,'patch-evidence.json':patch_evidence,
    'normalization.json':normalization,'after.json':after}
guide_deps={}
for name,value in guide_values.items():
    write_json(guidance/name,value);guide_deps[name]=digest((guidance/name).read_bytes())
for name,raw in [('recovery-before.json',local_raw),('global-before.json',global_raw)]:
    (guidance/name).write_bytes(raw);guide_deps[name]=digest(raw)
journal={'schema_version':1,'action_hash':digest(action),'phase':'APPLIED','dependencies':guide_deps,
    'before_hash':digest(before),'after_hash':digest(after),'proposal_number':7,'teacher_review':'NOT_RUN'}
write_json(guidance/'state.json',journal)
event('repair.guidance_applied',{'action_id':action['action_id'],'job_id':action['job_id'],'section_id':'S03',
    'before_hash':digest(before),'after_hash':digest(after),'unit_ids':request['unit_ids'],'source':'user',
    'status':'UNCHECKED_REPAIRED','teacher_review':'NOT_RUN'})
# The real mutable recovery states can advance; the archived original bytes
# must be checked against their immutable snapshots, never current-state bytes.
write_json(local_path,{'advanced':True});write_json(global_path,{'advanced':True})
positive_migration=inspect_uncertainty_migrations(workspace,snapshot,output/'positive')
positive_guidance=inspect_guidance_ledgers(workspace,snapshot,output/'positive')
assert positive_migration['all_files_verified'],positive_migration
assert positive_guidance['all_files_verified'],positive_guidance
assert positive_migration['records'][0]['disposition_counts']=={'open_dependency':1}
assert positive_guidance['records'][0]['saved_patch_replay']=='PASS_NO_MODEL_OR_COMPILER_CALL'
response.write_bytes(b'{}');(guidance/'after.json').write_bytes(b'{}')
negative_migration=inspect_uncertainty_migrations(workspace,snapshot,output/'negative')
negative_guidance=inspect_guidance_ledgers(workspace,snapshot,output/'negative')
assert not negative_migration['all_files_verified'] and not negative_guidance['all_files_verified']
old_collector=REPORTS/'collector-history/before-guidance-migration-20260923-020026-b3fb51/collect_final_live_evidence.py'
current_collector=REPORTS/'collect_final_live_evidence.py'
old_tree=ast.parse(old_collector.read_text(encoding='utf-8'));new_tree=ast.parse(current_collector.read_text(encoding='utf-8'))
def expressions(tree,name):
    return [ast.dump(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
for name in ('feedback_final_ready','service_feedback_matches'):
    assert expressions(old_tree,name)==expressions(new_tree,name)
for name in ('feedback_delivery_match','inspect_feedback_receipts'):
    get=lambda tree:next(ast.dump(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    assert get(old_tree)==get(new_tree)
assert not attempts
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'status':'PASS','synthetic_groups':2,'positive':['frozen CH03 verdict/call/archive migration','guided patch and exact original raw state snapshots'],
    'negative':['modified provider response archive rejected','modified guided output rejected'],
    'old_feedback_body_and_api_binding_unchanged':True,'real_db':'NOT_ACCESSED','external_attempts':len(attempts),
    'model_calls':0,'windows_compile':'NOT_RUN','browser':'NOT_RUN','teacher_review':'NOT_RUN',
    'collector_sha256':sha(current_collector),'helper_sha256':sha(REPORTS/'workflow_recovery_archive.py'),
    'original_archival_helper_sha256':sha(REPORTS/'recovery_evidence_archive.py'),
    'validator_package':str(PACKAGE),'uncertainty_replay_source_sha256':sha(PACKAGE/'math_agent/uncertainty_protocol_recovery.py')}
write_json(output/'result.json',result)
print(str(output));print(json.dumps(result,ensure_ascii=False))
