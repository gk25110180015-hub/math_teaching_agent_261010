"""Three bounded real API text probes, in the user's preferred order.

No key argument or file is accepted. Run with --execute-live after importing
Windows User environment variables. Each model is checked without fallback or
network/schema retries; a failing model cannot borrow another model's success.
"""
import argparse
import json
from pathlib import Path
from uuid import uuid4

from math_agent.cli import provider_capability_check
from math_agent.model_routing import MODEL_IDS
from math_agent.settings import PROJECT_ROOT, Settings
from math_agent.util import now, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = (args.output_dir or PROJECT_ROOT / 'reports' / 'iteration3' /
              ('model-probes-' + uuid4().hex[:12])).resolve()
    if not output.is_relative_to((PROJECT_ROOT / 'reports' / 'iteration3').resolve()):
        parser.error('Output must stay below reports/iteration3.')
    if output.exists():
        parser.error('Output directory already exists; choose a new path to retain earlier evidence.')
    output.mkdir(parents=True)
    summary = {'timestamp': now(), 'test_kind': 'REAL_API_TEXT_PROBES',
               'order': list(MODEL_IDS), 'fallback_enabled': False,
               'max_network_retries': 0, 'max_schema_repair_attempts': 0,
               'max_http_requests': len(MODEL_IDS), 'results': [],
               'windows_compile': 'NOT_RUN', 'human_visual_review': 'NOT_RUN',
               'teacher_math_review': 'NOT_RUN', 'price': None}
    if not args.execute_live:
        summary.update({'status': 'NOT_RUN', 'reason': '--execute-live was not supplied'})
        write_json(output / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    settings = Settings(max_network_retries=0, max_schema_repair_attempts=0)
    for model_id in MODEL_IDS:
        print('Checking ' + model_id + ' (no fallback, no retries)...', flush=True)
        evidence, code = provider_capability_check(settings, model_id, False)
        write_json(output / (model_id + '.json'), evidence)
        summary['results'].append({'model_id': model_id, 'status': evidence['status'],
                                   'actual_model_id': evidence['actual_model_id'],
                                   'request_count': evidence['request_count'],
                                   'exit_code': code, 'report': evidence['report']})
        summary['status'] = 'RUNNING'
        write_json(output / 'summary.json', summary)
    summary['status'] = 'PASS' if all(r['exit_code'] == 0 for r in summary['results']) else 'PARTIAL'
    summary['request_count'] = sum(r['request_count'] for r in summary['results'])
    write_json(output / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
