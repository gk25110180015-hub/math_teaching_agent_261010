from pathlib import Path
from datetime import datetime,timezone
import json
from math_agent.settings import Settings,PROJECT_ROOT
from math_agent.benchmark import BenchmarkRunner
from math_agent.util import digest,write_json,scrub
p=PROJECT_ROOT
settings=Settings(workspace=p/'workspace/iteration2-live',max_requests_per_run=60)
write_json(p/'reports/iteration2/live_retry3_ch01_source_snapshot.json',{'started_at':datetime.now(timezone.utc).isoformat(),'case':'CH01','per_run_budget':60,'total_budget':240,'live_enabled':settings.live_api_enabled,'key_configured':bool(settings.api_key.get_secret_value()),'source_files':{str(f.relative_to(p)):digest(f.read_bytes()) for folder in ('src','prompts','configs','templates') for f in sorted((p/folder).rglob('*')) if f.is_file() and '__pycache__' not in f.parts}})
r=BenchmarkRunner(settings,p/'reports/iteration2/live-lectures',per_run_budget=60,total_budget=240)
try:
    run=r.execute_case('CH01',retry_failed=True)
    result=r.analyze('CH01')
    print(json.dumps({'case':'CH01','status':run['status'],'stage':run['stage'],'request_count':run['request_count'],'error':run['error'],'teacher_visual_review':'NOT_RUN'},ensure_ascii=True))
except BaseException as exc:
    write_json(p/'reports/iteration2/live_retry3_ch01_failure.json',{'error_type':type(exc).__name__,'message':scrub(str(exc))})
    raise
finally:
    r.save()
