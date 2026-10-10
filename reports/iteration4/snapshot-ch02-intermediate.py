"""Read-only current CH02 checkpoint snapshot; write audit evidence only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
DEST = ROOT / 'reports/iteration4/CH02-intermediate-semantic.json'
assert not DEST.exists(), 'Preserve existing snapshot; do not overwrite.'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


conn = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA query_only=ON')
conn.execute('BEGIN')
run = dict(conn.execute('SELECT id,status,stage,active_plan_revision,request_count,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
plan_row = dict(conn.execute('SELECT * FROM plans WHERE run_id=? AND revision=?', (RID, run['active_plan_revision'])).fetchone())
approval = dict(conn.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (RID, run['active_plan_revision'])).fetchone())
rows = [dict(conn.execute('SELECT rowid,* FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (RID, f'section.S0{i}')).fetchone()) for i in range(1, 6)]
conn.rollback()
conn.close()
plan = json.loads(plan_row.pop('canonical_json'))
result = {'created_at': datetime.now(timezone.utc).isoformat(), 'scope': 'INTERMEDIATE_NOT_FINAL',
    'access': 'sqlite mode=ro / query_only / transaction; latest created_at DESC,rowid DESC per section',
    'real_api_requests': 0, 'new_windows_compile': 'NOT_RUN', 'pdf_visual_review': 'NOT_RUN',
    'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
    'run_snapshot': run, 'approved_plan_record': plan_row, 'approval': approval, 'approved_plan': plan,
    'sections': [], 'semantic_assessment': 'PENDING_AGENT_READ'}
for row in rows:
    payload = json.loads(row.pop('output_json'))
    assert sha(canonical(payload)) == row['output_hash']
    sid = row['step_key'].split('.')[1]
    generated = payload['generated']
    source = WS / payload['source_key']
    source_raw = source.read_bytes()
    assert sha(source_raw) == payload['source_hash']
    text = source_raw.decode('utf-8')
    unit_lines = {m[1]: text.count('\n', 0, m.start()) + 1 for m in re.finditer(r'^% UNIT (\S+)', text, re.M)}
    state_path = WS / 'runs' / RID / 'local-repair' / (sid + '.json')
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    candidate = WS / state['candidate_key']
    candidate_raw = candidate.read_bytes()
    parsed = json.loads(candidate_raw)
    assert sha(candidate_raw) == state['candidate_hash']
    dependencies = []
    for dep in state.get('evidence_dependencies', []):
        path = WS / dep['key']
        actual = sha(path.read_bytes())
        dependencies.append({**dep, 'actual_sha256': actual, 'hash_match': actual == dep['hash']})
    assert all(dep['hash_match'] for dep in dependencies)
    result['sections'].append({'section_id': sid, 'checkpoint': row, 'generated': generated,
        'generated_canonical_sha256': sha(canonical(generated)), 'report': payload['report'],
        'source_path': str(source), 'source_sha256': sha(source_raw), 'unit_source_lines': unit_lines,
        'source_unchanged_during_snapshot': source_raw == source.read_bytes(),
        'local_recovery': {'path': str(state_path), 'file_sha256': sha(state_raw), 'state': state,
            'unchanged_during_snapshot': state_raw == state_path.read_bytes(),
            'candidate_path': str(candidate), 'candidate_file_sha256': sha(candidate_raw),
            'candidate_matches_checkpoint_generated': parsed == generated,
            'candidate_unchanged_during_snapshot': candidate_raw == candidate.read_bytes(),
            'verified_dependencies': dependencies},
        'unit_evidence': [{'id': unit['id'], 'kind': unit['kind'], 'relates_to': unit.get('relates_to'),
            'canonical_sha256': sha(canonical(unit)), 'source_line': unit_lines.get(unit['id'])}
            for unit in generated['units']]})
DEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'saved': str(DEST), 'run': run, 'sections': [{
    'id': s['section_id'], 'rowid': s['checkpoint']['rowid'], 'created_at': s['checkpoint']['created_at'],
    'phase': s['local_recovery']['state']['phase'], 'units': len(s['generated']['units']),
    'candidate_matches': s['local_recovery']['candidate_matches_checkpoint_generated']}
    for s in result['sections']]}, ensure_ascii=False))
