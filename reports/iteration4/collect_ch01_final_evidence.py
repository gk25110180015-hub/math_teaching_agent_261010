"""Read-only CH01 final binding/preservation audit against its formal recheck backup."""
from datetime import datetime, timezone
import http.cookiejar
import json
from pathlib import Path
import sqlite3
import traceback
import urllib.request
import uuid
import collect_final_live_evidence as common

root = Path(__file__).resolve().parents[2]
workspace = root / 'workspace/iteration2-live'
rid = '05748ab6260c40989a560a98e1e2065a'
common.RUNS['CH01'] = rid
baseline = root / 'reports/iteration4/feedback-CH01-20260924T030623-6ba63f'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
output = root / 'reports/iteration4/ch01-final-evidence' / stamp
output.mkdir(parents=True, exist_ok=False)
result = {'at': common.utc(), 'status': 'RUNNING', 'model_calls': 0, 'database_mutations': 0,
          'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN', 'errors': []}
try:
    old = common.read_json(baseline / 'before.json')
    with sqlite3.connect((baseline / 'before-agent.db').as_uri() + '?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        old_events = [dict(row) for row in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY sequence', (rid,))]
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    common.get_local(opener, 'http://127.0.0.1:8766', '/api/session')
    api = common.get_local(opener, 'http://127.0.0.1:8766', '/api/runs/' + rid)['data']
    snapshot = common.take_database_snapshot(workspace / 'agent.db', ['CH01'])['CH01']
    common.save(output / 'database-snapshot.json', snapshot)
    common.save(output / 'service.json', api)
    run = snapshot['run']
    assert run['status'] == 'AWAITING_USER_REVIEW' and not any(j['status'] in ('running', 'queued') for j in snapshot['jobs'])
    plan, budget = snapshot['plan'], snapshot['budget']
    limits = {**json.loads(budget['defaults_json']), **json.loads(budget['overrides_json'])}
    metrics = common.request_metrics(snapshot['events'], run['request_count'], limits['requests'])
    artifacts = [common.inspect_artifact(workspace, row) for row in snapshot['artifacts']]
    receipts = common.inspect_feedback_receipts(workspace, snapshot, output)
    feedback = receipts['current']
    uncertainty = common.inspect_uncertainty_ledgers(workspace, snapshot, output)
    global_migrations = common.inspect_global_migrations(workspace, snapshot, output)
    uncertainty_migrations = common.inspect_uncertainty_migrations(workspace, snapshot, output)
    guidance_ledgers = common.inspect_guidance_ledgers(workspace, snapshot, output)
    normalized = lambda rows: [{k: row[k] for k in ('sequence','run_id','type','payload_json','timestamp')} for row in rows]
    actions = snapshot['budget_actions']
    previous = {key: old['budget'][key] for key in common.BUDGET_KEYS}
    chain = True
    for action in actions:
        before, after = json.loads(action['before_json']), json.loads(action['after_json'])
        chain &= all(before[k] == previous[k] and after[k] >= before[k] for k in previous)
        previous = {k: after[k] for k in previous}
    checks = {
        'input_preserved': json.loads(run['input_json']) == old['input'] and run['input_hash'] == old['input_hash'] == common.sha(run['input_json'].encode()),
        'plan_preserved': {**json.loads(plan['canonical_json']), 'hash': plan['hash']} == old['plan'] and common.sha(plan['canonical_json'].encode()) == plan['hash'],
        'approval_preserved': snapshot['approval'] == old['approval'],
        'old_events_exact_prefix': normalized(snapshot['events'][:len(old_events)]) == normalized(old_events),
        'original_counter_preserved': sum(e['type'] == 'provider.request' for e in old_events) == old['request_count'] == 37,
        'current_counter_matches_ledger': metrics['recorded_requests'] == run['request_count'] >= 37,
        'budget_chain_preserved': chain and previous == {k: limits[k] for k in previous} and budget['version'] == old['budget']['version'] + len(actions),
        'artifact_hashes': bool(artifacts) and all(a['integrity'] == 'PASS' for a in artifacts),
        'feedback_files': receipts['all_receipt_files_verified'],
        'current_feedback_body_bound': feedback['status'] == 'CURRENT_DELIVERY_VERIFIED' and feedback.get('no_pending_improvements') is True,
        'current_api_receipt_bound': api['feedback_review']['event_sequence'] == feedback['event_sequence'] and api['feedback_review']['identity_hash'] == feedback['receipt_identity_hash'] and api['feedback_review']['job_id'] == feedback['latest_build_job_id'],
        'uncertainty_files': uncertainty['all_files_verified'],
        'global_migration_archives': global_migrations['all_files_verified'],
        'uncertainty_migration_archives': uncertainty_migrations['all_files_verified'],
        'guidance_archives': guidance_ledgers['all_files_verified'],
        'no_teacher_reviews': not snapshot['reviews'] and not any(e['type'] == 'human.review' for e in snapshot['events']),
    }
    result.update(checks=checks, request_count=run['request_count'], budget_limits=limits,
                  request_summary=common.request_summary(metrics), feedback_receipts=receipts,
                  uncertainty_ledgers=uncertainty, baseline=common.provenance(baseline / 'before.json'),
                  global_migrations=global_migrations, uncertainty_migrations=uncertainty_migrations,
                  guidance_ledgers=guidance_ledgers,
                  artifacts_current=sum(a['delivery_group'] == 'current' for a in artifacts),
                  artifacts_history=sum(a['delivery_group'] == 'history' for a in artifacts))
    common.save(output / 'request-metrics.json', metrics)
    common.save(output / 'artifact-integrity.json', artifacts)
    result['status'] = 'PASS' if all(checks.values()) else 'NOT_PASS'
except BaseException as exc:
    result['status'] = 'NOT_PASS'
    result['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
    (output / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
finally:
    common.save(output / 'summary.json', result)
    print(json.dumps({'status': result['status'], 'report': str(output / 'summary.json'),
                      'errors': result['errors']}, ensure_ascii=False))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
