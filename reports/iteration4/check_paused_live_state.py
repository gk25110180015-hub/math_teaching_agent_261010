"""Preserve a read-only run/queue snapshot before restart and deployment."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
result = {'created_at': datetime.now(timezone.utc).isoformat(), 'read_only': True, 'databases': {}}
for relative in ['workspace/agent.db', 'workspace/iteration2-live/agent.db']:
    database = ROOT / relative
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        active = [dict(row) for row in connection.execute("SELECT id,run_id,kind,status FROM jobs WHERE status IN ('queued','running')")]
        runs = [dict(row) for row in connection.execute('SELECT id,status,stage,request_count,active_plan_revision,error_json FROM runs')]
        result['databases'][relative] = {'active_jobs': active, 'runs': runs}
        assert not active, 'Do not deploy over active jobs'
result['production_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    for name in ['src/math_agent/pipeline.py', 'src/math_agent/uncertainty_review.py',
        'src/math_agent/provider.py', 'src/math_agent/web/static/app.js']}
result['status'] = 'IDLE_PRESERVED'
result['preflight_http_observation'] = '2026-09-23 01:58 UTC local port 8766 refused connection; no model call or task mutation. Stale process record exists; restart required.'
target = REPORTS / ('paused-state-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6] + '.json')
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(target), **result}, ensure_ascii=True))
