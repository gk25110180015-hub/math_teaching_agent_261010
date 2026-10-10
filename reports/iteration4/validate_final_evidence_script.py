"""Offline syntax/classification checks only; do not call the final collector."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import uuid

OUT = Path(__file__).resolve().parent
source = OUT / 'collect_final_live_evidence.py'
compile(source.read_text(encoding='utf-8'), str(source), 'exec')
module = runpy.run_path(str(source))
events = []
for index, result in enumerate([
    {'http_status': 200},
    {'http_status': 200, 'output_hash': 'synthetic-validated-body', 'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3}},
    {'http_status': 200, 'status': 'TOTAL_TIMEOUT', 'billing_uncertain': True},
    {'http_status': 504, 'billing_uncertain': True},
], 1):
    events.append({'sequence': len(events)+1, 'timestamp': '2026-09-20T16:00:00+00:00',
                   'type': 'provider.request', 'payload': {'role': 'reviewer_math', 'model': 'gpt-6-astra', 'call_id': str(index)}})
    events.append({'sequence': len(events)+1, 'timestamp': '2026-09-20T16:00:01+00:00',
                   'type': 'provider.result', 'payload': {'role': 'reviewer_math', 'call_id': str(index), **result}})
metrics = module['request_metrics'](events, 4, 240)
summary = module['request_summary'](metrics)
assert summary['totals']['attempts'] == 4
assert summary['totals']['validated_successes'] == 1
assert summary['totals']['recorded_failures'] == 2
assert summary['totals']['completion_uncertain'] == 1
assert metrics['requests'][0]['status'] == 'HTTP_200'
assert metrics['requests'][2]['status'] == 'TOTAL_TIMEOUT'
stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
target = OUT / ('final-evidence-script-validation-' + stamp + '.json')
result = {'status': 'PASS', 'created_at': datetime.now(timezone.utc).isoformat(),
          'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'checks': ['Python syntax', 'headers-only HTTP 200 is uncertain',
                     'SCHEMA_VALIDATED only is success', 'HTTP 200 + TOTAL_TIMEOUT is failure',
                     'HTTP 504 is failure'],
          'synthetic_request_summary': summary,
          'real_api': 'NOT_RUN', 'live_database_read': 'NOT_RUN', 'final_collection': 'NOT_RUN'}
with target.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({'status': 'PASS', 'evidence': str(target), 'final_collection': 'NOT_RUN'}))
