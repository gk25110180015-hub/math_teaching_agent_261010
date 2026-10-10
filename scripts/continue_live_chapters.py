"""Resume user-authorized CH02/CH03 runs through the deployed local HTTP API.

Never creates or approves a plan, changes a historical counter, or signs a review.
The ordinary worker owns model calls. Each invocation preserves a new snapshot.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNS = {'CH02': 'fd6736af6ef14be3839e019e86ca1e5c',
        'CH03': 'a45be503af594ce8aae0bb1e4c30184b'}
WORKSPACE = ROOT / 'workspace/iteration2-live'
BASE = 'http://127.0.0.1:8766'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['CH02', 'CH03', 'both'], default='both')
    parser.add_argument('--increase-and-resume', action='store_true')
    parser.add_argument('--retry', action='store_true', help='Retry only after the recorded failure condition was addressed')
    parser.add_argument('--requests', type=int, default=240)
    parser.add_argument('--local-repairs', type=int, default=6)
    parser.add_argument('--global-rounds', type=int, default=6)
    parser.add_argument('--note', default='用户明确授权提高第二、三章修复及请求上限，以完善工作流和制作质量为优先；由Codex代为执行本次已授权预算动作。')
    args = parser.parse_args()
    if args.increase_and_resume and args.retry:
        parser.error('Choose one mutation mode')
    if not 1 <= args.requests <= 1000 or not 1 <= args.local_repairs <= 20 or not 1 <= args.global_rounds <= 20:
        parser.error('Limits must fit the application budget contract')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
    report = ROOT / 'reports/iteration4' / ('resume-' + stamp)
    report.mkdir(parents=True, exist_ok=False)
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf = None

    def request(path, payload=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers.update({'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': BASE})
        req = urllib.request.Request(BASE + path, data=None if payload is None else json.dumps(payload).encode('utf-8'), headers=headers)
        try:
            with client.open(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read())
            raise RuntimeError(f'Local HTTP {exc.code}: {json.dumps(body, ensure_ascii=True)}') from None

    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'base_url': BASE,
               'mode': 'increase_and_resume' if args.increase_and_resume else 'retry' if args.retry else 'snapshot_only',
               'authorization': args.note, 'cases': {}, 'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}
    try:
        csrf = request('/api/session')['csrf_token']
        summary['health'] = request('/api/health')
        names = list(RUNS) if args.case == 'both' else [args.case]
        before = {name: request('/api/runs/' + RUNS[name]) for name in names}
        for name, run in before.items():
            save(report / name / 'before.json', run)
            if args.increase_and_resume or args.retry:
                assert run['input']['provider'] == 'live'
                assert run['status'] in ('BLOCKED', 'FAILED')
                assert not any(job['status'] in ('queued', 'running') for job in run['jobs'])
                assert run['approval']['hash'] == run['plan']['hash']
        if args.increase_and_resume or args.retry:
            with sqlite3.connect((WORKSPACE / 'agent.db').as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(report / 'before-agent.db') as backup:
                    source.backup(backup)
            summary['consistent_database_backup'] = 'before-agent.db'
        # Increase every requested run before enqueueing any worker job.
        if args.increase_and_resume:
            for name, run in before.items():
                requested = {'requests': args.requests, 'local_repairs_per_unit': args.local_repairs,
                             'global_repair_rounds': args.global_rounds}
                updates = {key: value for key, value in requested.items() if value > run['budget'][key]}
                assert updates, 'No strictly larger budget was selected'
                payload = {**updates, 'expected_version': run['budget']['version'],
                    'expected_plan_revision': run['active_plan_revision'], 'expected_plan_hash': run['plan']['hash'],
                    'action_id': 'authorized-iteration4-' + name + '-' + stamp, 'note': args.note}
                save(report / name / 'budget-request.json', payload)
                updated = request('/api/runs/' + RUNS[name] + '/budget', payload)
                save(report / name / 'budget-response.json', updated)
                current = request('/api/runs/' + RUNS[name])
                assert current['request_count'] == run['request_count']
                for key in ('input', 'approval', 'plan'):
                    assert fingerprint(current[key]) == fingerprint(run[key]), key + ' changed during budget update'
        for name, run in before.items():
            if args.increase_and_resume or args.retry:
                result = request('/api/runs/' + RUNS[name] + '/retry', {})
                save(report / name / 'retry-response.json', result)
            current = request('/api/runs/' + RUNS[name])
            save(report / name / 'after.json', current)
            events = []
            after = 0
            while True:
                batch = request('/api/runs/' + RUNS[name] + '/events?after=' + str(after))
                if not batch:
                    break
                events.extend(batch)
                after = batch[-1]['sequence']
                if len(batch) < 500:
                    break
            save(report / name / 'events.json', events)
            from math_agent.benchmark import request_metrics
            metrics = request_metrics(events, current['request_count'], current['budget']['requests'])
            save(report / name / 'request-metrics.json', metrics)
            summary['cases'][name] = {'run_id': RUNS[name], 'status': current['status'], 'stage': current['stage'],
                'request_count': current['request_count'], 'budget': current['budget'], 'error': current.get('error'),
                'preferred_model': current.get('input', {}).get('model_id', 'gpt6'),
                'model_routing': current.get('model_routing'), 'approval_unchanged': fingerprint(current['approval']) == fingerprint(run['approval'])}
        summary['status'] = 'RECORDED'
    except BaseException as exc:
        summary['status'] = 'FAILED'
        summary['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        save(report / 'summary.json', summary)
        print(json.dumps({'report': str(report), **summary}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
