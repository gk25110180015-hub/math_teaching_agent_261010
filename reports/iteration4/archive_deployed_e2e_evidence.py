"""Archive this completed isolated E2E batch without touching earlier reports."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / 'reports/iteration4/full-e2e-deployed/20260920-152336-152ba3'
RUNTIME = ROOT / 'workspace/t/e2e-152ba3'
MODEL_ROOT = ROOT / 'reports/iteration3/model-selection-e2e'
MODEL_BATCHES = [
    '20260920-232530-f6d374', '20260920-232533-7f0eeb',
    '20260920-232535-c256a9', '20260920-232537-ae16b0', '20260920-232539-960e1d',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = json.loads((BATCH / 'source-hashes-before.json').read_text(encoding='utf-8-sig'))
after = json.loads((BATCH / 'source-hashes-after.json').read_text(encoding='utf-8-sig'))
assert before == after
assert all(sha(Path(row['Path'])).upper() == row['Hash'] for row in after)
suite = ElementTree.parse(BATCH / 'pytest.xml').getroot().find('testsuite')
assert suite is not None and suite.attrib['tests'] == '12'
assert all(suite.attrib[key] == '0' for key in ('errors', 'failures', 'skipped'))
copied = []
for name in MODEL_BATCHES:
    source = MODEL_ROOT / name
    target = BATCH / 'model-selection' / name
    evidence = json.loads((source / 'evidence.json').read_text(encoding='utf-8'))
    assert evidence['real_api'] == 'NOT_RUN'
    assert evidence['model_http_transport'] == 'MOCK_TRANSPORT'
    assert not evidence['javascript_errors'] and not evidence['external_browser_requests_blocked']
    shutil.copytree(source, target)  # Refuses to overwrite any previous archive.
    files = []
    for path in source.rglob('*'):
        if path.is_file():
            relative = path.relative_to(source)
            assert sha(path) == sha(target / relative)
            files.append({'file': relative.as_posix(), 'sha256': sha(path)})
    copied.append({'original': source.relative_to(ROOT).as_posix(),
                   'archive': target.relative_to(ROOT).as_posix(),
                   'test_name': evidence['test_name'], 'files': files})

databases = []
for original in sorted(RUNTIME.rglob('agent.db')):
    relative = original.relative_to(RUNTIME)
    target = BATCH / 'databases' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True) as connection:
        with sqlite3.connect(target) as archive:
            connection.backup(archive)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        reviews = connection.execute('SELECT count(*) FROM reviews').fetchone()[0] if 'reviews' in tables else 0
        assert reviews == 0, 'These E2E cases do not submit human reviews'
        runs = [dict(zip(('status', 'count'), row)) for row in connection.execute('SELECT status,count(*) FROM runs GROUP BY status')]
    databases.append({'original': original.relative_to(ROOT).as_posix(),
                      'archive': target.relative_to(ROOT).as_posix(),
                      'archive_sha256': sha(target), 'run_statuses': runs, 'human_reviews': reviews})
assert databases
result = {
    'status': 'PASS', 'tests': 12, 'failed': 0, 'skipped': 0, 'elapsed_seconds': 125.05,
    'production_source_hashes_unchanged': True, 'source_hashes': after,
    'real_edge': 'PASS', 'model_provider': 'MOCK_OR_HTTPX_MOCK_TRANSPORT',
    'windows_compile': 'PASS_FOR_COMPILING_WORKFLOW_CASES',
    'real_api': 'NOT_RUN', 'teacher_mathematics_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
    'human_reviews_submitted': 0, 'runtime_preserved': RUNTIME.relative_to(ROOT).as_posix(),
    'model_selection_archives': copied, 'database_snapshots': databases,
}
target = BATCH / 'result.json'
with target.open('x', encoding='utf-8') as output:
    json.dump(result, output, ensure_ascii=False, indent=2)
print(json.dumps({'status': result['status'], 'tests': result['tests'],
                  'model_evidence_archives': len(copied), 'database_snapshots': len(databases),
                  'source_unchanged': True, 'human_reviews': 0,
                  'result': target.relative_to(ROOT).as_posix()}))
