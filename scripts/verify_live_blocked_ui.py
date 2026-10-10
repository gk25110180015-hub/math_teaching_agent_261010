"""Read-only Edge checks for an existing live BLOCKED budget case.

Never starts services, calls models, changes budgets, retries, or submits teacher
reviews. UI checks can PASS while workflow_status remains BLOCKED and full_delivery
is NOT_RUN. Run only after the intended workspace is already served and idle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import traceback
from urllib.parse import quote, urlparse
import uuid

from verify_live_delivery_ui import (
    CASES, REPORTS, edge_executable, record_check, require, run_snapshot,
    save_json, sha256, stamp, verify_sidebar_bounds,
)


def verify_case(browser, base_url, name, run_id, folder, timeout):
    folder.mkdir(parents=True, exist_ok=False)
    result = {'name': name, 'run_id': run_id, 'ui_checks': 'IN_PROGRESS',
              'workflow_status': 'UNKNOWN', 'full_delivery': 'NOT_RUN',
              'teacher_visual_review': 'NOT_RUN', 'model_calls': 'NOT_PERFORMED',
              'checks': [], 'partial_downloads': []}
    network, console, page_errors, forbidden = [], [], [], []
    context = browser.new_context(base_url=base_url, viewport={'width': 1440, 'height': 1100},
                                  locale='zh-CN', service_workers='block')
    page = context.new_page()

    def guard(route):
        request = route.request
        parsed = urlparse(request.url)
        if request.method != 'GET' or f'{parsed.scheme}://{parsed.netloc}' != base_url:
            forbidden.append({'method': request.method, 'url': request.url})
            route.abort('blockedbyclient')
        else:
            route.continue_()

    context.route('**/*', guard)
    page.on('console', lambda message: console.append({'type': message.type, 'text': message.text}))
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.on('response', lambda response: network.append({'source': 'browser', 'method': response.request.method,
                                                        'url': response.url, 'http_status': response.status}))
    page.on('requestfailed', lambda request: network.append({'source': 'browser', 'method': request.method,
                                                            'url': request.url, 'failure': request.failure}))

    def get(path, as_json=True, expected_sha=None):
        require(path.startswith('/api/') and not path.startswith('//') and not urlparse(path).netloc,
                'Only an explicit same-origin API GET is allowed')
        entry = {'source': 'APIRequestContext', 'method': 'GET', 'url': base_url + path}
        network.append(entry)
        response = None
        try:
            response = context.request.get(base_url + path, timeout=timeout, max_redirects=0)
            entry['http_status'] = response.status
            require(response.status == 200, f'GET {path}: HTTP {response.status}')
            if expected_sha is not None:
                entry['response_headers'] = {key: response.headers.get(key) for key in
                                             ('x-content-sha256', 'x-math-agent-status')}
                require(entry['response_headers']['x-content-sha256'] == expected_sha,
                        'Partial response hash header differs from checkpoint')
                require(entry['response_headers']['x-math-agent-status'] == 'PARTIAL',
                        'Partial response lost its PARTIAL marker')
            return response.json() if as_json else response.body()
        except Exception as error:
            entry['error'] = str(error)[:2000]
            raise
        finally:
            if response is not None:
                response.dispose()

    run_path = '/api/runs/' + quote(run_id, safe='')
    before = None
    try:
        get('/api/session')  # Session cookie only; its CSRF value is never saved or used.
        run = get(run_path)
        before = {'run': run_snapshot(run), 'budget': get(run_path + '/budget'),
                  'partials': get(run_path + '/partials')}
        result['workflow_status'] = run.get('status', 'UNKNOWN')
        save_json(folder / 'before.json', before)
        parts = run.get('partial_checkpoints', [])

        def identity():
            require(run['id'] == run_id, 'Wrong run returned')
            require(run.get('input', {}).get('provider') == 'live', 'Expected a real API run')
            require(run['status'] == 'BLOCKED', 'Case is no longer BLOCKED; do not treat completed delivery as blocked evidence')
            require((run.get('error') or {}).get('code') == 'BUDGET_EXHAUSTED', 'Expected actual BUDGET_EXHAUSTED failure')
            require(run.get('approval'), 'Expected the preserved approved plan')
            require(not any(str(job.get('status', '')).lower() in ('queued', 'running') for job in run.get('jobs', [])),
                    'Run has an active job; wait until it is idle')
            require(before['budget'] == {key: value for key, value in run['budget'].items() if key != 'can_increase'},
                    'Budget endpoint and run disagree')
            require(before['partials'] == parts, 'Partial endpoint and run disagree')
            return {'workflow_status': 'BLOCKED', 'error': run['error'], 'budget': run['budget'],
                    'full_delivery': 'NOT_RUN', 'partial_sections': len(parts)}

        # Do not browse or download from an unexpectedly active run.
        require(record_check(result, 'real_blocked_budget_case', identity) is not None,
                'Blocked identity precondition failed')

        def load_ui():
            response = page.goto(base_url, wait_until='domcontentloaded', timeout=timeout)
            require(response and response.status == 200, 'Application did not return HTTP 200')
            page.locator('#new-run-form').wait_for(timeout=timeout)
            page.evaluate('(id) => localStorage.setItem("math-agent-run", id)', run_id)
            page.reload(wait_until='domcontentloaded', timeout=timeout)
            status = page.locator('#main [data-testid="run-status"]')
            status.wait_for(timeout=timeout)
            require(status.get_attribute('data-status') == 'BLOCKED', 'BLOCKED status is missing')
            require(page.locator('#main .tag.live').inner_text() == '真实 API', 'Live badge is missing')
            require(page.locator('#main .tag.mock').count() == 0, 'Mock badge displayed')
            require(run_id in page.locator('#main .hash').first.inner_text(), 'Wrong run loaded')
            panel = page.locator('#main > .error-panel')
            require(panel.count() == 1, 'Missing run-level failure panel')
            require('BUDGET_EXHAUSTED' in panel.inner_text(), 'Budget failure code is missing')
            require(json.loads(panel.locator('p').inner_text()) == run['error'], 'Failure message differs from API')
            require(run.get('stage', '') in page.locator('#run-stage').inner_text(), 'Recovery stage is missing')
            summary = page.locator('#budget-summary').inner_text()
            budget = run['budget']
            for value in (f'已用 {budget["request_count"]} / 上限 {budget["requests"]}',
                          f'每个单元最多修复 {budget["local_repairs_per_unit"]} 次',
                          f'全文最多修复 {budget["global_repair_rounds"]} 轮'):
                require(value in summary, 'UI budget differs from preserved counters/limits')
            require(budget.get('can_increase') and page.locator('#budget-form').count() == 1,
                    'Explicit user budget controls are missing')
            require('保存不会自动执行' in page.locator('#budget-editor').inner_text(), 'Explicit-save behavior is not explained')
            should_disable = budget.get('baseline_unknown') or budget.get('version', 0) <= run['error'].get('budget_version', 0)
            require(page.locator('#retry-run').is_disabled() == bool(should_disable), 'Retry budget gate differs from current version')
            for key in ('requests', 'local_repairs_per_unit', 'global_repair_rounds'):
                require(page.locator('#budget-' + key).input_value() == '', 'Budget form has a prefilled increase')
            page.screenshot(path=str(folder / 'blocked-overview.png'), full_page=False, timeout=timeout)
            page.locator('#budget-panel').screenshot(path=str(folder / 'budget-panel.png'), timeout=timeout)
            return {'status': 'BLOCKED', 'badge': '真实 API', 'budget_summary': summary,
                    'retry_disabled': bool(should_disable), 'budget_form_untouched': True}

        loaded = record_check(result, 'blocked_ui_failure_and_explicit_budget_gate', load_ui)

        def partial_links():
            require(parts, 'Expected already compiled checkpoint partial results')
            panel = page.locator('#partial-checkpoints')
            require(panel.count() == 1 and '部分结果待复核' in panel.inner_text(), 'Partial disclaimer missing')
            require('全文仍未完成' in panel.inner_text(), 'Incomplete full-delivery disclaimer missing')
            # Expanding HTML details changes presentation only; never click a workflow control.
            panel.locator('details').evaluate_all('(items) => items.forEach(item => { item.open = true; })')
            links = panel.locator('a.partial-link').evaluate_all('(items) => items.map(a => ({id:a.dataset.partialId,href:a.getAttribute("href"),text:a.innerText}))')
            expected = [item for part in parts for item in part.get('downloads', [])]
            by_id = {item['id']: item for item in links}
            require(len(by_id) == len(links) == len(expected), 'Duplicate or missing partial links')
            require(set(by_id) == {item['id'] for item in expected}, 'Partial links differ from published checkpoint IDs')
            for part in parts:
                require(part['checkpoint_hash'] in panel.inner_text(), 'Checkpoint hash not displayed')
                require(part.get('plan_binding', 'UNKNOWN') in panel.inner_text(), 'Plan association label missing')
                require(part.get('plan_binding_notice', '') in panel.inner_text(), 'Plan association explanation missing')
            for item in expected:
                require(by_id[item['id']]['href'] == item['url'], 'Partial link target differs')
                require(item['sha256'] in by_id[item['id']]['text'] and 'PARTIAL' in by_id[item['id']]['text'],
                        'Partial link omits hash or PARTIAL label')
            panel.screenshot(path=str(folder / 'partial-checkpoints.png'), timeout=timeout)
            return {'checkpoints': len(parts), 'links': len(links), 'label': 'PARTIAL'}

        if loaded:
            record_check(result, 'real_long_titles_stay_within_sidebar', lambda: verify_sidebar_bounds(page, folder, timeout))
            record_check(result, 'partial_only_links_and_disclaimers', partial_links)

            def refreshed():
                require(page.evaluate('localStorage.getItem("math-agent-run")') == run_id, 'Selection not persisted')
                page.reload(wait_until='domcontentloaded', timeout=timeout)
                status = page.locator('#main [data-testid="run-status"]')
                status.wait_for(timeout=timeout)
                require(status.get_attribute('data-status') == 'BLOCKED', 'Reload changed workflow status')
                require(run_id in page.locator('#main .hash').first.inner_text(), 'Reload selected another run')
                require(page.locator('#main .tag.live').inner_text() == '真实 API', 'Reload lost live identity')
                require('BUDGET_EXHAUSTED' in page.locator('#main > .error-panel').inner_text(), 'Reload lost failure')
                page.screenshot(path=str(folder / 'after-refresh.png'), full_page=False, timeout=timeout)
                return {'run_id': run_id, 'workflow_status': 'BLOCKED'}

            record_check(result, 'refresh_restores_same_blocked_run', refreshed)

        for part in parts:
            for artifact in part.get('downloads', []):
                entry = dict(artifact, section_id=part['section_id'], checkpoint_hash=part['checkpoint_hash'],
                             plan_binding=part.get('plan_binding', 'UNKNOWN'), status='IN_PROGRESS')
                data = None
                try:
                    require(re.fullmatch(r'[a-f0-9]{64}', artifact['id']) is not None, 'Invalid partial token')
                    require(re.fullmatch(r'[a-f0-9]{64}', artifact['sha256']) is not None, 'Invalid published hash')
                    require(artifact['url'] == run_path + '/partials/' + artifact['id'], 'Partial belongs to another run')
                    data = get(artifact['url'], as_json=False, expected_sha=artifact['sha256'])
                    entry.update(http_status=200, actual_sha256=sha256(data), bytes=len(data))
                    require(entry['actual_sha256'] == artifact['sha256'], 'Downloaded partial hash differs from published checkpoint')
                    if artifact['kind'] == 'pdf':
                        require(data.startswith(b'%PDF-'), 'Invalid partial PDF signature')
                        suffix = '.pdf'
                    elif artifact['kind'] == 'source':
                        require('\\documentclass' in data.decode('utf-8-sig'), 'Partial TeX lacks documentclass')
                        suffix = '.tex'
                    else:
                        json.loads(data)
                        suffix = '.json'
                    filename = artifact['id'] + suffix
                    (folder / filename).write_bytes(data)
                    entry.update(status='PASS', saved_as=filename)
                except Exception as error:
                    entry.update(status='FAIL', error=str(error)[:4000], error_type=type(error).__name__)
                    if data is not None:
                        filename = 'failed-' + sha256(data) + '.bin'
                        (folder / filename).write_bytes(data)
                        entry['failure_body_saved_as'] = filename
                result['partial_downloads'].append(entry)
                save_json(folder / 'result.json', result)

        def required_files():
            kinds = {item['kind'] for item in result['partial_downloads'] if item['status'] == 'PASS'}
            require({'pdf', 'source', 'checkpoint'} <= kinds, 'Required partial PDF/TeX/checkpoint were not all verified')
            return {'kinds': sorted(kinds), 'full_delivery': 'NOT_RUN'}
        record_check(result, 'actual_partial_pdf_tex_checkpoint_hashes', required_files)
    except Exception as error:
        result['fatal_error'] = {'type': type(error).__name__, 'message': str(error)[:4000]}
        (folder / 'failure-traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if before is not None:
            def unchanged():
                after = {'run': run_snapshot(get(run_path)), 'budget': get(run_path + '/budget'),
                         'partials': get(run_path + '/partials')}
                save_json(folder / 'after.json', after)
                require(after == before, 'Budget, count, reviews, approval, failure, jobs or checkpoints changed')
                return {'unchanged': True, 'request_count': before['run']['request_count'],
                        'teacher_reviews': len(before['run'].get('reviews') or [])}
            record_check(result, 'budget_counts_approval_reviews_and_checkpoints_unchanged', unchanged)
        record_check(result, 'no_page_errors', lambda: require(not page_errors, str(page_errors)))
        record_check(result, 'all_network_requests_only_same_origin_get',
                     lambda: require(not forbidden and all(item['method'] == 'GET' for item in network), str(forbidden)))
        for filename, data in [('network.json', network), ('console.json', console),
                               ('page-errors.json', page_errors), ('forbidden-requests.json', forbidden)]:
            save_json(folder / filename, data)
        result['ui_checks'] = 'FAIL' if result.get('fatal_error') or any(
            item['status'] == 'FAIL' for item in result['checks'] + result['partial_downloads']) else 'PASS'
        if result['ui_checks'] == 'FAIL':
            try:
                page.screenshot(path=str(folder / 'failure.png'), full_page=False, timeout=timeout)
            except Exception as error:
                result['failure_screenshot_error'] = str(error)[:2000]
        save_json(folder / 'result.json', result)
        context.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--state', type=Path, default=REPORTS / 'live-lectures' / 'benchmark_state.json')
    parser.add_argument('--output', type=Path, help='New child of reports/iteration2; must not exist')
    parser.add_argument('--case', dest='cases', action='append', choices=CASES,
                        help='Blocked case to inspect; repeat if needed; default CH03')
    parser.add_argument('--timeout-ms', type=int, default=30000)
    args = parser.parse_args(argv)
    args.cases = args.cases or ['CH03']
    base_url = args.base_url.rstrip('/')
    parsed = urlparse(base_url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        parser.error('--base-url must be an HTTP localhost origin without credentials, query, or path')
    if not 1000 <= args.timeout_ms <= 120000 or len(args.cases) != len(set(args.cases)):
        parser.error('Timeout must be 1000..120000 ms and cases must be unique')
    output = (args.output or REPORTS / ('live-blocked-ui-' + stamp() + '-' + uuid.uuid4().hex[:6])).resolve()
    if not output.is_relative_to(REPORTS.resolve()) or output == REPORTS.resolve():
        parser.error('--output must be a new child directory of reports/iteration2')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'ui_checks': 'IN_PROGRESS', 'full_delivery': 'NOT_RUN',
              'teacher_visual_review': 'NOT_RUN', 'model_calls': 'NOT_PERFORMED',
              'service_start_stop': 'NOT_PERFORMED', 'base_url': base_url,
              'started_at': datetime.now(timezone.utc).isoformat(), 'cases': []}
    save_json(output / 'report.json', report)
    try:
        raw = args.state.read_bytes()
        state = json.loads(raw)
        report.update(state_path=str(args.state.resolve()), state_sha256=sha256(raw),
                      workspace_from_state=state.get('workspace'), browser_executable=edge_executable())
        require(report['browser_executable'], 'Microsoft Edge executable not found')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, executable_path=report['browser_executable'],
                env={key: value for key, value in os.environ.items() if key not in ('MATH_AGENT_API_KEY', 'OPENAI_API_KEY')})
            try:
                for name in args.cases:
                    run_id = state.get('cases', {}).get(name, {}).get('run_id')
                    require(isinstance(run_id, str) and re.fullmatch(r'[a-f0-9]{32}', run_id), 'Missing or invalid state run ID')
                    report['cases'].append(verify_case(browser, base_url, name, run_id, output / name, args.timeout_ms))
                    save_json(output / 'report.json', report)
            finally:
                browser.close()
        report['ui_checks'] = 'PASS' if report['cases'] and all(case['ui_checks'] == 'PASS' for case in report['cases']) else 'FAIL'
    except Exception as error:
        report.update(ui_checks='FAIL', fatal_error={'type': type(error).__name__, 'message': str(error)[:4000]})
        (output / 'failure-traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save_json(output / 'report.json', report)
        lines = ['# Read-only BLOCKED workflow UI verification', '',
                 f'UI checks: **{report["ui_checks"]}**. Full delivery: **NOT_RUN**. Teacher acceptance: **NOT_RUN**.', '',
                 'Only existing real-provider runs were read. No model calls, budget updates, retries, plan confirmations, teacher reviews, service starts or service stops were performed.', '',
                 '| Case | Workflow status | UI checks | Partial GET/hash checks | Full delivery |',
                 '| --- | --- | --- | --- | --- |']
        for case in report['cases']:
            downloads = case['partial_downloads']
            lines.append(f'| {case["name"]} | {case["workflow_status"]} | {case["ui_checks"]} | {sum(item["status"] == "PASS" for item in downloads)}/{len(downloads)} | NOT_RUN |')
        lines += ['', 'Passing UI checks confirm visibility and retrieval of partial results, not completion or acceptance of the blocked chapter. Failures, partial evidence, unchanged-state snapshots and every browser/API GET remain in the case folder.', '', '[Detailed report](report.json)']
        (output / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'ui_checks': report['ui_checks'], 'full_delivery': 'NOT_RUN', 'output': str(output)}, ensure_ascii=False))
    return 0 if report['ui_checks'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
