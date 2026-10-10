"""Capture formal CH02 recheck progress read-only; never alter task or content."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
WS = ROOT / 'workspace/iteration2-live'
RID = 'fd6736af6ef14be3839e019e86ca1e5c'
JOB = '4678ed20f5c44ad89b289ffcee4d8143'
PRE = ROOT / 'reports/iteration4/CH02-pre-feedback-semantic-visual.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture(path):
    raw = path.read_bytes()
    parsed = json.loads(raw)
    return {'path': str(path), 'sha256': sha(raw), 'value': parsed,
            'unchanged_during_read': raw == path.read_bytes()}


before = json.loads(PRE.read_bytes())
old_sections = {s['section_id']: s for s in before['sections']}
c = sqlite3.connect((WS / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
c.execute('PRAGMA query_only=ON')
c.execute('BEGIN')
run = dict(c.execute('SELECT id,status,stage,request_count,active_plan_revision,updated_at FROM runs WHERE id=?', (RID,)).fetchone())
job = dict(c.execute('SELECT * FROM jobs WHERE id=? AND run_id=?', (JOB, RID)).fetchone())
rows = [dict(c.execute('SELECT rowid,* FROM steps WHERE run_id=? AND step_key=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (RID, 'section.S0' + str(i))).fetchone()) for i in range(1, 6)]
feedback = [dict(r) for r in c.execute("SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? AND type='checks.rerun_requested' ORDER BY sequence DESC LIMIT 1", (RID,))]
c.rollback()
c.close()
sections = []
for row in rows:
    output = json.loads(row.pop('output_json'))
    sid = row['step_key'].split('.')[1]
    old = old_sections[sid]['generated']
    new = output['generated']
    old_units = {u['id']: u for u in old['units']}
    new_units = {u['id']: u for u in new['units']}
    changes = [{'unit_id': uid, 'before': old_units.get(uid), 'after': new_units.get(uid)}
               for uid in dict.fromkeys([*old_units, *new_units]) if old_units.get(uid) != new_units.get(uid)]
    state = capture(WS / 'runs' / RID / 'local-repair' / (sid + '.json'))
    candidate = capture(WS / state['value']['candidate_key'])
    assert candidate['sha256'] == state['value']['candidate_hash']
    last_review_key = state['value'].get('last_review_key')
    last_review = capture(WS / last_review_key) if last_review_key else None
    sections.append({'section_id': sid, 'latest_checkpoint': row, 'output': output,
        'changed_vs_pre_feedback': changes,
        'non_unit_fields_changed': [k for k in dict.fromkeys([*old, *new]) if k != 'units' and old.get(k) != new.get(k)],
        'local_recovery': state, 'candidate': candidate, 'last_review': last_review,
        'candidate_equals_checkpoint': candidate['value'] == new})

evidence_dir = WS / 'b/fd6736af6ef14be3/sS02_2160fbbb764d'
semantic_false_positive = {name: capture(evidence_dir / name) for name in [
    'candidate-normalized.json', 'local-0-review-0.json', 'review-0.json',
    'repair-5-patch.json', 'repair-5-evidence.json', 'repair-5.json', 'local-1-review-0.json']}
boundary_dir = WS / 'b/fd6736af6ef14be3/sS04_ec8e066e11da'
boundary_evidence = {name: capture(boundary_dir / name) for name in [
    'candidate-normalized.json', 'local-0-review-0.json',
    'repair-6-patch.json', 'repair-6-evidence.json', 'repair-6.json', 'local-1-review-0.json']}
feedback_evidence = {}
for name in ('chapter-coverage-912a485a-feedback.json', 'chapter-coverage-912a485a-review-0.json'):
    path = WS / 'runs' / RID / name
    if path.exists():
        feedback_evidence[name] = capture(path)
calculation_evidence = {}
for key in (
    'runs/' + RID + '/local-repair/S03/candidate-0c54e0f5d2f5.json',
    'runs/' + RID + '/local-repair/S03/candidate-095388d71edf.json',
    'b/fd6736af6ef14be3/sS03_2df6bfc3c18e/repair-4-patch.json',
    'b/fd6736af6ef14be3/sS03_2df6bfc3c18e/repair-4-evidence.json',
):
    path = WS / key
    if path.exists():
        calculation_evidence[key] = capture(path)
result = {'created_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'FORMAL_FEEDBACK_RECHECK_INTERMEDIATE_NOT_FINAL', 'read_only': True,
    'api_calls_by_auditor': 0, 'new_compile_by_auditor': 'NOT_RUN', 'teacher_acceptance': 'NOT_RUN',
    'run': run, 'job': job, 'feedback_event': feedback,
    'pre_feedback_pdf_sha256': before['artifact_pdf']['sha256'],
    'sections': sections, 'feedback_first_cycle_evidence': feedback_evidence,
    'S03_calculation_AST_recovery_evidence': calculation_evidence,
    'S02_U10_semantic_false_positive_evidence': semantic_false_positive,
    'S04_U03_boundary_notation_evidence': boundary_evidence,
    'S04_U03_independent_assessment': {
        'finding': 'EXPLICIT_SMALLEST_INDEX_AND_ELLIPSIS_CONVENTION_CLARIFICATION',
        'old_route': 'The even-partial-sum proof is valid when the empty middle block for m=1 is understood; the displayed terminal pair uses index 2m-2 and is ambiguous at m=1 without that convention.',
        'new_route': 'The patch proves S2=b1-b2<=b1 separately and restricts the displayed middle-block expansion to m>=2. All subsequent monotonic-limit reasoning is preserved.',
        'new_proof': 'CORRECT_NO_NEW_HYPOTHESES',
        'not_a_counterexample_to_alternating_series_theorem': True},
    'S02_U10_independent_assessment': {
        'original_proof': 'CORRECT', 'model_criticism': 'SEMANTIC_FALSE_POSITIVE_NOT_QUOTE_MISATTRIBUTION',
        'reason': 'Under contradiction, sum(a+b) and sum(a) both converge. Apply the proved linear-combination theorem to those two series with coefficients 1 and -1 to obtain convergence of sum(b), a contradiction. No divergent sum is subtracted.',
        'new_proof': 'CORRECT_EXPLICIT_PARTIAL_SUM_CLARIFICATION',
        'classification': 'UNNECESSARY_MATHEMATICAL_REPAIR_BUT_VALID_CLARIFICATION',
        'do_not_count_as_corrected_mathematical_error': True,
        'do_not_rollback_or_reroll': True}}
folder = ROOT / 'reports/iteration4/CH02-feedback-tracking'
folder.mkdir(exist_ok=True)
dest = folder / ('snapshot-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.json')
dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'snapshot': str(dest), 'run': run, 'sections': [{'id': s['section_id'],
    'rowid': s['latest_checkpoint']['rowid'], 'changed_unit_ids': [u['unit_id'] for u in s['changed_vs_pre_feedback']],
    'phase': s['local_recovery']['value']['phase'],
    'candidate_equals_checkpoint': s['candidate_equals_checkpoint']} for s in sections]}, ensure_ascii=False, indent=2))
