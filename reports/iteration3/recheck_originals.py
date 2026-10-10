"""Read-only rehash of the 53 original reference files in the prior manifest."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
baseline = ROOT / 'reports/iteration2/final-originals-20260920-051655-382274.json'
baseline_bytes = baseline.read_bytes()
originals = json.loads(baseline_bytes)['original_files']
assert len(originals) == 53 and len({item['path'] for item in originals}) == 53
results = []
for item in originals:
    path = Path(item['path']).resolve()
    assert path.is_relative_to(ROOT.parent) and not path.is_relative_to(ROOT)
    row = {'path': str(path), 'expected_sha256': item['expected_sha256']}
    try:
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        row.update(observed_sha256=observed,
                   status='PASS' if observed == row['expected_sha256'] else 'FAIL')
    except OSError as exc:
        row.update(observed_sha256=None, status='UNREADABLE', error_type=type(exc).__name__)
    results.append(row)
report = {'created_at': datetime.now(timezone.utc).isoformat(),
          'verification_mode': 'read-only SHA256; files not modified',
          'baseline_manifest': str(baseline),
          'baseline_manifest_sha256': hashlib.sha256(baseline_bytes).hexdigest(),
          'file_count': len(results), 'checked_scope': '53 manifest-listed originals, not an inventory of later added files',
          'status': 'PASS' if all(row['status'] == 'PASS' for row in results) else
                    'FAIL' if any(row['status'] == 'FAIL' for row in results) else 'INCOMPLETE',
          'original_files': results}
output = ROOT / 'reports/iteration3' / ('originals-recheck-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
with output.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({'status': report['status'], 'file_count': report['file_count'], 'report': str(output)}, ensure_ascii=False))
raise SystemExit(0 if report['status'] == 'PASS' else 2)
