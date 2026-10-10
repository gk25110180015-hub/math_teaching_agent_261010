"""Verify completed tests still describe deployed sources before live continuation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
suite = json.loads((REPORTS/'local-full-20260923-100540-e935d4bf.json').read_bytes())
edge_folder = REPORTS/'final-deployed-e2e/20260923-020653-0344b8'
edge = json.loads((edge_folder/'result.json').read_bytes())
assert suite['status'] == 'LOCAL_SUITE_PASS' and edge['status'] == 'PASS'
snapshots = [suite['source_snapshot_before'], json.loads((edge_folder/'source-hashes-after.json').read_bytes())]
checked = {}; mismatch = []
for snapshot in snapshots:
    for name, expected in snapshot.items():
        path = ROOT/name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        checked[name] = actual
        if actual != expected: mismatch.append(name)
result = dict(at=datetime.now(timezone.utc).isoformat(), status='PASS' if not mismatch else 'FAIL',
    checked_files=len(checked), mismatches=sorted(set(mismatch)), local_tests=1078, edge_tests=14,
    real_api='NOT_RUN', windows_compile='21 actual marked local nodes; see original results',
    teacher_review='NOT_RUN', local_service_observation='Port 8766 refused connection after pause; restart needed')
out = REPORTS/('resume-code-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(report=str(out), **result), ensure_ascii=True))
assert not mismatch
