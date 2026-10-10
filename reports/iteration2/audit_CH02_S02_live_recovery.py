"""Read preserved S02 evidence only; no API, compile, service, or database writes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from math_agent.answer_completion import AnswerCompletion, apply_answer_completion
from math_agent.domain import MathReview
from math_agent.local_patch import LocalPatch, apply_local_patch
from math_agent.util import digest

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
OUT = PROJECT / 'reports/iteration2/CH02-S02-live-recovery.json'
if OUT.exists():
    raise SystemExit('Existing audit evidence must not be overwritten')
files = {}


def raw(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    files[str(path)] = digest(body)
    return body


def read(path):
    return json.loads(raw(path))


state_path = WORKSPACE / 'runs' / RID / 'local-repair/S02.json'
state = read(state_path)
old = WORKSPACE / 'b' / RID[:16] / 'sS02_a3c5b831b6c6'
draft = WORKSPACE / 'b' / RID[:16] / 'sS02_535f6e66022e'
accepted_old = read(old / 'repair-1.json')
old_base = read(old / 'candidate-normalized.json')
old_rejected = read(old / 'repair-2-raw.json')
proposal_path = WORKSPACE / state['answer_recovery']['proposal_key']
before = read(proposal_path.parent / 'before.json')
answer_proposal = read(proposal_path)
appended = read(proposal_path.parent / 'candidate.json')
patch = read(draft / 'repair-4-patch.json')
patch_record = read(draft / 'repair-4.json')
final = read(WORKSPACE / state['candidate_key'])
reviews = [read(draft / f'review-{number}.json') for number in range(3)]
targets = ['S02.U18', 'S02.U19', 'S02.U20']
new_ids = [target + '.answer' for target in targets]
before_units = {unit['id']: unit for unit in before['units']}
append_units = {unit['id']: unit for unit in appended['units']}
final_units = {unit['id']: unit for unit in final['units']}
replayed_append, _ = apply_answer_completion(before, answer_proposal)
replayed_patch, _ = apply_local_patch(appended, targets, patch)
checks = {
    'old_repair_hash_chain_valid': accepted_old['before_hash'] == digest(old_base) and accepted_old['after_hash'] == digest(accepted_old['section']),
    'legacy_accepted_body_is_exact_answer_baseline': before == accepted_old['section'],
    'old_rejected_proposal_not_seed': before != old_rejected,
    'all_20_original_units_preserved_by_append': len(before['units']) == 20 and appended['units'][:20] == before['units'],
    'exactly_three_answers_added': [unit['id'] for unit in appended['units'][20:]] == new_ids,
    'answers_have_exact_relates_to': all(append_units[new]['kind'] == 'solution' and append_units[new]['relates_to'] == target for target, new in zip(targets, new_ids)),
    'append_pure_replay_matches_saved_candidate': replayed_append == appended,
    'append_original_calculations_preserved': appended['calculations'][:len(before['calculations'])] == before['calculations'],
    'patch_pure_replay_matches_saved_candidate': replayed_patch == patch_record['section'] == final,
    'patch_only_three_tex_fields_change': all({key: value for key, value in append_units[uid].items() if key != 'tex'} == {key: value for key, value in final_units[uid].items() if key != 'tex'} for uid in append_units),
    'patch_order_preserved': [unit['id'] for unit in appended['units']] == [unit['id'] for unit in final['units']],
    'patch_non_target_20_units_exactly_preserved': all(final_units[uid] == unit for uid, unit in append_units.items() if uid not in targets),
    'each_target_removes_only_embedded_answer_suffix': all('答案：' in before_units[uid]['tex'] and final_units[uid]['tex'] == before_units[uid]['tex'].partition('\n\n答案：')[0] for uid in targets),
    'patch_all_four_calculations_preserved': final['calculations'] == appended['calculations'] and len(final['calculations']) == 4,
    'original_three_calculations_preserved_to_final': final['calculations'][:3] == before['calculations'],
    'patch_no_calculation_updates_additions': patch['calculation_updates'] == patch['calculation_additions'] == [],
    'old_uncertainties_preserved': final['uncertainties'][:len(before['uncertainties'])] == before['uncertainties'],
    'old_calculation_limitations_preserved': final['calculation_limitations'][:len(before['calculation_limitations'])] == before['calculation_limitations'],
    'final_candidate_byte_hash_matches_state': files[str((WORKSPACE / state['candidate_key']).resolve())] == state['candidate_hash'],
    'state_checked_no_pending_issues': state['phase'] == 'CHECKED' and state['pending_issues'] == [],
    'cumulative_local_counts_retained': (state['applied_rounds'], state['proposal_calls'], state['rejected_proposals']) == (3, 4, 1),
    'per_unit_old_and_new_counts_retained': all(state['unit_applied_counts'][uid] == 2 for uid in targets) and all(state['unit_applied_counts'][uid] == 1 for uid in new_ids),
    'proposal_rejection_key_counts_retained': all(state['proposal_counts_by_key']['unit:' + uid] == 3 and state['rejected_counts_by_key']['unit:' + uid] == 1 and state['proposal_counts_by_key']['answer:' + uid] == 1 for uid in targets),
    'legacy_request_count_retained_at_import': state['legacy_import']['total_request_count_at_import'] == 11,
    'legacy_rejected_status_retained': [entry['status'] for entry in state['legacy_import']['records']] == ['VERIFIED_APPLIED', 'REJECTED_NOT_ADOPTED'],
}
for dep in state['evidence_dependencies']:
    checks['dependency:' + dep['key']] = digest(raw(WORKSPACE / dep['key'])) == dep['hash']

connection = sqlite3.connect(WORKSPACE.joinpath('agent.db').resolve().as_uri() + '?mode=ro', uri=True)
connection.row_factory = sqlite3.Row
connection.execute('BEGIN')
run = dict(connection.execute('SELECT id,status,stage,request_count,active_plan_revision FROM runs WHERE id=?', (RID,)).fetchone())
event_rows = connection.execute('SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? ORDER BY sequence', (RID,)).fetchall()
events = [{**dict(row), 'payload': json.loads(row['payload_json'])} for row in event_rows]
for event in events:
    event.pop('payload_json')
rows = connection.execute("SELECT step_key,input_hash,output_hash,output_json,created_at FROM steps WHERE run_id=? AND step_key='section.S02'", (RID,)).fetchall()
checkpoints = [{**dict(row), 'value': json.loads(row['output_json'])} for row in rows]
for record in checkpoints:
    record.pop('output_json')
checkpoint = next(record for record in checkpoints if record['value']['generated'] == final)
budget = dict(connection.execute('SELECT * FROM run_budgets WHERE run_id=?', (RID,)).fetchone())
approval = dict(connection.execute('SELECT * FROM approvals WHERE run_id=? AND revision=?', (RID, run['active_plan_revision'])).fetchone())
budget_actions = connection.execute('SELECT count(*) FROM budget_actions WHERE run_id=?', (RID,)).fetchone()[0]
teacher_reviews = connection.execute('SELECT count(*) FROM reviews WHERE run_id=?', (RID,)).fetchone()[0]
connection.close()

checkpoint_event = next(event for event in events if event['type'] == 'step.checkpoint' and event['payload'].get('output_hash') == checkpoint['output_hash'])
request_events = [event for event in events if event['type'] == 'provider.request']
requests_before_checkpoint = [event for event in request_events if event['sequence'] < checkpoint_event['sequence']]
new_requests = requests_before_checkpoint[11:]
checks.update({
    'checkpoint_hash_matches_database': digest(checkpoint['value']) == checkpoint['output_hash'],
    'five_new_s02_requests_total_continues_from_11_to_16': len(requests_before_checkpoint) == 16 and len(new_requests) == 5,
    'new_request_role_chain': [event['payload']['role'] for event in new_requests] == ['reviewer_math', 'repair_missing_answers', 'reviewer_math', 'repair_local_patch', 'reviewer_math'],
    'current_request_count_matches_durable_request_events': run['request_count'] == len(request_events),
    'historical_60_limit_preserved_without_expansion': json.loads(budget['defaults_json'])['requests'] == 60 and json.loads(budget['overrides_json']) == {} and budget['version'] == 0 and budget_actions == 0,
    'original_plan_identity_preserved': state['identity']['plan_hash'] == approval['hash'],
    'no_teacher_reviews': teacher_reviews == 0,
})
role_schemas = {'reviewer_math': MathReview, 'repair_missing_answers': AnswerCompletion, 'repair_local_patch': LocalPatch}
output_files = [draft / 'local-0-review-0.json', proposal_path, draft / 'local-1-review-0.json', draft / 'repair-4-patch.json', draft / 'local-2-review-0.json']
request_chain = []
for number, (event, output_file) in enumerate(zip(new_requests, output_files), 12):
    payload = event['payload']; role = payload['role']
    next_sequence = next((request['sequence'] for request in request_events if request['sequence'] > event['sequence']), checkpoint_event['sequence'])
    results = [item for item in events if event['sequence'] < item['sequence'] < next_sequence and item['type'] == 'provider.result']
    output_hash = digest(read(output_file))
    valid = any(item['payload'].get('output_hash') == output_hash and item['payload'].get('schema_attempt') == 1 for item in results)
    streamed = any(item['payload'].get('http_status') == 200 and item['payload'].get('stream_complete') is True for item in results)
    checks[f'request_{number}_schema_validated_output_matches_saved_file'] = valid
    checks[f'request_{number}_http200_complete_stream'] = streamed
    checks[f'request_{number}_prompt_and_schema_provenance_matches'] = (
        payload['prompt_hash'] == digest(raw(PROJECT / 'src/math_agent/prompts' / (role + '.md')))
        and payload['schema_hash'] == digest(role_schemas[role].model_json_schema())
        and payload['prompt_version'] == (3 if role == 'reviewer_math' else 1)
        and payload['prompt_version_source'] == 'declared_prompt_header')
    request_chain.append({'run_request_ordinal': number, 'event_sequence': event['sequence'], **payload,
        'saved_output': str(output_file.resolve()), 'output_hash': output_hash,
        'schema_validated': valid, 'complete_http200_stream': streamed, 'result_events': results})

report = checkpoint['value']['report']; compile_report = report['compile']
pdf = Path(compile_report['pdf_path']); pdf_bytes = raw(pdf)
source_bytes = raw(WORKSPACE / checkpoint['value']['source_key'])
logs = [raw(Path(path)) for path in compile_report['log_paths']]
checks.update({
    'final_local_review_no_issues': reviews[2]['issues'] == report['issues'] == report['llm_review']['issues'] == [],
    'recorded_four_symbolic_checks_pass': report['math']['status'] == 'PASS' and len(report['math']['evidence']) == 4 and all(item['status'] == 'PASS' for item in report['math']['evidence']),
    'recorded_real_windows_compile': compile_report['status'] == 'PASS' and compile_report['passes'] == 2 and compile_report['page_count'] == 6 and compile_report['engine']['path'].lower().endswith('xelatex.exe'),
    'source_sha_matches_checkpoint': digest(source_bytes) == checkpoint['value']['source_hash'],
    'pdf_bytes_sha_matches_compile_record': pdf_bytes.startswith(b'%PDF-') and digest(pdf_bytes) == compile_report['pdf_sha256'],
    'preserved_logs_confirm_six_page_output': any(b'(6 pages)' in log and b'Output written on' in log for log in logs),
})
files_unchanged = all(Path(path).read_bytes() and digest(Path(path).read_bytes()) == expected for path, expected in files.items())
checks['all_read_evidence_files_unchanged_during_audit'] = bool(files_unchanged)
result = {
    'status': 'VERIFIED_SECTION_EVIDENCE' if all(checks.values()) else 'AUDIT_FAILED',
    'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'run_id': RID, 'section_id': 'S02',
    'read_only': True, 'database_mode': 'sqlite URI mode=ro, read transaction',
    'model_calls_by_audit': 0, 'recompilation_by_audit': 'NOT_RUN', 'teacher_review': 'NOT_RUN',
    'whole_chapter_acceptance': 'NOT_CLAIMED', 'current_run_snapshot': run,
    'checks': checks, 'failed_checks': [name for name, value in checks.items() if not value],
    'hash_chain': {'old_accepted_section': digest(before), 'after_append': digest(appended),
        'after_strict_patch': digest(final), 'final_candidate_file': state['candidate_hash'],
        'database_checkpoint': checkpoint['output_hash']},
    'append': {'original_unit_count': len(before['units']), 'new_unit_ids': new_ids,
        'original_calculation_ids': [item['id'] for item in before['calculations']],
        'new_calculations': appended['calculations'][len(before['calculations']):]},
    'strict_patch': {'changed_unit_ids': targets, 'preserved_other_unit_count': len(final['units']) - len(targets),
        'removal_rule_observed': 'Each final tex equals exact prefix before newline-newline-答案： in accepted legacy tex.',
        'replacement_data': patch},
    'local_state_snapshot': state,
    'local_event_timeline': [event for event in events if event['type'] == 'local.repair_state' and event['payload'].get('section_id') == 'S02' and event['sequence'] <= checkpoint_event['sequence'] + 1],
    'request_count_at_s02_completion': len(requests_before_checkpoint), 'live_s02_request_chain': request_chain,
    'budget_snapshot': budget, 'approval_snapshot': approval,
    'math_evidence': report['math'], 'compile_evidence': compile_report,
    'review_issue_progression': [{'review_index': n, 'issues': review['issues']} for n, review in enumerate(reviews)],
    'limitations': [
        'Only the preserved S02 completion is verified; the chapter and later global review may still fail.',
        'Answer/patch proposal audit status APPLIED_UNCHECKED and math_check NOT_RUN refer to the proposal stage; later checkpoint math/compile evidence is separate.',
        'U14 warning-only reviewer observations occurred earlier without changing U14; final model reviewer returned no issues. This is not teacher adjudication or formal proof.',
        'Old reviewer prompt hash remains UNKNOWN_NOT_ARCHIVED; no historical version was invented.',
        'The six-page local PDF is the cumulative S01+S02 draft, not a final chapter delivery.',
        'Live run may advance after the read transaction; current_run_snapshot is a point-in-time observation.'
    ],
    'evidence_file_sha256': files,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': result['status'], 'failed_checks': result['failed_checks'],
    'checks': len(checks), 'files': len(files), 'current_run_snapshot': run}, ensure_ascii=False))
