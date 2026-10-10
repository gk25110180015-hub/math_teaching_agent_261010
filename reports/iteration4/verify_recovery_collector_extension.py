"""Two synthetic archive checks; no live DB, HTTP, compiler or model use."""
import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import uuid

from math_agent.util import digest,write_json
from recovery_evidence_archive import inspect_global_migrations,inspect_uncertainty_ledgers

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
evidence=OUT/'recovery-collector-validation'/stamp;evidence.mkdir(parents=True,exist_ok=False)
workspace=ROOT/'workspace/t'/('rcl'+stamp[-6:]);workspace.mkdir(parents=True,exist_ok=False)
helper_path=OUT/'uncertainty_review.candidate.py'
spec=importlib.util.spec_from_file_location('math_agent.uncertainty_review',helper_path)
helper=importlib.util.module_from_spec(spec);sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
run_id='synthetic-recovery-run';run_root=workspace/'runs'/run_id
plan={'hash':'synthetic-approved-plan','revision':2,'sections':[{'id':'S01','title':'S01','prerequisites':[]}]}
approval={'hash':plan['hash'],'revision':2,'input_hash':'synthetic-input','action_id':'synthetic-explicit-approval'}
snapshot={'run':{'id':run_id,'input_hash':'synthetic-input','request_count':118},
          'plan':plan,'approval':approval,'events':[]}
section={'section_id':'S01','units':[{'id':'S01.U01','kind':'explanation',
    'tex':'当前假设明确规定正整数具有无上界性质，因此可以选择所需的正整数。','relates_to':None}],
    'uncertainties':['S01.U01：需核实本段存在性依据是否已经说明。'],'calculations':[]}
candidate=run_root/'global-repairs/r3-synthetic/S01-before.json';write_json(candidate,section)
before={'schema_version':1,'identity':{'plan_hash':plan['hash'],'old':'synthetic-known-contract'},
    'rounds_used':3,'phase':'repair_pending','issues':[{'unit_id':'S01.U01','severity':'review','message':'retained issue'}],
    'pending':[{'section_id':'S01','allowed_unit_ids':['S01.U01']}],
    'sections':{'S01':{'candidate_key':candidate.relative_to(workspace).as_posix(),'candidate_hash':digest(candidate.read_bytes())}}}
old_bytes=json.dumps(before,ensure_ascii=False,indent=2).encode()
new_identity={'plan_hash':plan['hash'],'repair_contract_version':2,'new':'synthetic-strict-patch'}
kind='known_full_section_v1_to_strict_patch_v2';key=digest([kind,run_id,digest(old_bytes),new_identity])
folder=run_root/'global-repairs/contract-migrations'/key[:24];folder.mkdir(parents=True)
evidence_key=(folder/'evidence.json').relative_to(workspace).as_posix()
after={**before,'schema_version':2,'identity':new_identity,'contract_migration':{'id':key,'evidence_key':evidence_key}}
after_bytes=json.dumps(after,ensure_ascii=False,indent=2).encode()
(folder/'before.json').write_bytes(old_bytes);(folder/'after.json').write_bytes(after_bytes)
(run_root/'global-repair-state.json').write_bytes(after_bytes)
kept={k:v for k,v in before.items() if k not in ('schema_version','identity','contract_migration')}
migration={'id':key,'migration':kind,'run_id':run_id,'plan_hash':plan['hash'],'plan_revision':2,
    'approval_hash':digest(approval),'input_hash':'synthetic-input','request_count_preserved':118,
    'rounds_used_preserved':3,'phase_preserved':'repair_pending','pending_scope':before['pending'],
    'before_sha256':digest(old_bytes),'after_sha256':digest(after_bytes),'preserved_payload_hash':digest(kept),
    'from_identity':before['identity'],'to_identity':new_identity,'evidence_key':evidence_key,
    'before_key':(folder/'before.json').relative_to(workspace).as_posix(),
    'after_key':(folder/'after.json').relative_to(workspace).as_posix(),'teacher_review':'NOT_RUN'}
write_json(folder/'evidence.json',migration)
snapshot['events'].append({'sequence':1,'timestamp':'synthetic-time','type':'global.repair_contract_migrated',
                          'payload_json':json.dumps(migration)})
