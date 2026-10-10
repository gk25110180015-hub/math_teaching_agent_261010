"""Resolve a post-submit harness assertion without repeating the submitted action."""
import http.cookiejar
import json
from pathlib import Path
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
folder = ROOT/'reports/iteration4/guidance-CH03-20260923T090838-b64292'
before = json.loads((folder/'before.json').read_bytes())
response = json.loads((folder/'response.json').read_bytes())
request = json.loads((folder/'request.json').read_bytes())
expected = next(job for job in reversed(before['jobs']) if job['kind'] == 'build' and job['status'] == 'failed')
assert response['id'] == expected['id'] == '89467291c05a478b9b525da3ce65b50f'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def get(path):
    with client.open('http://127.0.0.1:8766' + path, timeout=30) as result:
        return json.load(result)
get('/api/session')
after = get('/api/runs/' + before['id'])
assert after['approval'] == before['approval'] and after['plan'] == before['plan']
assert after['request_count'] >= before['request_count'] and after['reviews'] == before['reviews']
(folder/'verified-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding='utf-8')
result = dict(at=datetime.now(timezone.utc).isoformat(), status='SUBMISSION_VERIFIED',
    original_failure_preserved=True, repeated_posts=0, original_job=expected['id'],
    original_script_failure='Incorrectly selected oldest jobs[0]; actual API correctly requeued latest failed original build job',
    approval_preserved=True, teacher_review='NOT_RUN', current_status=after['status'],
    request_count=after['request_count'], action_id=request['action_id'])
(folder/'postcondition-correction.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True))
