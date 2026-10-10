"""Pin the API and a read-only helper snapshot for offline validation."""
import hashlib
import json
from pathlib import Path
import shutil

REPORTS = Path(__file__).resolve().parent
ROOT = REPORTS.parents[1]
OUT = REPORTS / 'repair-guidance-api-candidate'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((OUT / 'manifest.json').read_bytes())
for source, candidate, name in [
    ('src/math_agent/repair_guidance.py', 'repair_guidance.candidate.py', 'helper-pinned.py'),
    ('tests/test_repair_guidance_api.py', 'test_repair_guidance_api.candidate.py', 'test-pinned.py'),
]:
    target = OUT / name
    shutil.copyfile(REPORTS / candidate, target)
    original = ROOT / source
    manifest['files'].append(dict(source=source, candidate=target.relative_to(REPORTS).as_posix(),
        baseline_sha256=sha(original) if original.exists() else None, candidate_sha256=sha(target)))
(OUT / 'test-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('API test snapshot ready; production unchanged')
