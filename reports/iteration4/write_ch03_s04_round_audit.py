"""Read-only S04.U03 round 1/2/3 audit, preserving each actual text and review."""
import difflib
import hashlib
import json
import sqlite3
from datetime import datetime,timezone
from pathlib import Path

P=Path(__file__).resolve().parents[2]
O=Path(__file__).parent
W=P/'workspace/iteration2-live'
R=W/'runs/a45be503af594ce8aae0bb1e4c30184b'


def h(data):
    if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(data).hexdigest()


def record(path):
    raw=path.read_bytes()
    return {'path':str(path),'project_relative_path':path.relative_to(P).as_posix(),
            'raw_sha256':h(raw),'value':json.loads(raw)}


targets=[('before_round_1',R/'global-repairs/r1-37ae927f/S04-before.json'),
         ('round_1_accepted',R/'global-repairs/r1-37ae927f/S04-0df22531-candidate.json'),
         ('round_1_locally_checked',R/'global-repairs/r1-37ae927f/S04-locally-checked-c30ac4fa.json'),
         ('before_round_2',R/'global-repairs/r2-e4e359cf/S04-before.json'),
         ('round_2_locally_checked',R/'global-repairs/r2-e4e359cf/S04-locally-checked-cc72d851.json'),
         ('before_round_3',R/'global-repairs/r3-b62b4971/S04-before.json')]
versions=[]
for label,path in targets:
    item=record(path);data=item.pop('value')
    unit=next(u for u in data['units'] if u['id']=='S04.U03')
    item.update(label=label,unit=unit,unit_tex_sha256=h(unit['tex'].encode()))
    versions.append(item)
assert versions[1]['unit']==versions[2]['unit']==versions[3]['unit']
assert versions[4]['unit']==versions[5]['unit']
changes=[]
for left,right in [(0,1),(3,4),(4,5)]:
    a=json.loads(Path(versions[left]['path']).read_bytes());b=json.loads(Path(versions[right]['path']).read_bytes())
    ids=[u['id'] for u,v in zip(a['units'],b['units']) if u!=v]
    assert len(a['units'])==len(b['units'])
    changes.append({'from':versions[left]['label'],'to':versions[right]['label'],'changed_unit_ids':ids,
        'diff':''.join(difflib.unified_diff(versions[left]['unit']['tex'].splitlines(keepends=True),
            versions[right]['unit']['tex'].splitlines(keepends=True),fromfile=versions[left]['label'],tofile=versions[right]['label']))})
review_paths=[R/'global-7e7982c6-2-review-0.json',R/'global-7e7982c6-3-review-0.json',
    R/'global-5cf5d02e-2-review-0.json',W/'b/a45be503af594ce8/sS04_d8112be51cdd/local-0-review-0.json',
    R/'global-04fbc8be-2-review-0.json',R/'chapter-coverage-04fbc8be-review-0.json']
reviews=[record(path) for path in review_paths]
c=sqlite3.connect((W/'agent.db').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('BEGIN')
run=dict(c.execute('SELECT id,status,stage,request_count,updated_at FROM runs WHERE id=?',(R.name,)).fetchone())
events=[dict(row) for row in c.execute("SELECT sequence,timestamp,payload_json FROM events WHERE run_id=? AND type='provider.result' ORDER BY sequence",(R.name,))]
c.rollback();c.close()
for item in reviews:
    output_hash=h(item['value'])
    matched=[]
    for event in events:
        payload=json.loads(event['payload_json'])
        if payload.get('output_hash')==output_hash:
            matched.append({'sequence':event['sequence'],'timestamp':event['timestamp'],'payload':payload})
    item['provider_output_matches']=matched
    item['S04_U03_issues']=[issue for issue in item['value']['issues'] if issue.get('unit_id')=='S04.U03']
state=record(R/'global-repair-state.json');state['value']={k:v for k,v in state['value'].items() if k!='pending'}
report={'schema_version':1,'captured_at':datetime.now(timezone.utc).isoformat(),'run_snapshot':run,
    'status':'INTERMEDIATE_ROUND_AUDIT_NOT_FINAL','api_calls':0,'source_mutations':0,'product_mutations':0,
    'versions':versions,'changes':changes,'reviews':reviews,'global_state':state,
    'round_2_local_patch':record(W/'b/a45be503af594ce8/sS04_d8112be51cdd/repair-2-patch.json'),
    'findings':{
        'definite_text_regression':'NOT_FOUND',
        'repeated_repair_of_the_identical_resolved_issue':'NOT_FOUND',
        'round_1_undefined_point_issue':'CLARITY_REQUEST_OVERSTATED_AS_LOGICAL_INCONSISTENCY',
        'round_1_one_sided_infinite_quantifiers':'ACTUAL_ADDED_FORMAL_DEFINITION',
        'round_2_infinite_discontinuity_example':'ACTUAL_ADDED_TEACHING_APPLICATION_WITH_WARNING_REVIEW_SEVERITY_DRIFT',
        'round_3_two_sided_assumption':'GENERAL_DEFINITION_SCOPE_GAP_NOT_COUNTEREXAMPLE_TO_CORRECT_NARROW_STATEMENT',
        'round_3_repair_after_capture':'NOT_ASSESSED'},
    'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN','agent_visual_review':'NOT_RUN'}
target=O/'CH03-S04-round1-to3-audit.json'
assert not target.exists()
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report':str(target),'run':run,'review_models':[
    {'file':Path(item['path']).name,'models':[x['payload'].get('reported_model',x['payload'].get('model')) for x in item['provider_output_matches']]}
    for item in reviews]},ensure_ascii=False))
