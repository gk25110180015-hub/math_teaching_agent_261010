"""Read-only CH02 tracking after deployment three; no task/production mutation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
JOB = '4678ed20f5c44ad89b289ffcee4d8143'
BASELINE = ROOT / 'reports/iteration4/CH02-feedback-tracking/snapshot-20260920-182420-770058.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(path, parse=True):
    path = path.resolve()
    assert path.is_relative_to(WS.resolve()) or path.is_relative_to((ROOT / 'reports').resolve())
    data = path.read_bytes()
    result = {'path': str(path), 'sha256': sha(data), 'stable_read': path.read_bytes() == data}
    if parse:
        result['value'] = json.loads(data)
    return result


base = json.loads(BASELINE.read_bytes())
old_sections = {s['section_id']: s['output']['generated'] for s in base['sections']}
c = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
c.execute('PRAGMA query_only=ON')
c.execute('BEGIN')
run = dict(c.execute('SELECT id,status,stage,request_count,active_plan_revision,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
job = dict(c.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (JOB, RID)).fetchone())
rows = [dict(c.execute('SELECT rowid,* FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (RID, 'section.S0' + str(i))).fetchone()) for i in range(1, 6)]
events = [dict(r) for r in c.execute('SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? AND sequence>1895 ORDER BY sequence', (RID,))]
artifacts = [dict(r) for r in c.execute("SELECT * FROM artifacts WHERE run_id=? AND name IN ('lecture.pdf','lecture.tex','failure_diagnostic.json') ORDER BY created_at DESC,rowid DESC", (RID,))]
c.rollback()
c.close()
sections = []
current = {}
for row in rows:
    output = json.loads(row.pop('output_json'))
    sid = row['step_key'].split('.')[1]
    state = capture(WS / 'runs' / RID / 'local-repair' / (sid + '.json'))
    candidate = capture(WS / state['value']['candidate_key'])
    assert candidate['sha256'] == state['value']['candidate_hash']
    old = {u['id']: u for u in old_sections[sid]['units']}
    new = {u['id']: u for u in candidate['value']['units']}
    current.update(new)
    changes = [{'unit_id': uid, 'before': old.get(uid), 'after': new.get(uid)}
               for uid in dict.fromkeys([*old, *new]) if old.get(uid) != new.get(uid)]
    review_key = state['value'].get('last_review_key')
    sections.append({'section_id': sid, 'latest_checkpoint': row, 'output': output,
        'local_recovery': state, 'candidate': candidate,
        'candidate_matches_checkpoint': candidate['value'] == output['generated'],
        'changed_vs_pre_thirddeploy': changes,
        'last_review': capture(WS / review_key) if review_key else None})
receipts = []
for event in events:
    payload = json.loads(event.pop('payload_json'))
    event['payload'] = payload
    if event['type'] != 'feedback.reviewed':
        continue
    evidence = capture(WS / payload['evidence_key'])
    assert evidence['sha256'] == payload['evidence_sha256']
    folder = Path(evidence['path']).parent
    state = capture(folder / 'state.json')
    supplied = capture(folder / 'input.json')
    original_units = supplied['value']['units']
    supplied_units = {u['id']: u for u in original_units}
    assert len(supplied_units) == len(original_units)
    receipts.append({'event_sequence': event['sequence'], 'event_timestamp': event['timestamp'],
        'receipt': evidence, 'state': state, 'input': supplied,
        'response': capture(folder / state['value']['response_file']) if state['value'].get('response_file') else None,
        'body_unit_count': len(supplied_units),
        'body_diff_from_current_candidates': [uid for uid in dict.fromkeys([*supplied_units, *current]) if supplied_units.get(uid) != current.get(uid)],
        'job_matches': payload['job_id'] == JOB,
        'plan_matches': payload['plan_hash'] == sections[0]['local_recovery']['value']['identity']['plan_hash']})
result = {'created_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'POST_THIRD_DEPLOYMENT_READ_ONLY_TRACKING_NOT_FINAL_ACCEPTANCE',
    'baseline': {'path': str(BASELINE), 'sha256': sha(BASELINE.read_bytes())},
    'run': run, 'job': job, 'sections': sections, 'events': events,
    'global_recovery': capture(WS / 'runs' / RID / 'global-repair-state.json'),
    'feedback_receipts': receipts,
    'artifacts': [{**a, 'file': capture(WS / a['storage_key'], parse=False)} for a in artifacts],
    'new_api_calls_by_auditor': 0, 'new_compile_by_auditor': 'NOT_RUN',
    'agent_visual_review': 'NOT_RUN', 'teacher_review': 'NOT_RUN'}
folder = ROOT / 'reports/iteration4/CH02-post-thirddeploy-tracking'
folder.mkdir(exist_ok=True)
dest = folder / ('snapshot-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.json')
dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'snapshot': str(dest), 'run': run,
    'sections': [{'id': s['section_id'], 'rowid': s['latest_checkpoint']['rowid'],
        'phase': s['local_recovery']['value']['phase'],
        'candidate_matches_checkpoint': s['candidate_matches_checkpoint'],
        'changed_unit_ids': [u['unit_id'] for u in s['changed_vs_pre_thirddeploy']]} for s in sections],
    'receipts': [{'sequence': r['event_sequence'], 'status': r['receipt']['value']['status'],
        'items': [{k:i[k] for k in ('id','status','repair_unit_ids')} for i in r['receipt']['value']['items']],
        'body_diff_from_current_candidates': r['body_diff_from_current_candidates']} for r in receipts]}, ensure_ascii=False, indent=2))
