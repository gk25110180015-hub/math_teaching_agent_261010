"""Freeze reviewed candidates after checking exact test/candidate provenance."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
report = OUT/sys.argv[1]
assert report.is_file(), 'Independent review report must exist before READY'
path = OUT/'feedback-assessment-manifest.json'
manifest = json.loads(path.read_bytes())
evidence = OUT/'feedback-receipts-validation/20260920-181912-456058'
context = json.loads((evidence/'context.json').read_bytes())
result = json.loads((evidence/'result.json').read_bytes())
assert result['status'] == 'PASS' and result['production_unchanged']
tested = context['manifest']['pipeline_manifest']['files']
assert manifest['files'] == tested
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for entry in manifest['files']:
    assert sha(OUT/entry['candidate']) == entry['candidate_sha256']
    target = ROOT/entry['source']
    assert (sha(target) if target.exists() else None) == entry['baseline_sha256']
for name, expected in context['tests'].items():
    assert sha(ROOT/name) == expected, 'Test changed after frozen successful suite'
suites = list(ET.parse(evidence/'pytest.xml').getroot().iter('testsuite'))
assert sum(int(s.get('tests', 0)) for s in suites) == 118
assert all(int(s.get('failures', 0)) == 0 and int(s.get('errors', 0)) == 0 and int(s.get('skipped', 0)) == 0 for s in suites)
manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT', test_classification='MOCK_118_PASS',
    mock_test_evidence=evidence.relative_to(OUT).as_posix(),
    tests=context['tests'], independent_review={'path': report.relative_to(OUT).as_posix(), 'sha256': sha(report)},
    final_saved_real_response_replay={'path': 'feedback-assessment-final-saved-replay.json',
        'sha256': sha(OUT/'feedback-assessment-final-saved-replay.json'),
        'protocol_evidence_pass': 2, 'strict_expected_match': '1/2', 'new_api_calls': 0},
    windows_compile='NOT_RUN_IN_THIS_CANDIDATE_BATCH', real_browser='NOT_RUN_IN_THIS_CANDIDATE_BATCH',
    teacher_review='NOT_RUN', report='FEEDBACK_ASSESSMENT_CANDIDATE.md')
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': manifest['status'], 'manifest_sha256': sha(path)}, ensure_ascii=False))
