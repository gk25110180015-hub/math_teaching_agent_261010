"""Submit one explicit scoped repair proposal through the deployed local API."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
from pathlib import Path
import sqlite3
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent
RUN_ID = 'a45be503af594ce8aae0bb1e4c30184b'
BASE = 'http://127.0.0.1:8766'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6]
    folder = REPORTS / ('guidance-CH03-' + stamp)
    folder.mkdir(exist_ok=False)
    def save(name, data):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    token = None
    def call(path, data=None):
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers.update({'X-CSRF-Token': token, 'Origin': BASE, 'Content-Type': 'application/json'})
        request = urllib.request.Request(BASE + path, headers=headers,
            data=None if data is None else json.dumps(data).encode('utf-8'))
        with client.open(request, timeout=30) as response:
            return json.load(response)
    summary = {'created_at': stamp, 'mode': 'SUBMIT' if args.submit else 'READ_ONLY',
        'teacher_review': 'NOT_RUN', 'status': 'PREPARING'}
    try:
        token = call('/api/session')['csrf_token']
        before = call('/api/runs/' + RUN_ID); save('before.json', before)
        assert before['status'] in ('FAILED', 'BLOCKED')
        assert before['input']['provider'] == 'live' and before['approval']['hash'] == before['plan']['hash']
        assert not any(job['status'] in ('queued', 'running') for job in before['jobs'])
        context = before['repair_guidance_context']
        assert context['section_id'] == 'S03' and 'S03.U04' in [u['id'] for u in context['units']]
        instructions = (REPORTS / 'CH03-S03-U04-repair-guidance.txt').read_text(encoding='utf-8')
        body = {'expected_plan_revision': before['plan']['revision'], 'expected_plan_hash': before['plan']['hash'],
            'action_id': 'authorized-CH03-U04-' + stamp, 'section_id': 'S03',
            'expected_candidate_hash': context['candidate_hash'], 'unit_ids': ['S03.U04'],
            'instructions': instructions, 'source': 'agent_audit'}
        save('request.json', body)
        summary.update(candidate_hash=context['candidate_hash'], request_count_before=before['request_count'],
            instructions_sha256=hashlib.sha256(instructions.encode('utf-8')).hexdigest())
        if args.submit:
            database = ROOT / 'workspace/iteration2-live/agent.db'
            with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(folder / 'before-agent.db') as backup:
                    source.backup(backup)
            result = call('/api/runs/' + RUN_ID + '/repair-guidance', body)
            save('response.json', result)
            after = call('/api/runs/' + RUN_ID); save('after.json', after)
            original_job = next(job for job in reversed(before['jobs']) if job['kind'] == 'build' and job['status'] == 'failed')
            assert result['id'] == original_job['id'], 'Guidance must use original failed build job'
            assert after['approval'] == before['approval'] and after['plan'] == before['plan']
            assert after['request_count'] >= before['request_count'] and after['reviews'] == before['reviews']
            summary.update(status='SUBMITTED', job_id=result['id'], original_approval_preserved=True)
        else:
            summary['status'] = 'PREPARED_NOT_SUBMITTED'
    except BaseException as error:
        summary.update(status='FAILED', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        save('summary.json', summary)
        print(json.dumps({'folder': str(folder), **summary}, ensure_ascii=True))


if __name__ == '__main__':
    main()
