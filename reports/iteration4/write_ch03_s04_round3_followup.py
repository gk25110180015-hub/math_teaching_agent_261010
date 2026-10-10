"""Snapshot a read-only audit of real S04 round-3 follow-up reviews/patches."""
import difflib
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

P = Path(__file__).resolve().parents[2]
O = Path(__file__).parent
W = P / 'workspace/iteration2-live'
R = W / 'runs/a45be503af594ce8aae0bb1e4c30184b'
B = W / 'b/a45be503af594ce8/sS04_00aecb9ed051'


def sha(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def record(path):
    raw = path.read_bytes()
    return {'path': str(path), 'relative_path': path.relative_to(P).as_posix(),
            'raw_sha256': sha(raw), 'value': json.loads(raw)}


def units(value):
    value = value.get('section', value)
    return {unit['id']: unit for unit in value['units']}


names = [
    ('r1_before', R / 'global-repairs/r1-37ae927f/S04-before.json'),
    ('r1_checked', R / 'global-repairs/r1-37ae927f/S04-locally-checked-c30ac4fa.json'),
    ('r2_checked', R / 'global-repairs/r2-e4e359cf/S04-locally-checked-cc72d851.json'),
    ('r3_before', R / 'global-repairs/r3-b62b4971/S04-before.json'),
    ('r3_raw', R / 'global-repairs/r3-b62b4971/S04-b685fe55-raw.json'),
    ('r3_candidate', R / 'global-repairs/r3-b62b4971/S04-b685fe55-candidate.json'),
    ('local_candidate', B / 'candidate.json'),
    ('local_normalized', B / 'candidate-normalized.json'),
    ('after_patch_3', B / 'repair-3.json'),
    ('after_patch_4', B / 'repair-4.json'),
]
versions = {label: record(path) for label, path in names}
baseline = units(versions['r1_before']['value'])['S04.U05']
assert all(units(versions[name]['value'])['S04.U05'] == baseline for name, _ in names[:8])
assert '最后证明复合极限结论' not in baseline['tex']
assert '所以 $f\\circ g$ 在 $x_0$ 处连续' in baseline['tex']
assert versions['local_candidate']['value'] == versions['local_normalized']['value']
checks = []
for before, after, expected in [
    ('r3_before', 'r3_candidate', ['S04.U03']),
    ('local_normalized', 'after_patch_3', ['S04.U05']),
    ('after_patch_3', 'after_patch_4', ['S04.U03']),
]:
    a, b = units(versions[before]['value']), units(versions[after]['value'])
    assert list(a) == list(b)
    changed = [key for key in a if a[key] != b[key]]
    assert changed == expected
    checks.append({'before': before, 'after': after, 'changed_unit_ids': changed,
        'diffs': {key: ''.join(difflib.unified_diff(a[key]['tex'].splitlines(True), b[key]['tex'].splitlines(True),
                                                   fromfile=before, tofile=after)) for key in changed}})
reviews = [record(B / f'local-{n}-review-0.json') for n in range(3)]
for n in range(3):
    reviews[n]['pipeline_review'] = record(B / f'review-{n}.json')
assert reviews[0]['value']['issues'][0]['unit_id'] == 'S04.U05'
assert reviews[0]['value']['issues'][0]['severity'] == 'blocking'
assert reviews[1]['value']['issues'][0]['unit_id'] == 'S04.U03'
assert reviews[1]['value']['issues'][0]['severity'] == 'review'
assert all(x['severity'] == 'warning' for x in reviews[2]['value']['issues'])
assert reviews[0]['pipeline_review']['value']['local_recovery']['review_identity']['candidate_hash'] == sha(versions['local_normalized']['value'])

source = B / 'compile-attempt-2/source/lecture.tex'
raw = source.read_bytes()
lines = raw.decode('utf-8').splitlines()
line = next(i for i, text in enumerate(lines) if '最后证明复合极限结论' in text)
marker = next(i for i in range(line, -1, -1) if lines[i].startswith('% UNIT '))
end = next(i for i in range(line + 1, len(lines)) if lines[i].startswith('% UNIT '))
assert lines[marker] == '% UNIT S02.U03'
misattribution = {'source_path': str(source), 'source_raw_sha256': sha(raw),
    'actual_unit_id': 'S02.U03', 'unit_marker_line_1based': marker + 1,
    'quoted_proof_line_1based': line + 1,
    'actual_proof': '\n'.join(lines[line:end]),
    'incorrect_review_target': 'S04.U05',
    'actual_target_tex_sha256': sha(baseline['tex'].encode()),
    'original_target_already_proves_composition_continuity': True}

c = sqlite3.connect((W / 'agent.db').as_uri() + '?mode=ro', uri=True)
c.row_factory = sqlite3.Row
c.execute('BEGIN')
run = dict(c.execute('SELECT id,status,stage,request_count,updated_at FROM runs WHERE id=?', (R.name,)).fetchone())
events = [dict(row) for row in c.execute("SELECT sequence,timestamp,type,payload_json FROM events WHERE run_id=? AND (type='provider.result' OR type LIKE 'budget.%') ORDER BY sequence", (R.name,))]
c.rollback()
c.close()
for event in events:
    event['payload'] = json.loads(event.pop('payload_json'))
for review in reviews:
    output_hash = sha(review['value'])
    review['provider_result_matches'] = [event for event in events if event['type'] == 'provider.result' and event['payload'].get('output_hash') == output_hash]
    assert len(review['provider_result_matches']) == 1
state = record(R / 'local-repair/S04.json')
compile_record = record(B / 'compile-attempt-2/compile.json')
report = {
    'schema_version': 1, 'captured_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'INTERMEDIATE_S04_ROUND3_FOLLOWUP_NOT_FINAL_CH03_DELIVERY',
    'run_snapshot': run, 'api_calls_by_this_audit': 0, 'production_mutations': 0,
    'versions': versions, 'change_checks': checks, 'reviews': reviews,
    'patches': [record(B / f'repair-{n}-patch.json') for n in (3, 4)],
    'patch_evidence': [record(B / f'repair-{n}-evidence.json') for n in (3, 4)],
    'misattributed_proof': misattribution, 'local_state': state,
    'observed_existing_windows_compile': compile_record,
    'budget_events': [event for event in events if event['type'].startswith('budget.')],
    'findings': {
        'U05_blocking_issue': 'CONFIRMED_FALSE_POSITIVE_WRONG_UNIT_EVIDENCE_S02_U03_ATTRIBUTED_TO_S04_U05',
        'U05_text_regression_before_patch3': 'NOT_FOUND_EXACT_UNIT_EQUALITY_FROM_R1_BEFORE_TO_R3_NORMALIZED',
        'U05_patch3_effect': 'EXPLICIT_NEIGHBORHOOD_SHRINKING_IN_ALREADY_VALID_CONTINUITY_PROOF',
        'U03_patch4_trigger': 'UNCHANGED_TEXT_WARNING_TO_REVIEW_SEVERITY_DRIFT_CONTEXT_INHERITANCE_AMBIGUITY',
        'U03_counterexample': 'ONE_SIDED_DOMAIN_DOES_NOT_SATISFY_OPENING_TWO_SIDED_CLASSIFICATION_PREMISE_NOT_A_PROOF_OF_CONTRADICTION',
        'U03_patch4_effect': 'EXPLICITLY_RETAINS_TWO_SIDED_CLASSIFICATION_AND_INDEPENDENT_ONE_SIDED_LIMIT_DEFINITIONS',
        'old_per_unit_limit2': 'PATCH4_U03_WOULD_BLOCK_AT_PRIOR_COUNT2_CURRENT6_ALLOWED_THIRD_ACCEPTED_CHANGE',
        'patch3_budget_distinction': 'U05_COUNT1_TO2_WOULD_NOT_ITSELF_BE_BLOCKED_BY_PER_UNIT_LIMIT2',
    },
    'tests': {'audit_assertions': 'PASS', 'new_mock_tests': 'NOT_RUN_NO_IMPLEMENTATION_CHANGE',
        'new_real_api_tests': 'NOT_RUN_READ_ONLY_REAL_HISTORY', 'new_windows_compile': 'NOT_RUN_EXISTING_COMPILER_RECORD_OBSERVED',
        'agent_visual': 'NOT_RUN', 'teacher_math': 'NOT_RUN', 'teacher_visual': 'NOT_RUN'},
}
target = O / 'CH03-S04-round3-local-followup.json'
assert not target.exists()
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'report': str(target), 'raw_sha256': sha(target.read_bytes()), 'run_snapshot': run,
                  'local_phase': state['value']['phase'], 'compile_status': compile_record['value'].get('status'),
                  'proof_source_unit': misattribution['actual_unit_id'], 'proof_line': line + 1}, ensure_ascii=False))
