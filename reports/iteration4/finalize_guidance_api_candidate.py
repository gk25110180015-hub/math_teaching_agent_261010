"""Mark the exact API/test candidate validated; this does not deploy anything."""
import hashlib
import json
from pathlib import Path
import shutil

REPORTS = Path(__file__).resolve().parent
ROOT = REPORTS.parents[1]
OUT = REPORTS / 'repair-guidance-api-candidate'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((OUT / 'manifest.json').read_bytes())
validation = REPORTS / 'combined-recovery-validation/20260922-145813-9d3b56'
assert json.loads((validation/'result.json').read_bytes())['status'] == 'PASS'
context = json.loads((validation/'context.json').read_bytes())
for item in manifest['files']:
    assert sha(REPORTS / item['candidate']) == item['candidate_sha256']
    assert item in context['manifest']['files']
source = 'tests/test_repair_guidance_api.py'
candidate = REPORTS / 'test_repair_guidance_api.candidate.py'
test_item = next(item for item in context['manifest']['files'] if item['source'] == source)
assert sha(candidate) == test_item['candidate_sha256']
manifest['files'].append({**test_item, 'candidate': candidate.name})
manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT',
    validation={'path': validation.relative_to(REPORTS).as_posix(), 'passed': 128,
        'real_api': 'NOT_RUN', 'windows_compile': 'NOT_RUN', 'browser': 'NOT_RUN',
        'external_attempts': 0, 'production_unchanged': True},
    independent_review='repair-guidance-api-independent-audit.md',
    prior_failure={'path': 'combined-recovery-validation/20260922-145311-81c0b6',
        'passed': 126, 'failed': 2,
        'reason': 'New test expected PLAN_CONFLICT, while existing contract returns REVISION_CONFLICT; tests corrected, implementation unchanged'},
    teacher_review='NOT_RUN')
(OUT/'ready-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('Exact API/test candidate READY; 128 offline PASS; no deployment')
