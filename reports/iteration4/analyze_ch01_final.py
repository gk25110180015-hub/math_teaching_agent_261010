"""Measure CH01 in a new report directory; preserve the original benchmark."""
import copy
import json
from pathlib import Path
import shutil
from math_agent.benchmark import BenchmarkRunner
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import digest, now, write_json

old = PROJECT_ROOT / 'reports/iteration2/live-lectures'
target = PROJECT_ROOT / 'reports/iteration4/ch01-live-lectures'
historical = json.loads((old / 'benchmark_state.json').read_bytes())
state_path = target / 'benchmark_state.json'
if not state_path.exists():
    write_json(state_path, {'schema_version': 1, 'created_at': now(),
        'workspace': historical['workspace'], 'actor': 'benchmark_driver',
        'teacher_visual_review': 'NOT_RUN', 'per_run_budget': 60, 'total_budget': 60,
        'execution_mode': 'ANALYZE_ONLY; actual execution uses formal HTTP and worker',
        'historical_manifest': str(old / 'benchmark_state.json'),
        'historical_manifest_sha256': digest((old / 'benchmark_state.json').read_bytes()),
        'cases': {'CH01': {key: copy.deepcopy(historical['cases']['CH01'][key]) for key in
            ('run_id', 'started_epoch', 'dataset', 'topic', 'teacher_visual_review')}}})
    source = old / 'references/CH01/metrics.json'
    dest = target / 'references/CH01/metrics.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
settings = Settings(workspace=Path(historical['workspace']), api_key='', deepseek_api_key='',
                    live_api_enabled=False, max_requests_per_run=60)
runner = BenchmarkRunner(settings, target, per_run_budget=60, total_budget=60)
current = runner.service.get(runner.state['cases']['CH01']['run_id'])
assert current['status'] == 'AWAITING_USER_REVIEW' and not any(
    j['status'] in ('running', 'queued') for j in current['jobs'])
if (target / 'CH01/comparison.json').exists():
    runner.preserve_attempt('CH01', current, 'before-analyze')
runner.state['cases']['CH01']['effective_request_limit'] = current['budget']['requests']
runner.analyze('CH01')
print(json.dumps({'status': current['status'], 'request_count': current['request_count'],
                  'comparison': str(target / 'CH01/comparison.json'), 'model_calls': 0}, ensure_ascii=False))
