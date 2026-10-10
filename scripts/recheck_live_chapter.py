"""Submit saved agent observations through the approved run's formal recheck API.

Does not approve a plan, sign a human review, change budgets, or invoke models
directly. The ordinary application worker handles the queued recheck.
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
BASE = 'http://127.0.0.1:8766'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=RUNS)
    parser.add_argument('--feedback-file', required=True, type=Path)
    parser.add_argument('--submit', action='store_true', help='Otherwise preserve a read-only preview')
    args = parser.parse_args()
    feedback = args.feedback_file.read_text(encoding='utf-8').strip()
    if not feedback or len(feedback) > 10000:
        parser.error('Feedback must contain 1 to 10000 characters')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
    report = ROOT / 'reports/iteration4' / ('feedback-' + args.case + '-' + stamp)
    report.mkdir(parents=True, exist_ok=False)
    (report / 'feedback.txt').write_text(feedback, encoding='utf-8')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf = None

    def request(path, payload=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': BASE, 'X-CSRF-Token': csrf})
        req = urllib.request.Request(BASE + path, headers=headers,
            data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        try:
            with opener.open(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Local HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")}') from None

    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'case': args.case,
        'run_id': RUNS[args.case], 'mode': 'submit' if args.submit else 'preview',
        'feedback_source': 'agent_audit', 'feedback_file': str(args.feedback_file.resolve()),
        'feedback_sha256': hashlib.sha256(feedback.encode('utf-8')).hexdigest(),
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}
    try:
        csrf = request('/api/session')['csrf_token']
        path = '/api/runs/' + RUNS[args.case]
        before = request(path)
        save(report / 'before.json', before)
        assert before['input']['provider'] == 'live'
        assert before['status'] == 'AWAITING_USER_REVIEW', before['status']
        assert not any(job['status'] in ('running', 'queued') for job in before['jobs'])
        assert before['approval']['hash'] == before['plan']['hash']
        payload = {'expected_plan_revision': before['active_plan_revision'],
            'expected_plan_hash': before['plan']['hash'],
            'idempotency_key': 'iteration4-feedback-' + args.case + '-' + stamp,
            'feedback': feedback, 'feedback_source': 'agent_audit'}
        save(report / 'request.json', payload)
        if args.submit:
            db = ROOT / 'workspace/iteration2-live/agent.db'
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(report / 'before-agent.db') as backup:
                    source.backup(backup)
            result = request(path + '/recheck', payload)
            save(report / 'response.json', result)
            after = request(path)
            save(report / 'after.json', after)
            for key in ('input', 'approval', 'plan', 'reviews'):
                assert before[key] == after[key], key + ' unexpectedly changed'
            # Queueing changes can_increase; an independent worker may already
            # have charged a new request. Neither is a budget authorization.
            stable_budget = ('requests', 'local_repairs_per_unit', 'global_repair_rounds',
                'version', 'initialized', 'initialized_fields', 'source', 'baseline_unknown',
                'defaults', 'overrides', 'maximums', 'limitations')
            assert {k: before['budget'].get(k) for k in stable_budget} == {
                k: after['budget'].get(k) for k in stable_budget}, 'budget authorization changed'
            assert after['budget']['request_count'] >= before['budget']['request_count']
            assert after['request_count'] >= before['request_count']
            summary.update(status='QUEUED', response=result, request_count_before=before['request_count'],
                request_count_after=after['request_count'], approval_unchanged=True, teacher_reviews_unchanged=True)
        else:
            summary.update(status='PREVIEW_ONLY', request_count_before=before['request_count'])
    except BaseException as exc:
        summary.update(status='FAILED', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save(report / 'summary.json', summary)
        print(json.dumps({'report': str(report), **summary}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
