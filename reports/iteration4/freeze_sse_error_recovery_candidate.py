"""Bind the small transport candidate to its actual offline regression result."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; REPORTS=Path(__file__).resolve().parent
OUT=REPORTS/'sse-error-recovery-candidate'
validation=REPORTS/'combined-recovery-validation/20260923-091907-824890'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path=OUT/'manifest.json'; manifest=json.loads(manifest_path.read_bytes())
context=json.loads((validation/'context.json').read_bytes())
result=json.loads((validation/'result.json').read_bytes())
assert context['manifest_sha256']==sha(manifest_path) and result['status']=='PASS'
assert result['production_unchanged'] and not result['external_network_attempts']
for item in manifest['files']:
    assert sha(REPORTS/item['candidate'])==item['candidate_sha256']
    original=ROOT/item['source']
    assert (sha(original) if original.exists() else None)==item['baseline_sha256']
manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT', validation={
    'path':validation.relative_to(REPORTS).as_posix(),'passed':157,'real_api_excluded':1,
    'new_tests':20,'real_api':'NOT_RUN','windows_compile':'NOT_RUN','browser':'NOT_RUN','teacher_review':'NOT_RUN'},
    review='SSE_ERROR_RECOVERY.md', production_modified=False)
(OUT/'ready-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Exact transport candidate READY; no production writes')
