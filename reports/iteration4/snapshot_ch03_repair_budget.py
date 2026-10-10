"""One read-only CH03 budget/state snapshot; never advances its worker."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / 'workspace/iteration2-live'
RUN_ID = 'a45be503af594ce8aae0bb1e4c30184b'
run_root = WORKSPACE / 'runs' / RUN_ID
with sqlite3.connect((WORKSPACE/'agent.db').as_uri()+'?mode=ro', uri=True, timeout=5) as connection:
    connection.row_factory = sqlite3.Row
    connection.execute('BEGIN')
    run = dict(connection.execute('SELECT id,status,stage,request_count,error_json FROM runs WHERE id=?', (RUN_ID,)).fetchone())
    budget = dict(connection.execute('SELECT version,defaults_json,overrides_json FROM run_budgets WHERE run_id=?', (RUN_ID,)).fetchone())
    event_count = connection.execute("SELECT count(*) FROM events WHERE run_id=? AND type='provider.request'", (RUN_ID,)).fetchone()[0]
    jobs = [dict(value) for value in connection.execute('SELECT id,status,attempt FROM jobs WHERE run_id=? ORDER BY created_at', (RUN_ID,))]
    connection.rollback()
limits = {**json.loads(budget['defaults_json']), **json.loads(budget['overrides_json'])}
report = {'created_at': datetime.now(timezone.utc).isoformat(), 'mode': 'READ_ONLY_POINT_IN_TIME',
          'run': run, 'budget_version': budget['version'], 'limits': limits,
          'provider_request_events': event_count, 'counter_matches_ledger': event_count == run['request_count'],
          'jobs': jobs, 'global': None, 'local_sections': {}, 'file_read_errors': [],
          'limitations': ['State files may progress independently after the short SQLite snapshot.'],
          'model_calls': 0, 'database_writes': 0}
paths = [run_root/'global-repair-state.json', *sorted((run_root/'local-repair').glob('S*.json'))]
for path in paths:
    if not path.is_file():
        continue
    try:
        raw = path.read_bytes()
        state = json.loads(raw)
        value = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'phase': state.get('phase')}
        if path.name == 'global-repair-state.json':
            value.update(rounds_used=state.get('rounds_used'), pending=state.get('pending'),
                         unresolved_issue_count=len(state.get('issues', [])))
            report['global'] = value
        else:
            value.update({key: state.get(key) for key in ('applied_rounds', 'proposal_calls', 'rejected_proposals',
                'unit_applied_counts', 'proposal_counts_by_key', 'rejected_counts_by_key')})
            value['pending_issue_count'] = len(state.get('pending_issues', []))
            report['local_sections'][path.stem] = value
    except (OSError, ValueError, TypeError) as error:
        report['file_read_errors'].append({'path': str(path), 'type': type(error).__name__, 'message': str(error)})
error = json.loads(run['error_json'] or 'null')
report['actionable'] = ('AWAITING_USER_REVIEW' if run['status'] == 'AWAITING_USER_REVIEW' else
    'BUDGET_EXHAUSTED' if (error or {}).get('code') == 'BUDGET_EXHAUSTED'
    or (report['global'] or {}).get('phase') == 'budget_exhausted'
    or any(value.get('phase') == 'BUDGET_EXHAUSTED' for value in report['local_sections'].values()) else None)
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
target = ROOT / 'reports/iteration4/ch03-budget-state' / (stamp+'.json')
target.parent.mkdir(parents=True, exist_ok=True)
with target.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({'evidence': str(target), 'status': run['status'], 'stage': run['stage'],
    'requests': run['request_count'], 'limits': limits, 'global': report['global'],
    'unit_applied_counts': {key: value['unit_applied_counts'] for key, value in report['local_sections'].items()},
    'actionable': report['actionable']}, ensure_ascii=True))
