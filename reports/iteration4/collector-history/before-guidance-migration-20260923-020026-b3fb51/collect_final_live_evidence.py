"""Collect a fresh read-only CH02/CH03 evidence snapshot; never execute tasks.

Uses the formal service's GET endpoints and one consistent SQLite read snapshot.
Does not instantiate Service/BenchmarkRunner, migrate a DB, or invoke a model.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid

from math_agent.benchmark import request_metrics
from math_agent.util import AgentError, digest
from recovery_evidence_archive import inspect_global_migrations, inspect_uncertainty_ledgers

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / 'reports/iteration4'
INITIAL = REPORT_ROOT / 'resume-20260920T143357-e340db'
RUNS = {'CH02': 'fd6736af6ef14be3839e019e86ca1e5c',
        'CH03': 'a45be503af594ce8aae0bb1e4c30184b'}
BUDGET_KEYS = ('requests', 'local_repairs_per_unit', 'global_repair_rounds')


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def provenance(path):
    return {'path': str(path.resolve()), 'sha256': sha(path.read_bytes())}


def request_summary(metrics):
    """Schema-validated body only; HTTP 200 headers never imply success."""
    grouped = defaultdict(lambda: {'attempts': 0, 'validated_successes': 0,
                                   'recorded_failures': 0, 'completion_uncertain': 0,
                                   'billing_uncertain': 0, 'statuses': Counter()})
    for item in metrics['requests']:
        model = item.get('model_id') or ('gpt6' if item.get('model') == 'gpt-6-astra' else item.get('model')) or 'UNKNOWN'
        row = grouped[model]
        row['attempts'] += 1
        status = item.get('status') or 'NO_FINAL_RESPONSE_RECORDED'
        row['statuses'][status] += 1
        if status == 'SCHEMA_VALIDATED':
            row['validated_successes'] += 1
        elif (isinstance(item.get('http_status'), int) and item['http_status'] >= 400
              or re.search(r'TIMEOUT|FAILED|FAILURE|ERROR|INVALID|INTERRUPTED|TRUNCATED|CANCELLED', status)):
            row['recorded_failures'] += 1
        else:
            row['completion_uncertain'] += 1
        if item.get('billing_uncertain', True):
            row['billing_uncertain'] += 1
    return {'by_model': dict(grouped),
            'totals': {key: sum(value[key] for value in grouped.values()) for key in
                       ('attempts', 'validated_successes', 'recorded_failures', 'completion_uncertain', 'billing_uncertain')},
            'success_definition': 'SCHEMA_VALIDATED only; not mathematical correctness or teacher acceptance.',
            'uncertainty_definition': 'No definitive success/failure recorded; HTTP 200 headers alone are uncertain. '
                                      'Timeouts are recorded client failures and may still have been handled/billed by the server.',
            'known_usage_sum': metrics['known_usage_sum'],
            'usage_reporting_complete': metrics['usage_reporting_complete'],
            'price_status': metrics['price_status']}


def get_local(client, base, path):
    request = urllib.request.Request(base + path, headers={'Accept': 'application/json'}, method='GET')
    with client.open(request, timeout=10) as response:
        return {'status': 'PASS', 'http_status': response.status, 'observed_at': utc(), 'data': json.load(response)}


def take_database_snapshot(database, cases):
    values = {}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')
        for case in cases:
            run_id = RUNS[case]
            row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row is None:
                raise ValueError('Expected run not found: ' + case)
            run = dict(row)
            plan = connection.execute('SELECT * FROM plans WHERE run_id=? AND revision=?',
                                      (run_id, run['active_plan_revision'])).fetchone()
            approval = connection.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?',
                                          (run_id, run['active_plan_revision'])).fetchone()
            budget = connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (run_id,)).fetchone()
            def rows(table, order):
                return [dict(value) for value in connection.execute(
                    f'SELECT * FROM {table} WHERE run_id=? ORDER BY {order}', (run_id,))]
            values[case] = {'run': run, 'plan': dict(plan) if plan else None,
                'approval': dict(approval) if approval else None, 'budget': dict(budget) if budget else None,
                'events': rows('events', 'sequence'), 'budget_actions': rows('budget_actions', 'created_at,action_id'),
                'jobs': [dict(value) for value in connection.execute(
                    'SELECT rowid AS _rowid,* FROM jobs WHERE run_id=? ORDER BY created_at,rowid', (run_id,))],
                'artifacts': rows('artifacts', 'created_at,artifact_id'),
                'reviews': rows('reviews', 'created_at,artifact_id'),
                'step_count': connection.execute('SELECT count(*) FROM steps WHERE run_id=?', (run_id,)).fetchone()[0]}
        connection.rollback()
    return values


def inspect_artifact(workspace, row):
    result = {key: row[key] for key in ('artifact_id', 'revision', 'name', 'storage_key', 'media_type', 'status', 'sha256', 'created_at')}
    result['delivery_group'] = 'history' if row['status'] == 'superseded' else 'current'
    result['observed_sha256'] = None
    try:
        path = (workspace / row['storage_key']).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError('Artifact path leaves the expected workspace')
        raw = path.read_bytes()
        result['observed_sha256'] = sha(raw)
        result['bytes'] = len(raw)
        result['integrity'] = 'PASS' if result['observed_sha256'] == row['sha256'] else 'CHANGED'
        result['metadata'] = json.loads(row['metadata_json'])
        if row['name'] == 'quality_report.json':
            quality = json.loads(raw)
            result['recorded_automatic_quality'] = {
                key: quality.get(key, {}).get('status', 'NOT_RECORDED') for key in
                ('content', 'math', 'compile', 'layout', 'policy', 'security')}
    except (OSError, ValueError, TypeError) as error:
        result['integrity'] = 'UNREADABLE_OR_INVALID'
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    return result


def inspect_attribution_evidence(workspace, run_id, events):
    """Record new guard states/dependencies without treating a resolution as human review."""
    root = (workspace/'runs'/run_id).resolve()
    results = []
    seen = set()
    for event in events:
        data = event['payload']
        key = (data.get('identity_hash'), data.get('evidence_key'))
        if key in seen:
            continue
        seen.add(key)
        result = {'identity_hash': key[0], 'evidence_key': key[1], 'dependencies': [],
                  'observed_at': utc(), 'integrity': 'NOT_CHECKED'}
        try:
            if not isinstance(key[1], str):
                raise ValueError('Attribution event has no evidence key')
            path = (workspace/key[1]).resolve()
            if not path.is_relative_to(root/'review-attribution'):
                raise ValueError('Attribution evidence path leaves its task scope')
            raw = path.read_bytes()
            state = json.loads(raw)
            if state.get('identity_hash') != key[0]:
                raise ValueError('Attribution state identity does not match its event')
            result.update(observed_sha256=sha(raw), phase=state.get('status', state.get('phase')), state=state)
            dependencies = state.get('dependencies', {})
            if not isinstance(dependencies, dict):
                raise ValueError('Invalid attribution dependency manifest')
            for name, expected in dependencies.items():
                dependency = (path.parent/name).resolve()
                if not dependency.is_relative_to(path.parent):
                    raise ValueError('Attribution dependency leaves its identity directory')
                observed = sha(dependency.read_bytes())
                result['dependencies'].append({'file': name, 'expected_sha256': expected,
                    'observed_sha256': observed, 'integrity': 'PASS' if observed == expected else 'CHANGED'})
            result['integrity'] = 'PASS' if all(value['integrity'] == 'PASS' for value in result['dependencies']) else 'CHANGED'
        except (OSError, ValueError, TypeError) as error:
            result['integrity'] = 'UNREADABLE_OR_INVALID'
            result['error'] = {'type': type(error).__name__, 'message': str(error)}
        results.append(result)
    return results


def attribution_error_summary(events, run_error, evidence):
    """Count persisted job endings once, preserving new/legacy codes and pending states."""
    guard_codes = ('REVIEW_EVIDENCE_BLOCKED', 'REVIEW_EVIDENCE_UNRESOLVED',
                   'REVIEW_EVIDENCE_CACHE_INVALID')
    counts = Counter()
    for event in events:
        if event['type'] == 'job.finished':
            error = json.loads(event['payload_json']).get('error') or {}
            code = error.get('code')
            if code in (*guard_codes, 'BUDGET_EXHAUSTED'):
                counts[code] += 1
    return {
        'job_finished_error_code_counts': {code: counts[code] for code in (*guard_codes, 'BUDGET_EXHAUSTED')},
        'attribution_error_endings': sum(counts[code] for code in guard_codes),
        'budget_exhaustion_endings_all_stages': counts['BUDGET_EXHAUSTED'],
        'current_run_error_code': run_error.get('code') if isinstance(run_error, dict) else None,
        'observed_state_status_counts': dict(Counter(value.get('phase', 'UNKNOWN') for value in evidence)),
        'definition': 'Counts job.finished events once, not duplicated run/job error snapshots. '
                      'REVIEW_EVIDENCE_BLOCKED is the current guard code; REVIEW_EVIDENCE_UNRESOLVED '
                      'is retained as a historical code. BUDGET_EXHAUSTED is separate and may arise '
                      'outside attribution. State and event statuses remain verbatim; pending does '
                      'not imply a completed adjudication or teacher review.',
    }


def feedback_delivery_match(workspace, snapshot, context):
    """Re-render saved review units in memory and compare the exact delivered TeX."""
    from math_agent.pipeline import render_lecture
    current = [row for row in snapshot['artifacts'] if row['status'] != 'superseded']
    result = {'status': 'NOT_VERIFIED', 'unit_payload_sha256': digest(context['units']),
        'unit_sha256': {unit['id']: digest(unit) for unit in context['units']},
        'renderer': provenance(Path(__import__('math_agent.pipeline', fromlist=['']).__file__)),
        'note': 'Pure in-memory rendering only; no compiler or model is invoked.'}
    chosen = {}
    for name in ('lecture.tex', 'source_map.json'):
        rows = [row for row in current if row['name'] == name]
        if len(rows) != 1:
            result['reason'] = 'Expected exactly one current ' + name
            return result
        row = rows[0]
        path = (workspace/row['storage_key']).resolve()
        if not path.is_relative_to(workspace.resolve()):
            raise ValueError('Current delivery leaves workspace')
        raw = path.read_bytes()
        if sha(raw) != row['sha256']:
            raise ValueError('Current delivery SHA mismatch: ' + name)
        chosen[name] = (row, raw)
    plan = {**json.loads(snapshot['plan']['canonical_json']), 'hash': snapshot['plan']['hash']}
    if context['plan'] != plan:
        result['reason'] = 'Receipt input plan differs from current approved plan'
        return result
    mapping = json.loads(chosen['source_map.json'][1])['sections']
    if [section['id'] for section in mapping] != [section['id'] for section in plan['sections']]:
        raise ValueError('Current source map section order differs from the approved plan')
    actual = {unit['id']: unit for unit in context['units']}
    mapped = [ident for section in mapping for ident in section['units']]
    if len(actual) != len(context['units']) or len(mapped) != len(set(mapped)) or set(mapped) != set(actual):
        result['reason'] = 'Current source map units differ from the receipt body'
        return result
    sections = [(spec, {'section_id': spec['id'], 'units': [actual[ident] for ident in section['units']]})
                for spec, section in zip(plan['sections'], mapping)]
    rendered = render_lecture(plan['title'], sections, plan).encode('utf-8')
    observed = sha(rendered)
    tex_row = chosen['lecture.tex'][0]
    result.update(status='PASS' if observed == tex_row['sha256'] else 'BODY_DIFFERS',
        current_tex_artifact_id=tex_row['artifact_id'], current_tex_sha256=tex_row['sha256'],
        rendered_receipt_body_sha256=observed, source_map_artifact_id=chosen['source_map.json'][0]['artifact_id'],
        source_map_sha256=chosen['source_map.json'][0]['sha256'])
    return result


def inspect_feedback_receipts(workspace, snapshot, output):
    """Archive every durable receipt; select by latest job/action/event, never first response."""
    events = snapshot['events']
    plan, approval = snapshot['plan'], snapshot['approval']
    jobs = [row for row in snapshot['jobs'] if row['kind'] == 'build']
    job = jobs[-1] if jobs else None
    actions = [row for row in events if row['type'] == 'checks.rerun_requested']
    action_row = actions[-1] if actions else None
    action = json.loads(action_row['payload_json']) if action_row else {}
    nonempty = isinstance(action.get('feedback'), str) and bool(action['feedback'].strip())
    current_action = bool(job and plan and approval and action_row
        and action.get('job_id') == job['id'] and action.get('plan_hash') == plan['hash'] == approval['hash']
        and action.get('plan_revision') == plan['revision'] == approval['revision'])
    selected = None
    rows = []
    for event in events:
        if event['type'] != 'feedback.reviewed':
            continue
        record = {'sequence': event['sequence'], 'timestamp': event['timestamp'], 'integrity': 'NOT_CHECKED'}
        after_current_action = bool(current_action and nonempty and event['sequence'] > action_row['sequence'])
        try:
            record['payload'] = json.loads(event['payload_json'])
            data = record['payload']
            if not isinstance(data, dict):
                raise ValueError('Feedback receipt event is not an object')
            eligible = bool(after_current_action
                and data.get('job_id') == job['id'] and data.get('plan_hash') == plan['hash']
                and data.get('plan_revision') == plan['revision'])
            record['matches_current_job_and_plan'] = eligible
            if eligible:
                selected = record  # Later corrupt/mismatched feedback must not fall back to an earlier PASS.
            if (type(data.get('schema_version')) is not int or data['schema_version'] != 1
                    or type(data.get('plan_revision')) is not int or type(data.get('mock')) is not bool
                    or data.get('teacher_review') != 'NOT_RUN'
                    or data.get('status') not in ('reviewed','unresolved','invalid','transport_pending')):
                raise ValueError('Feedback receipt metadata is invalid')
            path = (workspace/data['evidence_key']).resolve()
            scope = (workspace/'runs'/snapshot['run']['id']/'feedback-reviews').resolve()
            if not path.is_relative_to(scope) or path.name != Path(data['evidence_key']).name:
                raise ValueError('Feedback receipt leaves this task evidence scope')
            raw = path.read_bytes()
            receipt = json.loads(raw)
            if sha(raw) != data['evidence_sha256'] or receipt != {k:v for k,v in data.items() if k not in ('evidence_key','evidence_sha256')}:
                raise ValueError('Feedback event and saved receipt SHA/payload differ')
            state_path = path.parent/'state.json'
            state_raw = state_path.read_bytes()
            state = json.loads(state_raw)
            if state['identity_hash'] != data['identity_hash'] or digest(state['identity']) != data['identity_hash']:
                raise ValueError('Feedback state identity SHA mismatch')
            for key in ('job_id','plan_hash','plan_revision','feedback_hash'):
                if state['identity'][key] != data[key]:
                    raise ValueError('Feedback state and receipt identity differ: ' + key)
            archive = output/'feedback-evidence'/data['identity_hash'][:24]
            archive.mkdir(parents=True, exist_ok=True)
            dependencies = []
            saved = {}
            for name, expected in state['dependencies'].items():
                if Path(name).name != name:
                    raise ValueError('Feedback dependency is not a sibling filename')
                source = (path.parent/name).resolve()
                if not source.is_relative_to(path.parent):
                    raise ValueError('Feedback dependency leaves its identity directory')
                value = source.read_bytes()
                observed = sha(value)
                if observed != expected:
                    raise ValueError('Feedback dependency SHA mismatch: ' + name)
                target = archive/name
                if target.exists():
                    if target.read_bytes() != value:
                        raise ValueError('Feedback evidence changed during collection: ' + name)
                else:
                    with target.open('xb') as stream:
                        stream.write(value)
                saved[name] = json.loads(value)
                dependencies.append({'name':name,'sha256':observed,'archive':str(target)})
            if path.name not in saved or saved[path.name] != receipt:
                raise ValueError('Receipt is not registered among immutable dependencies')
            context = saved['input.json']
            if digest(context) != state['identity']['context_hash'] or digest(context['feedback_text']) != data['feedback_hash']:
                raise ValueError('Saved feedback input and body identity differ')
            if (context['plan']['hash'], context['plan']['revision']) != (data['plan_hash'], data['plan_revision']):
                raise ValueError('Feedback input plan and receipt identity differ')
            source_event = context['source_event']
            source_row = next((row for row in actions if row['sequence'] == source_event['sequence']), None)
            if (source_row is None or digest(source_row['payload_json']) != source_event['payload_sha256']
                    or source_event['job_id'] != data['job_id'] or source_event['plan_hash'] != data['plan_hash']
                    or source_event['plan_revision'] != data['plan_revision']):
                raise ValueError('Saved feedback action provenance does not match the event ledger')
            source_action = json.loads(source_row['payload_json'])
            if source_action.get('feedback') != context['feedback_text']:
                raise ValueError('Receipt input feedback differs from its recorded action')
            if eligible and source_event['sequence'] != action_row['sequence']:
                raise ValueError('Current receipt belongs to an earlier feedback action')
            from math_agent.feedback_review import FeedbackAssessment
            FeedbackAssessment.model_validate({'items':receipt['items'],'limitations':receipt['limitations']})
            fixed_ids = [item['id'] for item in context['feedback_items']]
            if [item['id'] for item in receipt['items']] != fixed_ids:
                raise ValueError('Receipt does not cover its fixed feedback items in order')
            replay = 'NOT_APPLICABLE_TO_PENDING_OR_INVALID'
            if receipt['status'] in ('reviewed','unresolved'):
                from math_agent.feedback_review import validate_assessment
                assessment, _ = validate_assessment(saved[state['response_file']], context)
                if assessment != {'items':receipt['items'],'limitations':receipt['limitations']}:
                    raise ValueError('Saved response does not justify the receipt')
                replay = 'PASS_PURE_VALIDATION_NO_MODEL_CALL'
            elif any(item.get('status') != 'unresolved' for item in receipt['items']):
                raise ValueError('Pending/invalid receipt contains a completed disposition')
            # State can advance between historical receipt events. Preserve each
            # observed state by event sequence rather than overwriting an archive.
            with (archive/('state-at-event-'+str(event['sequence'])+'.json')).open('xb') as stream:
                stream.write(state_raw)
            record.update(integrity='PASS', observed_at=utc(), receipt_file_sha256=sha(raw),
                state_file_sha256=sha(state_raw), state_status=state['status'], identity=state['identity'],
                dependencies=dependencies, saved_response_revalidation=replay,
                body_unit_payload_sha256=digest(context['units']),
                body_unit_sha256={unit['id']:digest(unit) for unit in context['units']},
                input_plan_hash=context['plan']['hash'], input_plan_revision=context['plan']['revision'],
                saved_context=context)
        except (OSError, ValueError, KeyError, TypeError, AgentError) as error:
            if after_current_action and not isinstance(record.get('payload'), dict):
                selected = record
            record.update(integrity='UNREADABLE_OR_INVALID', error={'type':type(error).__name__,'message':str(error)})
        rows.append(record)
    current = {'status':'NOT_APPLICABLE', 'latest_build_job_id':job['id'] if job else None,
        'latest_feedback_action_sequence':action_row['sequence'] if action_row else None,
        'nonempty_feedback':nonempty, 'teacher_review':'NOT_RUN'}
    if current_action and nonempty:
        current.update(status='NO_CURRENT_RECEIPT', expected_feedback_sha256=digest(action['feedback']))
        if selected:
            selected_payload = selected.get('payload') if isinstance(selected.get('payload'),dict) else {}
            current.update(event_sequence=selected['sequence'], receipt_status=selected_payload.get('status'),
                receipt_identity_hash=selected_payload.get('identity_hash'))
            if selected['integrity'] != 'PASS':
                current['status'] = 'INVALID_CURRENT_RECEIPT'
            elif selected['payload']['feedback_hash'] != current['expected_feedback_sha256']:
                current['status'] = 'CURRENT_FEEDBACK_HASH_MISMATCH'
            else:
                try:
                    match = feedback_delivery_match(workspace,snapshot,selected['saved_context'])
                except (OSError, ValueError, KeyError, TypeError, AgentError) as error:
                    match = {'status':'UNREADABLE_OR_INVALID','error':{'type':type(error).__name__,'message':str(error)}}
                current['delivery_match'] = match
                current['status'] = 'CURRENT_DELIVERY_VERIFIED' if match['status']=='PASS' else 'NOT_CURRENT_DELIVERY'
                current['item_status_counts'] = dict(Counter(item['status'] for item in selected['payload']['items']))
                current['no_pending_improvements'] = selected['payload']['status']=='reviewed' and all(
                    item['status'] in ('satisfied','rejected_not_supported','out_of_scope') for item in selected['payload']['items'])
    elif nonempty:
        current['status'] = 'LATEST_FEEDBACK_NOT_BOUND_TO_CURRENT_JOB_AND_APPROVAL'
    for row in rows:
        row.pop('saved_context', None)  # Already archived byte-for-byte as input.json.
        row['is_selected_current_receipt'] = selected is row
    save(output/'feedback-receipts.json', rows)
    save(output/'feedback-current-delivery.json', current)
    return {'all_receipt_files_verified':all(row['integrity']=='PASS' for row in rows),
        'recorded_receipts':len(rows), 'current':current,
        'selection_rule':'Latest current job/approved plan receipt after the latest nonempty feedback action; never the first response or a fallback across invalid/latest records.'}


def inspect_case(case, snapshot, workspace, output, service_run=None):
    original_path = INITIAL / case / 'before.json'
    original = read_json(original_path)
    old_events_path = INITIAL / case / 'events.json'
    old_events = read_json(old_events_path)
    request = read_json(INITIAL / case / 'budget-request.json')
    run, plan, approval, budget = (snapshot[key] for key in ('run', 'plan', 'approval', 'budget'))
    events = snapshot['events']
    defaults = json.loads(budget['defaults_json']) if budget else {}
    overrides = json.loads(budget['overrides_json']) if budget else {}
    limits = {key: overrides.get(key, defaults.get(key)) for key in BUDGET_KEYS}
    metrics = request_metrics(events, run['request_count'], limits['requests'] or 0)
    model_summary = request_summary(metrics)
    normalized_keys = ('sequence', 'run_id', 'type', 'payload_json', 'timestamp')
    normalized_old = [{key: value[key] for key in normalized_keys} for value in old_events]
    normalized_now = [{key: value[key] for key in normalized_keys} for value in events[:len(old_events)]]
    old_requests = [value for value in old_events if value['type'] == 'provider.request']
    new_requests = [value for value in events if value['type'] == 'provider.request']
    actions = []
    for row in snapshot['budget_actions']:
        actions.append({key: value for key, value in row.items() if key not in ('before_json', 'after_json')}
                       | {'before': json.loads(row['before_json']), 'after': json.loads(row['after_json'])})
    feedback, audit_actions, attribution_events = [], [], []
    for event in events:
        if event['type'] in ('budget.increased_by_user', 'job.retry', 'checks.rerun_requested', 'review.evidence_attribution', 'feedback.reviewed',
                             'global.repair_contract_migrated', 'math.uncertainty_reviewed'):
            data = json.loads(event['payload_json'])
            value = {key: event[key] for key in ('sequence', 'type', 'timestamp')} | {'payload': data}
            audit_actions.append(value)
            if event['type'] == 'checks.rerun_requested':
                value = dict(value)
                value['feedback_present'] = bool(data.get('feedback', '').strip()) if isinstance(data.get('feedback', ''), str) else None
                value['matches_original_approval'] = data.get('plan_hash') == original['approval']['hash'] and data.get('plan_revision') == original['approval']['revision']
                feedback.append(value)
            elif event['type'] == 'review.evidence_attribution':
                attribution_events.append(value)
    attribution_files = inspect_attribution_evidence(workspace, run['id'], attribution_events)
    run_error = json.loads(run['error_json'] or 'null')
    attribution_errors = attribution_error_summary(events, run_error, attribution_files)
    artifacts = [inspect_artifact(workspace, row) for row in snapshot['artifacts']]
    feedback_receipts = inspect_feedback_receipts(workspace, snapshot, output)
    global_migrations = inspect_global_migrations(workspace, snapshot, output)
    uncertainty_ledgers = inspect_uncertainty_ledgers(workspace, snapshot, output)
    initial_action = next((value for value in actions if value['action_id'] == request['action_id']), None)
    checks = {
        'original_input_hash_preserved': run['input_hash'] == original['input_hash'],
        'original_input_payload_preserved': json.loads(run['input_json']) == original['input'],
        'stored_input_hash_matches_payload': sha(run['input_json'].encode('utf-8')) == run['input_hash'],
        'original_plan_revision_hash_preserved': bool(plan) and plan['revision'] == original['plan']['revision'] and plan['hash'] == original['plan']['hash'],
        'original_plan_payload_preserved': bool(plan) and {**json.loads(plan['canonical_json']), 'hash': plan['hash']} == original['plan'],
        'stored_plan_hash_matches_payload': bool(plan) and sha(plan['canonical_json'].encode('utf-8')) == plan['hash'],
        'original_approval_record_preserved': approval == original['approval'],
        'all_original_events_preserved_as_exact_prefix': normalized_old == normalized_now,
        'original_request_event_count_matches_initial_counter': len(old_requests) == original['request_count'],
        'current_request_counter_matches_event_ledger': len(new_requests) == run['request_count'] == metrics['recorded_requests'],
        'request_counter_not_reset': run['request_count'] >= original['request_count'],
        'initial_explicit_budget_action_preserved': bool(initial_action)
            and all(initial_action['after'].get(key) == request[key] for key in BUDGET_KEYS)
            and all(initial_action['before'].get(key) == original['budget'][key] for key in BUDGET_KEYS),
        'current_limits_at_least_authorized_240_6_6': all(type(limits[key]) is int and limits[key] >= request[key] for key in BUDGET_KEYS),
        'budget_version_matches_number_of_actions': bool(budget) and budget['version'] == original['budget']['version'] + len(actions),
        'feedback_actions_bound_to_original_approval': all(value['matches_original_approval'] for value in feedback),
        'all_published_artifact_hashes_verified': all(value['integrity'] == 'PASS' for value in artifacts),
        'attribution_state_dependency_hashes_verified': all(value['integrity'] == 'PASS' for value in attribution_files),
        'feedback_receipt_dependencies_verified': feedback_receipts['all_receipt_files_verified'],
        'global_migration_archives_verified': global_migrations['all_files_verified'],
        'uncertainty_ledger_dependencies_verified': uncertainty_ledgers['all_files_verified'],
        'human_review_table_empty': not snapshot['reviews'],
        'no_human_review_events': not any(value['type'] == 'human.review' for value in events),
    }
    latest_limits = {key: original['budget'][key] for key in BUDGET_KEYS}
    continuous = True
    for action in actions:
        continuous &= all(action['before'].get(key) == latest_limits[key] for key in BUDGET_KEYS)
        continuous &= all(type(action['after'].get(key)) is int and action['after'][key] >= latest_limits[key] for key in BUDGET_KEYS)
        latest_limits = {key: action['after'].get(key) for key in BUDGET_KEYS}
    checks['budget_action_chain_matches_current_limits'] = continuous and latest_limits == limits
    current_artifacts = [value for value in artifacts if value['delivery_group'] == 'current']
    active_jobs = [value['id'] for value in snapshot['jobs'] if value['status'] in ('queued', 'running')]
    feedback_current = feedback_receipts['current']
    feedback_final_ready = (feedback_current['status'] == 'NOT_APPLICABLE'
        or feedback_current['status'] == 'CURRENT_DELIVERY_VERIFIED' and feedback_current.get('no_pending_improvements') is True)
    api_receipt = service_run.get('feedback_review') if isinstance(service_run, dict) else None
    service_feedback_matches = (isinstance(service_run, dict) and service_run.get('id') == run['id'] and
        (api_receipt is None if feedback_current['status'] == 'NOT_APPLICABLE' else
         isinstance(api_receipt, dict) and api_receipt.get('event_sequence') == feedback_current.get('event_sequence')
         and api_receipt.get('identity_hash') == feedback_current.get('receipt_identity_hash')
         and api_receipt.get('job_id') == feedback_current['latest_build_job_id']))
    job_error_codes = Counter()
    for event in events:
        if event['type'] == 'job.finished':
            error = json.loads(event['payload_json']).get('error') or {}
            if isinstance(error.get('code'), str):
                job_error_codes[error['code']] += 1
    result = {'preservation_status': 'PASS' if all(checks.values()) else 'NOT_PASS',
        'run_id': run['id'], 'status_at_snapshot': run['status'], 'stage_at_snapshot': run['stage'],
        'run_error_at_snapshot': run_error,
        'active_jobs': active_jobs, 'stable_delivery_snapshot': not active_jobs and run['status'] == 'AWAITING_USER_REVIEW',
        'original_snapshot': provenance(original_path), 'original_event_snapshot': provenance(old_events_path),
        'checks': checks, 'request_count_initial': original['request_count'], 'request_count_current': run['request_count'],
        'request_events_appended': len(new_requests) - len(old_requests), 'request_summary': model_summary,
        'approval': approval, 'plan_hash': plan['hash'] if plan else None, 'input_hash': run['input_hash'],
        'budget_limits': limits, 'budget_version': budget['version'] if budget else None,
        'budget_actions': actions, 'feedback_actions': feedback, 'attribution_events': attribution_events,
        'attribution_phase_counts': dict(Counter(value['payload'].get('phase', 'UNKNOWN') for value in attribution_events)),
        'attribution_error_summary': attribution_errors,
        'feedback_receipts': feedback_receipts,
        'global_migrations': global_migrations, 'uncertainty_ledgers': uncertainty_ledgers,
        'final_feedback_delivery_ready': feedback_final_ready,
        'formal_service_feedback_matches_database_snapshot': service_feedback_matches,
        'all_job_finished_error_code_counts': dict(job_error_codes),
        'human_review_count': len(snapshot['reviews']),
        'artifacts_current': len(current_artifacts), 'artifacts_history': len(artifacts) - len(current_artifacts),
        'current_artifact_ids': [value['artifact_id'] for value in current_artifacts],
        'current_automatic_quality': [value for value in current_artifacts if value['name'] == 'quality_report.json'],
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}
    save(output / 'database-snapshot.json', snapshot)
    save(output / 'events.json', events)
    save(output / 'request-metrics.json', metrics)
    save(output / 'request-summary.json', model_summary)
    save(output / 'budget-retry-feedback-actions.json', audit_actions)
    save(output / 'attribution-evidence.json', attribution_files)
    save(output / 'artifact-integrity.json', artifacts)
    save(output / 'preservation.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', choices=RUNS, help='Repeat for both; default CH02 and CH03')
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--workspace', type=Path, default=ROOT / 'workspace/iteration2-live')
    parser.add_argument('--output-root', type=Path, default=REPORT_ROOT / 'final-live-evidence')
    args = parser.parse_args(argv)
    base = args.base_url.rstrip('/')
    parsed = urllib.parse.urlparse(base)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        parser.error('Only a plain loopback HTTP service URL is accepted')
    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(REPORT_ROOT.resolve()) or output_root == REPORT_ROOT.resolve():
        parser.error('Output must be a child directory of reports/iteration4')
    workspace = args.workspace.resolve()
    if not workspace.is_relative_to((ROOT / 'workspace').resolve()):
        parser.error('Workspace must remain within this project workspace directory')
    cases = list(dict.fromkeys(args.case or RUNS))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    output = output_root / stamp
    output.mkdir(parents=True, exist_ok=False)
    summary = {'started_at': utc(), 'status': 'COLLECTING', 'mode': 'READ_ONLY_SNAPSHOT',
        'script': provenance(Path(__file__)),
        'recovery_archival_helper': provenance(Path(__file__).with_name('recovery_evidence_archive.py')),
        'workspace': str(workspace), 'base_url': base,
        'model_calls_by_this_script': 0, 'database_mutations': 0, 'cases': {}, 'errors': [],
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'limitations': ['A running job can progress after this timestamp; use a stable snapshot for final delivery.',
            'Schema-validated model output is not a mathematical verdict.',
            'Filesystem hashes do not replace clean Windows compilation or teacher visual review.',
            'No prior evidence directory or benchmark manifest is overwritten.']}
    save(output / 'summary.json', summary)
    try:
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        # GET creates only a browser-session cookie; never persist its token.
        try:
            get_local(client, base, '/api/session')
        except (OSError, ValueError, urllib.error.URLError) as error:
            summary['errors'].append({'scope': 'local_session', 'type': type(error).__name__, 'message': str(error)})
        service_runs = {}
        for name, path in [('health', '/api/health'), *[(case, '/api/runs/' + RUNS[case]) for case in cases]]:
            try:
                response = get_local(client, base, path)
                if name in cases:
                    service_runs[name] = response['data']
                save(output / ('service-' + name + '.json'), response)
            except (OSError, ValueError, urllib.error.URLError) as error:
                failure = {'scope': 'local_service_' + name, 'type': type(error).__name__, 'message': str(error)}
                summary['errors'].append(failure)
                save(output / ('service-' + name + '.json'), {'status': 'UNAVAILABLE', 'error': failure})
        summary['database_snapshot_started_at'] = utc()
        snapshots = take_database_snapshot(workspace / 'agent.db', cases)
        summary['database_snapshot_finished_at'] = utc()
        for case in cases:
            try:
                summary['cases'][case] = inspect_case(case, snapshots[case], workspace, output / case, service_runs.get(case))
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                summary['errors'].append({'scope': case, 'type': type(error).__name__, 'message': str(error)})
                save(output / case / 'database-snapshot.json', snapshots[case])
        restart = REPORT_ROOT / 'restart-preservation.json'
        if restart.is_file():
            summary['prior_restart_preservation'] = provenance(restart) | {'recorded_status': read_json(restart).get('status')}
        summary['status'] = 'PASS' if not summary['errors'] and len(summary['cases']) == len(cases) and all(
            value['preservation_status'] == 'PASS' for value in summary['cases'].values()) else 'NOT_PASS'
        summary['final_delivery_snapshot_ready'] = summary['status']=='PASS' and all(
            value['stable_delivery_snapshot'] and value['final_feedback_delivery_ready']
            and value['formal_service_feedback_matches_database_snapshot'] for value in summary['cases'].values())
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        summary['status'] = 'NOT_PASS'
        summary['errors'].append({'scope': 'collection', 'type': type(error).__name__, 'message': str(error)})
    finally:
        summary['finished_at'] = utc()
        save(output / 'summary.json', summary)
        lines = ['# 最终真实任务证据快照', '', f"保留核对：**{summary['status']}**。UTC：{summary['finished_at']}。", '',
            '仅只读采集；不会推进工作流、调用模型、改变预算或提交人审。通过仅表示历史与文件完整性核对通过，不能代替数学和视觉验收。', '',
            '| 章节 | 运行状态 | 请求累计 | 有效返回 | 已记录失败 | 完成未确定 | 当前/历史文件 | 保留核对 |',
            '|---|---|---:|---:|---:|---:|---:|---|']
        for case, value in summary['cases'].items():
            totals = value['request_summary']['totals']
            lines.append(f"| {case} | {value['status_at_snapshot']} | {value['request_count_initial']}→{value['request_count_current']} | "
                f"{totals['validated_successes']} | {totals['recorded_failures']} | {totals['completion_uncertain']} | "
                f"{value['artifacts_current']}/{value['artifacts_history']} | {value['preservation_status']} |")
        lines += ['', '有效返回只统计 SCHEMA_VALIDATED；HTTP 200 响应头不能算成功。超时列为已记录失败，服务器是否已完成或计费仍可能不确定。', '',
            '逐模型结果、全部请求账本、预算/反馈动作、原审批和文件哈希见每章 JSON。人审及教师数学/视觉验收未由本脚本执行。', '',
            f"最终交付快照与当前反馈正文一致：{summary.get('final_delivery_snapshot_ready', False)}。这与历史文件保留核对分开判定。", '',
            '每章 feedback-current-delivery.json 记录最后一轮回执选择及受审正文重新渲染后与当前 TeX 的 SHA 比较；全部历史回执和原始输入/响应/依赖字节保存于 feedback-evidence。', '',
            '[机器总报告](summary.json)']
        if summary['errors']:
            lines += ['', '本次未完成或异常项：', *['- ' + json.dumps(error, ensure_ascii=False) for error in summary['errors']]]
        (output / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(json.dumps({'output': str(output), 'status': summary['status'], 'cases': list(summary['cases']),
                          'error_count': len(summary['errors'])}, ensure_ascii=True))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
