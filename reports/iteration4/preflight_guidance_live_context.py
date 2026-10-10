"""Read-only verify the candidate guidance projection against the two real runs."""
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import urllib.request
import uuid

from math_agent.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
source = REPORTS / 'repair_guidance.candidate.py'
spec = importlib.util.spec_from_file_location('math_agent.guidance_preflight', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
settings = Settings(workspace=ROOT/'workspace/iteration2-live')
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def get(path):
    with client.open('http://127.0.0.1:8766' + path, timeout=20) as response:
        return json.load(response)
get('/api/session')
results = {}
for name, run_id in [('CH02', 'fd6736af6ef14be3839e019e86ca1e5c'), ('CH03', 'a45be503af594ce8aae0bb1e4c30184b')]:
    run = get('/api/runs/' + run_id)
    context = module.guidance_context(settings, run)
    results[name] = dict(status=run['status'], stage=run['stage'], request_count=run['request_count'],
        active_jobs=sum(job['status'] in ('queued', 'running') for job in run['jobs']),
        approval_matches=run['approval']['hash'] == run['plan']['hash'], context=context)
    assert results[name]['active_jobs'] == 0 and results[name]['approval_matches']
    assert context and context['section_id'] == ('S02' if name == 'CH02' else 'S03'), name
out = REPORTS / ('guidance-live-preflight-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6] + '.json')
out.write_text(json.dumps(dict(status='PASS_READ_ONLY',
    helper_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), cases=results,
    writes_to_task_state=0, model_calls=0, teacher_review='NOT_RUN'), ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(report=str(out), cases={name:{k:v for k,v in value.items() if k!='context'} for name,value in results.items()}), ensure_ascii=True))
