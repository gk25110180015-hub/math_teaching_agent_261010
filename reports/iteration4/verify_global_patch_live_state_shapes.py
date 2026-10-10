"""Read-only legacy-state preflight; no Store, migration, DB write or model call."""
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from math_agent.pipeline import Pipeline
from math_agent.util import digest

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
path=OUT/'global_repair_contract.candidate.py'
spec=importlib.util.spec_from_file_location('math_agent._global_contract_readonly_preview',path)
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
results={}
for case in ('CH02','CH03'):
    snapshot=OUT/'resume-20260920T143357-e340db'/case/'before.json'
    run=json.loads(snapshot.read_bytes())
    pipeline=object.__new__(Pipeline)
    pipeline.settings=SimpleNamespace(workspace=ROOT/'workspace/iteration2-live',model='gpt-6-astra')
    pipeline.root=pipeline.settings.workspace/'runs'/run['id']
    pipeline.run=run;pipeline.model_id=run['input'].get('model_id','gpt6')
    state_path=pipeline.root/'global-repair-state.json'
    raw=state_path.read_bytes();state=json.loads(raw)
    result={'run_id':run['id'],'state_sha256':digest(raw),'phase':state['phase'],
            'rounds_used':state['rounds_used'],'identity_exact_known_v1':state['identity']==contract.known_legacy_identity(pipeline,run['plan']),
            'approved_plan_hash':run['plan']['hash'],'sections':list(state['sections']),
            'pending_scope':[{'section_id':x['section_id'],'allowed_unit_ids':x['allowed_unit_ids']} for x in state['pending']]}
    try:
        contract._validate_state(pipeline,run['plan'],state)
        result['read_only_shape_and_candidate_hash_check']='PASS'
    except Exception as error:
        result.update(read_only_shape_and_candidate_hash_check='FAIL',error_type=type(error).__name__,error=str(error))
    result['state_unchanged']=state_path.read_bytes()==raw
    results[case]=result
stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
output=OUT/('global-patch-live-shapes-'+stamp+'.json')
output.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'helper_sha256':digest(path.read_bytes()),
    'mode':'READ_ONLY_SHAPE_VALIDATION_NO_MIGRATION','cases':results,'db_access':'NOT_RUN',
    'remote_api':'NOT_RUN','teacher_review':'NOT_RUN'},ensure_ascii=False,indent=2),encoding='utf-8')
print(str(output));print(json.dumps(results,ensure_ascii=False))
