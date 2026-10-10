"""Freeze narrow transport delta after independent review and exact mock provenance."""
import hashlib
import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
audit = OUT/'provider-transport-recovery-independent-audit.md'
assert audit.exists()
evidence = OUT/'feedback-receipts-validation/20260920-183027-64c540'
context = json.loads((evidence/'context.json').read_bytes())
result = json.loads((evidence/'result.json').read_bytes())
assert result['status'] == 'PASS' and result['production_unchanged']
path = OUT/'feedback-assessment-manifest.json'
manifest = json.loads(path.read_bytes())
assert manifest['files'] == context['manifest']['pipeline_manifest']['files']
for item in manifest['files']:
    assert sha(OUT/item['candidate']) == item['candidate_sha256']
    target = ROOT/item['source']
    assert (sha(target) if target.exists() else None) == item['baseline_sha256']
for name, expected in context['tests'].items(): assert sha(ROOT/name) == expected
suites = list(ET.parse(evidence/'pytest.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests', 0)) for s in suites) == 117
assert all(not int(s.get(k, 0)) for s in suites for k in ('failures','errors','skipped'))
database = ROOT/'workspace/iteration2-live/agent.db'
with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as connection:
    connection.row_factory = sqlite3.Row
    rows = connection.execute('SELECT sequence,timestamp,type,payload_json FROM events WHERE run_id=? AND sequence BETWEEN 1892 AND 1895 ORDER BY sequence',
        ('fd6736af6ef14be3839e019e86ca1e5c',)).fetchall()
snapshot = {'mode': 'READ_ONLY_EXISTING_EVENTS', 'raw_sse_archive': 'NOT_AVAILABLE_IN_ORIGINAL_IMPLEMENTATION',
    'root_cause_specific_payload': 'UNDETERMINED', 'new_api_calls': 0,
    'events': [{**dict(row), 'payload_sha256': hashlib.sha256(row['payload_json'].encode()).hexdigest()} for row in rows]}
snapshot_path = OUT/'CH02-request101-existing-events.json'
if snapshot_path.exists(): assert json.loads(snapshot_path.read_bytes()) == snapshot
else: snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT',
    test_classification='PRIOR_FEEDBACK_118_PASS_PLUS_FINAL_TRANSPORT_117_PASS',
    mock_test_evidence=evidence.relative_to(OUT).as_posix(), tests=context['tests'],
    transport_independent_review={'path': audit.name, 'sha256': sha(audit)},
    transport_report='PROVIDER_TRANSPORT_RECOVERY.md',
    real_failure_evidence={'path': snapshot_path.name, 'sha256': sha(snapshot_path)},
    real_api='NOT_RUN_FOR_TRANSPORT_DELTA', deployed_full_suite='NOT_RUN')
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
delta = OUT/'provider-transport-recovery-manifest.json'
value = json.loads(delta.read_bytes())
value.update(status='READY_FOR_REVIEWED_DEPLOYMENT', test_evidence=evidence.relative_to(OUT).as_posix(),
    independent_review={'path': audit.name, 'sha256': sha(audit)})
delta.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': manifest['status'], 'manifest_sha256': sha(path), 'files': len(manifest['files'])}))
