"""Read-only checkpoint comparison; no Store initialization and no API calls."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3

root = Path(__file__).resolve().parents[2]
workspace = root / 'workspace/iteration2-live'
cases = [('CH02', 'fd6736af6ef14be3839e019e86ca1e5c', 'S04', 'candidate-1f19b7a36820.json'),
         ('CH03', 'a45be503af594ce8aae0bb1e4c30184b', 'S03', 'candidate-8e5a43ddec81.json')]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


connection = sqlite3.connect((workspace / 'agent.db').resolve().as_uri() + '?mode=ro', uri=True)
connection.row_factory = sqlite3.Row
connection.execute('PRAGMA query_only=ON')
connection.execute('BEGIN')
snapshots = []
for chapter, run_id, section_id, prior_name in cases:
    row = dict(connection.execute('SELECT * FROM steps WHERE run_id=? AND step_key=?',
        (run_id, 'section.' + section_id)).fetchone())
    run = dict(connection.execute('SELECT id,status,stage,request_count,updated_at FROM runs WHERE id=?',
        (run_id,)).fetchone())
    snapshots.append((chapter, run_id, section_id, prior_name, row, run))
connection.rollback()
connection.close()
result = {'created_at': datetime.now(timezone.utc).isoformat(), 'access': 'sqlite mode=ro/query_only; no Store/migration',
          'real_api_requests': 0, 'new_windows_compile': 'NOT_RUN', 'pdf_visual_review': 'NOT_RUN',
          'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN', 'chapters': []}
for chapter, run_id, section_id, prior_name, row, run in snapshots:
    payload = json.loads(row['output_json'])
    output_hash_match = sha(row['output_json'].encode('utf-8')) == row['output_hash']
    assert output_hash_match
    generated = payload['generated']
    report = payload['report']
    prior_path = workspace / 'runs' / run_id / 'local-repair' / section_id / prior_name
    prior_bytes = prior_path.read_bytes()
    prior = json.loads(prior_bytes)
    before = {unit['id']: unit for unit in prior['units']}
    after = {unit['id']: unit for unit in generated['units']}
    assert list(before) == list(after)
    diffs = []
    for unit_id, new in after.items():
        old = before[unit_id]
        old_tex, new_tex = old['tex'], new['tex']
        old_count = len(re.findall(r'\\\\(?=[A-Za-z\[\]()])', old_tex))
        new_count = len(re.findall(r'\\\\(?=[A-Za-z\[\]()])', new_tex))
        reduced = re.sub(r'\\\\(?=[A-Za-z\[\]()])', lambda match: '\\', old_tex)
        diffs.append({'unit_id': unit_id, 'changed': old != new, 'tex_changed': old_tex != new_tex,
            'before_sha256': sha(canonical(old).encode()), 'after_sha256': sha(canonical(new).encode()),
            'kind_and_relation_unchanged': (old['kind'], old.get('relates_to')) == (new['kind'], new.get('relates_to')),
            'double_backslash_before_command_before': old_count, 'double_backslash_before_command_after': new_count,
            'only_reduced_command_escaping': reduced == new_tex})
    source = workspace / payload['source_key']
    source_bytes = source.read_bytes()
    source_text = source_bytes.decode('utf-8')
    pdf = Path(report['compile']['pdf_path'])
    source_hash_match = sha(source_bytes) == payload['source_hash']
    pdf_hash_match = sha(pdf.read_bytes()) == report['compile']['pdf_sha256']
    assert source_hash_match and pdf_hash_match
    lines = {match[1]: source_text.count('\n', 0, match.start()) + 1
             for match in re.finditer(r'% UNIT (S\d+\.U\d+)', source_text)}
    base = source.parent.parent
    evidence_files = [source, pdf, prior_path, base / 'compile.json', base / 'local-recovery.json']
    for pattern in ('repair-*-patch.json', 'repair-*-evidence.json', 'repair-*.json', 'review-*.json'):
        evidence_files.extend(sorted(base.glob(pattern)))
    evidence = [{'path': str(path), 'sha256': sha(path.read_bytes())} for path in dict.fromkeys(evidence_files)]
    result['chapters'].append({'chapter': chapter, 'run_snapshot': run, 'section_id': section_id,
        'checkpoint': {key: value for key, value in row.items() if key != 'output_json'},
        'checkpoint_output_hash_match': output_hash_match, 'source_hash_match': source_hash_match,
        'pdf_hash_match': pdf_hash_match, 'source_path': str(source), 'unit_source_lines': lines,
        'before_path': str(prior_path), 'before_sha256': sha(prior_bytes),
        'prior_file_unchanged_during_read': prior_bytes == prior_path.read_bytes(),
        'unit_diffs': diffs, 'changed_unit_ids': [item['unit_id'] for item in diffs if item['changed']],
        'calculations_unchanged': prior['calculations'] == generated['calculations'],
        'uncertainties_unchanged': prior['uncertainties'] == generated['uncertainties'],
        'limitation_changes': [item for item in generated['calculation_limitations'] if item not in prior['calculation_limitations']],
        'generated': generated, 'report': report, 'evidence_files': evidence})
destination = root / 'reports/iteration4/resumed-sections-semantic-audit.json'
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'saved': str(destination), 'chapters': [{
    'chapter': item['chapter'], 'changed': item['changed_unit_ids'],
    'output_hash_match': item['checkpoint_output_hash_match'], 'source_hash_match': item['source_hash_match'],
    'pdf_hash_match': item['pdf_hash_match'], 'calculations_unchanged': item['calculations_unchanged'],
    'only_escape_changes': {diff['unit_id']: diff['only_reduced_command_escaping'] for diff in item['unit_diffs'] if diff['changed']},
    'compiled_pages': item['report']['compile']['page_count'], 'math_status': item['report']['math']['status'],
    'source_hash': item['report']['compile']['pdf_sha256'],
} for item in result['chapters']]}, ensure_ascii=False))
