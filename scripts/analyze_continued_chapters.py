"""Measure existing CH02/CH03 artifacts; never enqueue work or call a model."""
import argparse
import copy
import json
from pathlib import Path
import shutil

from math_agent.benchmark import BenchmarkRunner
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import digest, now, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', choices=['CH02', 'CH03'])
    args = parser.parse_args()
    names = args.case or ['CH02', 'CH03']
    original = PROJECT_ROOT / 'reports/iteration2/live-lectures'
    target = PROJECT_ROOT / 'reports/iteration4/live-lectures'
    historical = json.loads((original / 'benchmark_state.json').read_bytes())
    state_path = target / 'benchmark_state.json'
    if not state_path.exists():
        # New analysis manifest, linked to the old evidence rather than rewriting it.
        state = {'schema_version': 1, 'created_at': now(), 'workspace': historical['workspace'],
            'actor': 'benchmark_driver', 'teacher_visual_review': 'NOT_RUN',
            'per_run_budget': 240, 'total_budget': 480,
            'execution_mode': 'ANALYZE_ONLY; actual execution uses local HTTP and its independent Worker',
            'historical_manifest': str(original / 'benchmark_state.json'),
            'historical_manifest_sha256': digest((original / 'benchmark_state.json').read_bytes()),
            'cases': {name: {key: copy.deepcopy(historical['cases'][name][key])
                for key in ('run_id', 'started_epoch', 'dataset', 'topic', 'teacher_visual_review')}
                for name in ('CH02', 'CH03')}}
        write_json(state_path, state)
        for name in ('CH02', 'CH03'):
            source = original / 'references' / name / 'metrics.json'
            if source.is_file():
                destination = target / 'references' / name / 'metrics.json'
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    settings = Settings(workspace=Path(historical['workspace']), api_key='', deepseek_api_key='',
                        live_api_enabled=False, max_requests_per_run=240)
    runner = BenchmarkRunner(settings, target, per_run_budget=240, total_budget=480)
    result = {'created_at': now(), 'model_requests_this_invocation': 0,
              'teacher_visual_review': 'NOT_RUN', 'cases': []}
    for name in names:
        current = runner.service.get(runner.state['cases'][name]['run_id'])
        before = current['request_count']
        if (target / name / 'comparison.json').exists():
            runner.preserve_attempt(name, current, 'before-analyze')
        runner.state['cases'][name]['effective_request_limit'] = current['budget']['requests']
        runner.analyze(name)
        measured = json.loads((target / name / 'comparison.json').read_bytes())
        result['cases'].append({'case': name, 'run_status': measured['run_status'],
            'requests_observed_before': before, 'report': str(target / name / 'comparison.json')})
    write_json(target / 'analysis-invocation.json', result)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