context=helper.build_uncertainty_context(plan,section,[],{'issues':[]},[],mock=True)
identity={'plan_hash':plan['hash'],'plan_revision':2,'context_hash':digest(context),'contract':{'synthetic':True}}
uncertainty_key=digest(identity);ledger=run_root/'uncertainty-reviews'/uncertainty_key[:24];ledger.mkdir(parents=True)
doubt=context['declared_doubts'][0];source=context['sources'][0]
response={'items':[{'uncertainty_id':doubt['uncertainty_id'],'unit_id':doubt['unit_id'],
    'disposition':'resolved_by_current_body','reason':'合成响应仅核对已提供的正文陈述与逐字证据，不代表真实教师裁定。',
    'evidence':[{'source_key':source['source_key'],'source_sha256':source['source_sha256'],'quote':source['tex']}],
    'remaining_dependency':False,'repair_instruction':None}],'limitations':['SYNTHETIC archive fixture; no real review.']}
assessment=helper.validate_uncertainty_assessment(response,context)
ordinary={'issues':[],'checked_unit_ids':['S01.U01'],'limitations':['synthetic']}
values={'input.json':context,'ordinary-context.json':{'section':section},'ordinary-review.json':ordinary,
        'assessment-input.json':{**context,'ordinary_review':ordinary},'response-1.json':response,'assessment.json':assessment}
deps={}
for name,value in values.items():
    write_json(ledger/name,value);deps[name]=digest((ledger/name).read_bytes())
state={'schema_version':1,'identity':identity,'identity_hash':uncertainty_key,'status':'REVIEWED',
       'calls':1,'origin_job_id':'synthetic-job','teacher_review':'NOT_RUN','response_file':'response-1.json','dependencies':deps}
write_json(ledger/'state.json',state)
payload={'job_id':'synthetic-job','origin_job_id':'synthetic-job','plan_hash':plan['hash'],'plan_revision':2,
    'identity_hash':uncertainty_key,'status':'REVIEWED','evidence_key':(ledger/'state.json').relative_to(workspace).as_posix(),
    'evidence_sha256':digest((ledger/'state.json').read_bytes()),'teacher_review':'NOT_RUN'}
snapshot['events'].append({'sequence':2,'timestamp':'synthetic-time','type':'math.uncertainty_reviewed','payload_json':json.dumps(payload)})
positive_global=inspect_global_migrations(workspace,snapshot,evidence/'positive')
positive_uncertainty=inspect_uncertainty_ledgers(workspace,snapshot,evidence/'positive')
assert positive_global['all_files_verified'] and positive_uncertainty['all_files_verified']
assert positive_uncertainty['records'][0]['saved_response_validation']=='PASS_NO_NEW_MODEL_CALL'
assert positive_uncertainty['records'][0]['current_delivery_body_binding']=='NOT_INFERRED_FROM_THIS_LEDGER'
candidate.write_bytes(b'{}');(ledger/'response-1.json').write_bytes(b'{}')
negative_global=inspect_global_migrations(workspace,snapshot,evidence/'negative')
negative_uncertainty=inspect_uncertainty_ledgers(workspace,snapshot,evidence/'negative')
assert not negative_global['all_files_verified'] and not negative_uncertainty['all_files_verified']
old=OUT/'collector-history/before-recovery-20260920-192828-05f1a4/collect_final_live_evidence.py'
new=OUT/'collect_final_live_evidence.py'
old_tree=ast.parse(old.read_text(encoding='utf-8'));new_tree=ast.parse(new.read_text(encoding='utf-8'))
def assignment(tree,name):
    return [ast.dump(node.value) for node in ast.walk(tree) if isinstance(node,ast.Assign)
            and any(isinstance(target,ast.Name) and target.id==name for target in node.targets)]
assert assignment(old_tree,'feedback_final_ready')==assignment(new_tree,'feedback_final_ready')
assert assignment(old_tree,'service_feedback_matches')==assignment(new_tree,'service_feedback_matches')
result={'status':'PASS','synthetic_checks':2,'positive':{'migration_archive':'PASS','uncertainty_archive_and_saved_replay':'PASS'},
    'negative':{'changed_migration_candidate':'BLOCKED_AS_EXPECTED','changed_uncertainty_response':'BLOCKED_AS_EXPECTED'},
    'existing_feedback_body_and_api_binding_unchanged':True,'api_calls':0,'db_access':'NOT_RUN',
    'windows_compile':'NOT_RUN','browser':'NOT_RUN','teacher_review':'NOT_RUN',
    'old_collector_sha256':digest(old.read_bytes()),'collector_sha256':digest(new.read_bytes()),
    'archival_helper_sha256':digest((OUT/'recovery_evidence_archive.py').read_bytes()),
    'pure_uncertainty_helper_sha256':digest(helper_path.read_bytes())}
write_json(evidence/'result.json',result)
print(str(evidence));print(json.dumps(result,ensure_ascii=False))
