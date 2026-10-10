"""Synthetic-only validation of final receipt/body collection; no live DB or API."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import sys
import uuid

from math_agent.pipeline import render_lecture
from math_agent.util import canonical, digest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
evidence = OUT/'feedback-collector-validation'/stamp
evidence.mkdir(parents=True, exist_ok=False)
workspace = ROOT/'workspace/t'/('fbc-'+stamp[-6:])
workspace.mkdir(parents=True, exist_ok=False)
helper = OUT/'feedback_review.candidate.py'
spec = importlib.util.spec_from_file_location('math_agent.feedback_review', helper)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
collector_path = OUT/'collect_final_live_evidence.py'
compile(collector_path.read_text(encoding='utf-8'), str(collector_path), 'exec')
collector = runpy.run_path(str(collector_path))

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2),encoding='utf-8')
    return digest(path.read_bytes())

plan_base = {'revision':2,'title':'Synthetic receipt/body snapshot','provider':'mock',
    'objectives':['说明基础概念与合法条件。'], 'lecture':{'answers_location':'end'},
    'sections':[{'id':'S01','title':'初值','objectives':['给出初值说明。']},
                {'id':'S02','title':'参数范围','objectives':['说明参数域与边界。']}]}
plan = {**plan_base,'hash':digest(plan_base)}
feedback = '1. 请补充参数域与边界说明。'
action = {'job_id':'job-current','plan_hash':plan['hash'],'plan_revision':2,
          'feedback':feedback,'feedback_source':'agent_audit'}
event0 = {'sequence':1,'type':'checks.rerun_requested','timestamp':'2026-09-20T18:00:00+00:00','payload_json':canonical(action)}
source_event = {'sequence':1,'timestamp':event0['timestamp'],'payload_sha256':digest(event0['payload_json']),
                'job_id':'job-current','plan_hash':plan['hash'],'plan_revision':2}
old_units = [{'id':'S01.U01','kind':'explanation','tex':'本节已有初值说明。','relates_to':None},
             {'id':'S02.U01','kind':'explanation','tex':'当前仅给具体参数例子。','relates_to':None}]
new_units = copy.deepcopy(old_units)
new_units[1]['tex'] = '一般参数域与边界现已补齐。'

def make_receipt(units, sequence, pending=False):
    record = {'feedback':feedback,'feedback_source':'agent_audit','source_event':source_event}
    context = module.build_feedback_context(plan,units,record,mock=False)
    identity = {'job_id':'job-current','plan_hash':plan['hash'],'plan_revision':2,
        'feedback_hash':digest(feedback),'context_hash':digest(context),'contract':{'synthetic':True,'variant':sequence}}
    key = digest(identity)
    folder = workspace/'runs'/'synthetic-run'/'feedback-reviews'/key[:24]
    improved = units == new_units
    item = {'id':'F1','status':'satisfied' if improved else 'supported_improvement',
        'reason':'离线控制用例：依当前所提供的正文快照核对教学内容。',
        'unit_ids':['S02.U01'],'repair_unit_ids':[] if improved else ['S02.U01'],
        'unit_evidence':[{'unit_id':'S02.U01','quote':units[1]['tex'],'kind':'statement'}],
        'objective_evidence':[{'section_id':'S02','field':'objectives','quote':plan['sections'][1]['objectives'][0]}],
        'repair_instruction':None if improved else '仅在现有单元补足参数域与边界说明。'}
    if pending:
        item.update(status='unresolved',unit_ids=[],repair_unit_ids=[],unit_evidence=[],objective_evidence=[],repair_instruction=None)
    assessment = {'items':[item],'limitations':['Synthetic only; no teacher or model assessment.']}
    receipt = {'schema_version':1,'job_id':'job-current','plan_hash':plan['hash'],'plan_revision':2,
        'feedback_hash':digest(feedback),'identity_hash':key,'status':'transport_pending' if pending else 'reviewed',
        **assessment,'teacher_review':'NOT_RUN','mock':False}
    deps = {name:write(folder/name,value) for name,value in (
        ('input.json',context),('response-1.json',assessment),('receipt-1.json',receipt))}
    state = {'identity':identity,'identity_hash':key,'status':'TRANSPORT_PENDING' if pending else 'REVIEWED',
        'response_file':'response-1.json','receipt_file':'receipt-1.json','dependencies':deps}
    write(folder/'state.json',state)
    payload = {**receipt,'evidence_key':(folder/'receipt-1.json').relative_to(workspace).as_posix(),
               'evidence_sha256':deps['receipt-1.json']}
    return {'sequence':sequence,'type':'feedback.reviewed','timestamp':'2026-09-20T18:01:00+00:00','payload_json':canonical(payload)}

old_event,new_event = make_receipt(old_units,2),make_receipt(new_units,3)
section_pairs = [(spec,{'units':[unit]}) for spec,unit in zip(plan['sections'],new_units)]
tex = workspace/'delivery/lecture.tex';tex.parent.mkdir(parents=True)
tex.write_bytes(render_lecture(plan['title'],section_pairs,plan).encode('utf-8'))
mapping = workspace/'delivery/source_map.json'
write(mapping,{'sections':[{'id':s['id'],'units':[u['id']]} for s,u in zip(plan['sections'],new_units)]})
snapshot = {'run':{'id':'synthetic-run'},'plan':{'revision':2,'hash':plan['hash'],'canonical_json':canonical(plan_base)},
    'approval':{'revision':2,'hash':plan['hash']},'jobs':[{'id':'job-current','kind':'build','status':'done','_rowid':1}],
    'events':[event0,old_event,new_event], 'artifacts':[
        {'artifact_id':'tex-current','name':'lecture.tex','storage_key':'delivery/lecture.tex','status':'draft','sha256':digest(tex.read_bytes())},
        {'artifact_id':'map-current','name':'source_map.json','storage_key':'delivery/source_map.json','status':'draft','sha256':digest(mapping.read_bytes())}]}
checks = {}
results = {}
def inspect(name, snap):
    result = collector['inspect_feedback_receipts'](workspace,snap,evidence/name)
    results[name] = result
    return result

current = inspect('latest',snapshot)
checks['last_receipt_not_first_response'] = current['current']['event_sequence']==3 and current['current']['status']=='CURRENT_DELIVERY_VERIFIED'
checks['closed_current_feedback'] = current['current']['no_pending_improvements'] is True
checks['historical_receipts_archived'] = current['recorded_receipts']==2 and current['all_receipt_files_verified']
earlier = copy.deepcopy(snapshot);earlier['events'].pop()
checks['old_body_not_current'] = inspect('earlier-only',earlier)['current']['status']=='NOT_CURRENT_DELIVERY'
empty = copy.deepcopy(snapshot)
empty['events'].append({'sequence':4,'type':'checks.rerun_requested','timestamp':event0['timestamp'],'payload_json':canonical({**action,'feedback':''})})
checks['empty_feedback_withdraws_old_result'] = inspect('empty-feedback',empty)['current']['status']=='NOT_APPLICABLE'
other_job = copy.deepcopy(snapshot);other_job['jobs'].append({'id':'new-job','kind':'build','status':'queued','_rowid':2})
checks['new_job_does_not_inherit_old_receipt'] = inspect('new-job',other_job)['current']['status']=='LATEST_FEEDBACK_NOT_BOUND_TO_CURRENT_JOB_AND_APPROVAL'
malformed = copy.deepcopy(snapshot);malformed['events'].append({'sequence':4,'type':'feedback.reviewed','timestamp':event0['timestamp'],'payload_json':'{'})
checks['malformed_latest_never_falls_back'] = inspect('malformed-latest',malformed)['current']['status']=='INVALID_CURRENT_RECEIPT'
pending = copy.deepcopy(snapshot);pending['events'].append(make_receipt(new_units,4,pending=True))
pending_result = inspect('pending',pending)
checks['pending_is_not_closed_even_when_body_matches'] = pending_result['current']['status']=='CURRENT_DELIVERY_VERIFIED' and pending_result['current']['no_pending_improvements'] is False
saved_tex = tex.read_bytes();tex.write_bytes(saved_tex+b'% synthetic drift\n')
checks['changed_delivery_sha_rejected'] = inspect('changed-tex',snapshot)['current']['status']=='NOT_CURRENT_DELIVERY'
tex.write_bytes(saved_tex)
latest_path = workspace/json.loads(new_event['payload_json'])['evidence_key']
latest_path.write_bytes(latest_path.read_bytes()+b' ')
checks['corrupt_latest_receipt_never_falls_back'] = inspect('corrupt-receipt',snapshot)['current']['status']=='INVALID_CURRENT_RECEIPT'
report = {'status':'PASS' if all(checks.values()) else 'NOT_PASS','checks':checks,'results':results,
    'collector_sha256':digest(collector_path.read_bytes()),'helper_candidate_sha256':digest(helper.read_bytes()),
    'workspace':str(workspace),'real_api':'NOT_RUN','live_database_read':'NOT_RUN','windows_compile':'NOT_RUN',
    'teacher_review':'NOT_RUN','final_collection':'NOT_RUN'}
write(evidence/'result.json',report)
print(json.dumps({'status':report['status'],'checks':checks,'evidence':str(evidence)},ensure_ascii=False))
assert report['status']=='PASS'
