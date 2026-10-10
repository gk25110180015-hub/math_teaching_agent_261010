"""Read-only pre-deployment evidence freeze; no Store, API or compiler calls."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
SNAPSHOT = ROOT / 'reports/iteration4/CH02-feedback-tracking/snapshot-20260920-182420-770058.json'
OUT = ROOT / 'reports/iteration4/CH02-pre-thirddeploy-baseline.json'


def digest(path):
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'stable_read': path.read_bytes() == data}


snapshot = json.loads(SNAPSHOT.read_bytes())
c = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
c.execute('PRAGMA query_only=ON')
c.execute('BEGIN')
run = dict(c.execute('SELECT id,status,stage,request_count,active_plan_revision,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
assert run == snapshot['run'], 'Run changed after snapshot; capture a new baseline explicitly.'
events = [dict(r) for r in c.execute('SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? AND sequence>=1882 ORDER BY sequence', (RID,))]
artifacts = [dict(r) for r in c.execute("SELECT * FROM artifacts WHERE run_id=? AND name IN ('lecture.pdf','lecture.tex','failure_diagnostic.json') ORDER BY created_at DESC,rowid DESC", (RID,))]
current_pdfs = [dict(r) for r in c.execute("SELECT artifact_id,status,storage_key,sha256 FROM artifacts WHERE run_id=? AND name='lecture.pdf' AND status!='superseded'", (RID,))]
c.rollback()
c.close()

last = snapshot['sections'][-1]
source = WS / last['output']['source_key']
pdf = Path(last['output']['report']['compile']['pdf_path'])
assert digest(source)['sha256'] == last['output']['source_hash']
assert digest(pdf)['sha256'] == last['output']['report']['compile']['pdf_sha256']
source_text = source.read_text(encoding='utf-8')
unit_presence = []
for section in snapshot['sections']:
    for unit in section['output']['generated']['units']:
        unit_presence.append({'unit_id': unit['id'], 'tex_sha256': hashlib.sha256(unit['tex'].encode()).hexdigest(),
                              'verbatim_in_cumulative_source': unit['tex'].strip() in source_text})
assert all(u['verbatim_in_cumulative_source'] for u in unit_presence)

result = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'PRE_THIRD_DEPLOYMENT_FAILED_RUN_BASELINE_NOT_FINAL_DELIVERY',
    'run': run, 'snapshot': digest(SNAPSHOT),
    'latest_registered_current_pdf': current_pdfs,
    'historical_registered_artifacts': [{**a, 'actual_file': digest(WS / a['storage_key'])} for a in artifacts],
    'latest_cumulative_section_compile': {
        'classification': 'EXISTING_PRODUCT_WINDOWS_XELATEX_PASS_NOT_FINAL_CHAPTER',
        'section_id': 'S05', 'checkpoint_rowid': last['latest_checkpoint']['rowid'],
        'page_count': last['output']['report']['compile']['page_count'],
        'source': digest(source), 'pdf': digest(pdf),
        'report': last['output']['report']['compile'], 'unit_presence': unit_presence,
    },
    'changes_vs_pre_feedback': [
        {'section_id': s['section_id'], 'checkpoint_rowid': s['latest_checkpoint']['rowid'],
         'phase': s['local_recovery']['value']['phase'], 'candidate_sha256': s['candidate']['sha256'],
         'candidate_matches_checkpoint': s['candidate_equals_checkpoint'],
         'changes': s['changed_vs_pre_feedback'],
         'non_unit_fields_changed': s['non_unit_fields_changed']}
        for s in snapshot['sections']
    ],
    'failure_events': [{**e, 'payload': json.loads(e['payload_json'])} for e in events],
    'new_api_calls': 0, 'new_compile': 'NOT_RUN',
    'final_agent_visual': 'NOT_RUN', 'teacher_acceptance': 'NOT_RUN',
    'snapshot_first_write_failure': 'PermissionError from workspace sandbox; same read-only script succeeded after authorized report-directory escalation. No production or DB mutation.',
}
with OUT.open('x', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(json.dumps({'output': str(OUT), 'run': run, 'current_registered_pdf_count': len(current_pdfs),
    'cumulative_pdf_sha256': digest(pdf)['sha256'], 'cumulative_source_sha256': digest(source)['sha256'],
    'verified_units_in_source': len(unit_presence)}, ensure_ascii=False, indent=2))
