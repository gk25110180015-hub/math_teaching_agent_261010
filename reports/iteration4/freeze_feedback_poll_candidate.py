"""Freeze reviewed browser candidates after their isolated RED/GREEN run."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
folder = REPORTS/'feedback-poll-candidate'
candidate = folder/'test_feedback_receipts_candidate.py'
text = candidate.read_text(encoding='utf-8')
imports = '''import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/e2e'))
'''
assert text.count(imports) == 1
text = text.replace(imports, 'import re\n', 1)
start = text.index("    candidate_js = os.environ.get('MATH_AGENT_E2E_APP_JS_CANDIDATE')")
end = text.index('    posts = []', start)
text = text[:start] + text[end:]
assert text.count("'candidate_js': candidate_js") == 1
text = text.replace("'candidate_js': candidate_js", "'app_js_source': 'deployed_static_asset'", 1)
ast.parse(text)
delivered = folder/'test_feedback_receipts.delivered.py'
assert not delivered.exists()
delivered.write_text(text, encoding='utf-8')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = folder/'manifest.json'
before = manifest_path.read_bytes()
(folder/'manifest.before-validation.json').write_bytes(before)
manifest = json.loads(before)
red = REPORTS/'feedback-poll-validation/red-20260922-093722-6c6c22'
green = REPORTS/'feedback-poll-validation/green-20260922-093829-0849b9'
for path in (red,green):
    result=json.loads((path/'result.json').read_bytes())
    assert result['expected_result_observed'] and result['source_and_tests_unchanged']
    assert all(item['human_reviews']==item['human_review_events']==0 for item in result['database_snapshots'])
    observations=list(path.rglob('receipt-polling-evidence.json'))
    assert len(observations)==1
    observed=json.loads(observations[0].read_bytes())
    assert observed['snapshot_get_hits']==observed['held_event_requests']==1
    assert observed['event_requests_released_at_observation'] is False
    assert observed['manual_refresh_after_route_installation'] is False
manifest['files'][1]['candidate']='feedback-poll-candidate/test_feedback_receipts.delivered.py'
manifest['files'][1]['candidate_sha256']=sha(delivered)
manifest.update(status='READY_FOR_REVIEWED_DEPLOYMENT',ready_at=datetime.now(timezone.utc).isoformat(),
    validation={'red':str(red.relative_to(REPORTS)), 'green':str(green.relative_to(REPORTS)),
        'real_edge':'RED_then_GREEN','windows_compile':'PASS_GREEN', 'model':'MOCK',
        'real_api':'NOT_RUN','teacher_review':'NOT_RUN',
        'harness_sha256':sha(candidate), 'delivered_test_harness_difference':
        'Removed reports path/sys.path and candidate JS interception hooks only; retained held-events scenario, 10-second DOM, draft, request-hit and original empty-feedback assertions.'})
for item in manifest['files']:
    assert sha(ROOT/item['source'])==item['baseline_sha256']
    assert sha(REPORTS/item['candidate'])==item['candidate_sha256']
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2), encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
