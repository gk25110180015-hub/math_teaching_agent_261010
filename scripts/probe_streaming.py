"""Explicit live SSE capability probe. Records no headers or credentials."""
import json
import time
from pathlib import Path
import httpx
from math_agent.settings import Settings
from math_agent.util import write_json

s=Settings()
assert s.live_api_enabled and s.api_key.get_secret_value(), 'Live API not configured'
report={'capability':'text_streaming','status':'NOT_RUN','model':s.model,'chunks':0,'completed':False,'usage':None}
started=time.monotonic()
try:
    with httpx.Client(timeout=httpx.Timeout(90,connect=15),trust_env=False,follow_redirects=False) as client:
        with client.stream('POST',s.api_base_url.rstrip('/')+'/chat/completions',
            headers={'Authorization':'Bearer '+s.api_key.get_secret_value()},
            json={'model':s.model,'messages':[{'role':'user','content':'只回复 OK。'}],'temperature':0.7,'stream':True}) as response:
            report['http_status']=response.status_code
            report['content_type']=response.headers.get('content-type','')
            response.raise_for_status()
            parts=[]
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                raw=line[5:].strip()
                if raw=='[DONE]':
                    report['completed']=True
                    break
                body=json.loads(raw)
                report['chunks']+=1
                if 'usage' in body:
                    report['usage']=body['usage']
                for choice in body.get('choices',[]):
                    parts.append(choice.get('delta',{}).get('content') or '')
            report['response']=''.join(parts)[:100]
            report['status']='PASS' if report['completed'] and report['response'].strip()=='OK' else 'FAIL'
except Exception as exc:
    report.update(status='FAIL',error_type=type(exc).__name__)
report['elapsed_seconds']=round(time.monotonic()-started,3)
write_json(Path('reports/iteration2/streaming_probe.json'),report)
print(json.dumps(report,ensure_ascii=True))
