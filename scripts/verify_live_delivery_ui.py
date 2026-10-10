"""Read-only Edge verification of existing live runs; never starts services or models.

Only call this after the benchmark driver has finished and the intended workspace
is already served. This is automated UI/delivery evidence, not teacher acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import traceback
from urllib.parse import quote, urlparse
import uuid
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / 'reports' / 'iteration2'
ALL_REPORTS = PROJECT / 'reports'
CASES = ('smoke', 'CH01', 'CH02', 'CH03')
READY = {'AWAITING_USER_REVIEW', 'COMPLETED', 'COMPLETED_WITH_WARNINGS'}


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + uuid.uuid4().hex[:12] + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def edge_executable():
    # Explicit override is accepted only if it names Edge, not another browser.
    candidates = [os.environ.get('MATH_AGENT_BROWSER_PATH'),
                  r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                  r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
    return next((str(Path(path).resolve()) for path in candidates
                 if path and Path(path).name.lower() == 'msedge.exe' and Path(path).is_file()), None)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_snapshot(run):
    return {key: run.get(key) for key in ('id', 'status', 'stage', 'request_count', 'approval', 'reviews',
                                        'budget', 'error', 'jobs', 'active_plan_revision', 'partial_checkpoints')} | {
        'provider': run.get('input', {}).get('provider'),
        'plan_hash': (run.get('plan') or {}).get('hash'),
        'artifacts': run.get('artifacts', []),
    }


def record_check(case, name, action):
    """Preserve a failed check and continue independent checks for partial evidence."""
    try:
        value = action()
        case['checks'].append({'name': name, 'status': 'PASS', 'value': value})
        return value
    except Exception as error:
        case['checks'].append({'name': name, 'status': 'FAIL', 'error': str(error)[:4000],
                               'error_type': type(error).__name__})
        return None


def get_json(context, base_url, path, timeout, network=None):
    response = context.request.get(base_url + path, timeout=timeout, max_redirects=0)
    try:
        if network is not None:
            network.append({'source': 'APIRequestContext', 'method': 'GET', 'url': base_url + path,
                            'status': response.status})
        require(response.status == 200, f'GET {path}: HTTP {response.status}')
        return response.json()
    finally:
        response.dispose()


def capture_preview(page, artifact, folder, filename, timeout):
    target = page.locator(f'.page-review[data-page-id="{artifact["artifact_id"]}"]')
    require(target.count() == 1, 'Each published physical page needs one UI preview')
    # Native details expansion and scrolling change only local presentation.
    target.evaluate('(element) => { element.open = true; }')
    image = target.locator('img')
    image.scroll_into_view_if_needed(timeout=timeout)
    image.evaluate('(image) => { image.loading = "eager"; }')
    page.wait_for_function('(id) => { const image = document.querySelector(`.page-review[data-page-id="${id}"] img`); return image && image.complete && image.naturalWidth > 0 && image.naturalHeight > 0; }',
                           arg=artifact['artifact_id'], timeout=timeout)
    target.screenshot(path=str(folder / filename), timeout=timeout)
    return {'screenshot': filename, 'artifact_id': artifact['artifact_id'],
            'natural_size': image.evaluate('(image) => [image.naturalWidth, image.naturalHeight]')}


def verify_sidebar_bounds(page, folder, timeout):
    """Measure real long task titles; CSS clipping must stay inside the sidebar."""
    page.locator('#run-list .run-link').first.wait_for(timeout=timeout)
    measured = page.evaluate('''() => {
        const box = element => { const r = element.getBoundingClientRect();
            return {left:r.left,right:r.right,width:r.width}; };
        const aside = document.querySelector('aside'), list = document.querySelector('#run-list');
        return {aside:box(aside),list:box(list),main:box(document.querySelector('#main')),
            list_client_width:list.clientWidth,list_scroll_width:list.scrollWidth,
            buttons:[...list.querySelectorAll('.run-link')].map(button => {
                const title = button.querySelector('strong'), style = getComputedStyle(title);
                return {button:box(button),title:box(title),text:title.textContent,
                    title_client_width:title.clientWidth,title_scroll_width:title.scrollWidth,
                    overflow:style.overflow,text_overflow:style.textOverflow,white_space:style.whiteSpace};
            })};
    }''')
    save_json(folder / 'sidebar-bounds.json', measured)
    require(measured['buttons'], 'No real task buttons measured')
    require(measured['list_scroll_width'] <= measured['list_client_width'] + 1,
            'Task list content overflows its horizontal bounds')
    require(any(item['title_scroll_width'] > item['title_client_width'] + 1 for item in measured['buttons']),
            'No actual long title exercised ellipsis constraints')
    for item in measured['buttons']:
        require(item['button']['left'] >= measured['aside']['left'] - 1 and
                item['button']['right'] <= measured['aside']['right'] + 1 and
                item['button']['right'] <= measured['main']['left'] + 1,
                'Task button escapes sidebar or overlaps main content')
        require(item['title']['left'] >= item['button']['left'] - 1 and
                item['title']['right'] <= item['button']['right'] + 1,
                'Title element escapes its task button')
        require(item['overflow'] == 'hidden' and item['text_overflow'] == 'ellipsis' and item['white_space'] == 'nowrap',
                'Long title does not use bounded ellipsis presentation')
    page.locator('#run-list').screenshot(path=str(folder / 'sidebar.png'), timeout=timeout)
    page.screenshot(path=str(folder / 'sidebar-overview.png'), full_page=False, timeout=timeout)
    return measured


def match_expected_delivery(run, artifacts, expected):
    """Pin UI evidence to the exact ZIP/PDF previously clean-compiled locally."""
    require(expected.get('run_id') == run['id'], 'Expected delivery refers to another run')
    selected = {item['name']: item for item in artifacts}
    for name, hash_key, id_key in [('source_bundle.zip', 'zip_sha256', 'bundle_artifact_id'),
                                    ('lecture.pdf', 'original_pdf_sha256', 'pdf_artifact_id')]:
        artifact = selected.get(name)
        require(artifact is not None, 'Current delivery lacks ' + name)
        require(expected.get(hash_key) == artifact['sha256'], 'Current ' + name + ' differs from clean-recompile input SHA256')
        if expected.get(id_key):
            require(expected[id_key] == artifact['artifact_id'], 'Current ' + name + ' has another artifact identity')
    return {'run_id': run['id'], 'zip_sha256': expected['zip_sha256'],
            'original_pdf_sha256': expected['original_pdf_sha256'],
            'clean_recompile_status': expected.get('status', 'UNRECORDED')}


def verify_case(browser, base_url, name, run_id, folder, timeout, expected_delivery=None):
    folder.mkdir(parents=True, exist_ok=False)
    case = {'name': name, 'run_id': run_id, 'status': 'IN_PROGRESS', 'checks': [],
            'artifacts': [], 'teacher_visual_review': 'NOT_RUN', 'model_calls': 'NOT_PERFORMED'}
    network, console, page_errors, blocked = [], [], [], []
    context = browser.new_context(base_url=base_url, viewport={'width': 1440, 'height': 1100},
                                  locale='zh-CN', service_workers='block')
    page = context.new_page()

    def guard(route):
        request = route.request
        parsed = urlparse(request.url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if request.method != 'GET' or origin != base_url:
            blocked.append({'method': request.method, 'url': request.url})
            route.abort('blockedbyclient')
        else:
            route.continue_()

    context.route('**/*', guard)
    page.on('console', lambda message: console.append({'type': message.type, 'text': message.text}))
    page.on('pageerror', lambda error: page_errors.append(str(error)))
    page.on('response', lambda response: network.append({'method': response.request.method,
                                                        'url': response.url, 'status': response.status}))
    page.on('requestfailed', lambda request: network.append({'method': request.method, 'url': request.url,
                                                            'failure': request.failure}))
    before = None
    try:
        # This GET sets the existing application's local session cookie; its CSRF
        # value is neither saved nor used to make any state-changing request.
        get_json(context, base_url, '/api/session', timeout, network)
        run = get_json(context, base_url, '/api/runs/' + quote(run_id, safe=''), timeout, network)
        before = run_snapshot(run)
        case['before'] = before
        save_json(folder / 'run-before.json', before)
        all_artifacts = run.get('artifacts', [])
        artifacts = [item for item in all_artifacts if item.get('status') != 'superseded']
        historical = [item for item in all_artifacts if item.get('status') == 'superseded']
        case.update(current_artifact_count=len(artifacts), historical_artifact_count=len(historical))
        pages = [item for item in artifacts if item['media_type'] == 'image/png'
                 and item.get('metadata', {}).get('physical_page')]
        pdfs = [item for item in artifacts if item['media_type'] == 'application/pdf']
        zips = [item for item in artifacts if item['media_type'] == 'application/zip'
                or item.get('name', '').endswith('.zip')]

        def live_identity():
            require(run['id'] == run_id, 'API returned a different run')
            require(run.get('input', {}).get('provider') == 'live', 'This is not a real API run')
            require(run['status'] in READY, f'Run is not ready for delivery: {run["status"]}')
            require(artifacts and pages and pdfs and zips, 'Expected PDF, source ZIP and physical-page PNG artifacts')
            require(len({item['artifact_id'] for item in artifacts}) == len(artifacts), 'Duplicate artifact IDs')
            return {'provider': 'live', 'status': run['status'], 'artifacts': len(artifacts),
                    'physical_pages': len(pages), 'pdfs': len(pdfs), 'zips': len(zips)}

        record_check(case, 'published_live_run_and_complete_delivery', live_identity)
        if expected_delivery is not None:
            record_check(case, 'same_delivery_as_clean_source_recompile',
                         lambda: match_expected_delivery(run, artifacts, expected_delivery))

        def load_ui():
            response = page.goto(base_url, wait_until='domcontentloaded', timeout=timeout)
            require(response and response.status == 200, 'Application HTML did not load with HTTP 200')
            page.locator('#new-run-form').wait_for(timeout=timeout)
            page.evaluate('(runId) => localStorage.setItem("math-agent-run", runId)', run_id)
            page.reload(wait_until='domcontentloaded', timeout=timeout)
            status = page.locator('#main [data-testid="run-status"]')
            status.wait_for(timeout=timeout)
            require(status.get_attribute('data-status') == run['status'], 'UI status differs from published run')
            require(page.locator('#main .tag.live').inner_text() == '真实 API', 'Real API badge is missing')
            require(run_id in page.locator('#main .hash').first.inner_text(), 'UI loaded another run')
            require(page.locator('#main .tag.mock').count() == 0, 'Mock badge shown for real run')
            page.screenshot(path=str(folder / 'overview.png'), full_page=False, timeout=timeout)
            return {'status': status.get_attribute('data-status'), 'badge': '真实 API', 'screenshot': 'overview.png'}

        loaded = record_check(case, 'real_ui_identity_and_status', load_ui)

        if loaded:
            record_check(case, 'real_long_titles_stay_within_sidebar', lambda: verify_sidebar_bounds(page, folder, timeout))
            def links_and_pages():
                links = page.locator('a.artifact-link[data-artifact-id]').evaluate_all('(elements) => elements.map(e => ({id:e.dataset.artifactId, href:e.getAttribute("href"), text:e.innerText}))')
                expected = [item for item in artifacts if item['media_type'] != 'image/png']
                by_id = {item['id']: item for item in links}
                require(set(by_id) == {item['artifact_id'] for item in expected}, 'UI download links do not cover all non-PNG artifacts')
                for item in expected:
                    link = by_id[item['artifact_id']]
                    require(link['href'] == '/api/artifacts/' + quote(item['artifact_id'], safe=''), 'Unexpected artifact link target')
                    require(item['sha256'] in link['text'], 'UI download link omits the published SHA256')
                require(page.locator('.page-review').count() == len(pages), 'UI physical-page count differs from published artifacts')
                for item in pages:
                    preview = page.locator(f'.page-review[data-page-id="{item["artifact_id"]}"]')
                    require(preview.count() == 1, 'Missing physical-page preview')
                    require(preview.locator('img').get_attribute('src') == '/api/artifacts/' + quote(item['artifact_id'], safe=''), 'Preview points to another artifact')
                    preview.evaluate('(element) => { element.open = true; }')
                    require(item['sha256'] in preview.locator('.hash').inner_text(), 'Preview omits page hash')
                require(page.locator('iframe.pdf-preview').count() == 1, 'PDF preview iframe missing')
                require(page.locator('iframe.pdf-preview').get_attribute('src') == '/api/artifacts/' + quote(pdfs[-1]['artifact_id'], safe=''), 'PDF preview is not the latest published PDF')
                history_links = page.locator('#artifact-history a[data-historical-artifact-id]').evaluate_all('(elements) => elements.map(e => ({id:e.dataset.historicalArtifactId, href:e.getAttribute("href"), text:e.textContent}))')
                history_by_id = {item['id']: item for item in history_links}
                require(set(history_by_id) == {item['artifact_id'] for item in historical}, 'History links do not match superseded artifacts')
                for item in historical:
                    link = history_by_id[item['artifact_id']]
                    require(link['href'] == '/api/artifacts/' + quote(item['artifact_id'], safe=''), 'Unexpected history download target')
                    require(item['sha256'] in link['text'], 'History link omits its saved SHA256')
                    require(page.locator(f'.page-review[data-page-id="{item["artifact_id"]}"]').count() == 0, 'Historical page is incorrectly offered for current review')
                return {'download_links': len(links), 'physical_page_previews': len(pages), 'history_links': len(history_links)}

            record_check(case, 'all_download_links_and_page_previews', links_and_pages)

            def refresh_preserves_selection():
                # No init script or storage rewrite runs on reload: persistence
                # comes from the application's actual localStorage restore path.
                require(page.evaluate('localStorage.getItem("math-agent-run")') == run_id, 'Selection was not saved')
                page.reload(wait_until='domcontentloaded', timeout=timeout)
                status = page.locator('#main [data-testid="run-status"]')
                status.wait_for(timeout=timeout)
                require(status.get_attribute('data-status') == run['status'], 'Reload changed the visible status')
                require(run_id in page.locator('#main .hash').first.inner_text(), 'Reload changed the selected run')
                require(page.locator('#main .tag.live').inner_text() == '真实 API', 'Reload lost live badge')
                page.screenshot(path=str(folder / 'after-refresh.png'), full_page=False, timeout=timeout)
                return {'run_id': run_id, 'status': run['status'], 'screenshot': 'after-refresh.png'}

            record_check(case, 'refresh_restores_same_real_run', refresh_preserves_selection)
            if pages:
                record_check(case, 'first_page_image_loaded', lambda: capture_preview(page, pages[0], folder, 'first-page.png', timeout))
                if len(pages) > 1:
                    record_check(case, 'last_page_image_loaded', lambda: capture_preview(page, pages[-1], folder, 'last-page.png', timeout))

        # APIRequestContext shares the browser session, but these calls are only
        # explicit same-origin GETs. Every published artifact, including all PNGs
        # and retained diagnostics, gets a fresh HTTP/hash check.
        for index, artifact in enumerate(all_artifacts):
            item = {key: artifact.get(key) for key in ('artifact_id', 'name', 'media_type', 'sha256', 'revision')}
            item['status'] = 'IN_PROGRESS'
            item['delivery_status'] = artifact.get('status')
            response = None
            data = None
            try:
                require(re.fullmatch(r'[A-Za-z0-9_-]+', item['artifact_id']) is not None, 'Unsafe artifact ID')
                require(re.fullmatch(r'[0-9a-fA-F]{64}', item['sha256'] or '') is not None, 'Missing published SHA256')
                response = context.request.get(base_url + '/api/artifacts/' + quote(item['artifact_id'], safe=''), timeout=timeout, max_redirects=0)
                item['http_status'] = response.status
                network.append({'source': 'APIRequestContext', 'method': 'GET',
                                'url': base_url + '/api/artifacts/' + quote(item['artifact_id'], safe=''),
                                'status': response.status})
                require(response.status == 200, f'Artifact HTTP {response.status}')
                data = response.body()
                item.update(actual_sha256=sha256(data), bytes=len(data))
                require(item['actual_sha256'] == item['sha256'].lower(), 'Downloaded SHA256 differs from database-published SHA256')
                if item['media_type'] == 'image/png':
                    require(data.startswith(b'\x89PNG\r\n\x1a\n'), 'Invalid PNG signature')
                elif item['media_type'] == 'application/pdf':
                    require(data.startswith(b'%PDF-'), 'Invalid PDF signature')
                    if pdfs and item['artifact_id'] == pdfs[-1]['artifact_id']:
                        filename = 'downloaded-' + item['artifact_id'] + '.pdf'
                        (folder / filename).write_bytes(data)
                        item['saved_as'] = filename
                elif item['media_type'] == 'application/zip' or item['name'].endswith('.zip'):
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        require(archive.testzip() is None, 'ZIP CRC error')
                        require(any(member.endswith('.tex') for member in archive.namelist()), 'Source ZIP contains no TeX')
                    if zips and item['artifact_id'] == zips[-1]['artifact_id']:
                        filename = 'downloaded-' + item['artifact_id'] + '.zip'
                        (folder / filename).write_bytes(data)
                        item['saved_as'] = filename
                item['status'] = 'PASS'
            except Exception as error:
                item.update(status='FAIL', error=str(error)[:4000], error_type=type(error).__name__)
                if data is not None:
                    filename = 'failed-download-' + item['artifact_id'] + '.bin'
                    (folder / filename).write_bytes(data)
                    item['failure_body_saved_as'] = filename
            finally:
                if response is not None:
                    response.dispose()
                case['artifacts'].append(item)
                save_json(folder / 'result.json', case)
            if (index + 1) % 20 == 0:
                print(f'{name}: checked {index + 1}/{len(all_artifacts)} current/historical artifacts', flush=True)
    except Exception as error:
        case['fatal_error'] = {'type': type(error).__name__, 'message': str(error)[:4000]}
        (folder / 'failure-traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if before is not None:
            def unchanged():
                after = run_snapshot(get_json(context, base_url, '/api/runs/' + quote(run_id, safe=''), timeout, network))
                save_json(folder / 'run-after.json', after)
                require(after == before, 'Run status, model request count, approval, reviews or artifacts changed during this read-only verification')
                return {'unchanged': True, 'teacher_reviews_before': len(before.get('reviews') or []),
                        'teacher_reviews_after': len(after.get('reviews') or [])}
            record_check(case, 'run_state_and_teacher_reviews_unchanged', unchanged)
        record_check(case, 'no_page_errors', lambda: require(not page_errors, f'Browser page errors: {page_errors}'))
        record_check(case, 'no_state_changing_or_external_requests', lambda: require(not blocked, f'Forbidden requests blocked: {blocked}'))
        save_json(folder / 'console.json', console)
        save_json(folder / 'page-errors.json', page_errors)
        save_json(folder / 'network.json', network)
        save_json(folder / 'blocked-requests.json', blocked)
        if case.get('fatal_error') or any(check['status'] == 'FAIL' for check in case['checks']) or any(item['status'] == 'FAIL' for item in case['artifacts']):
            case['status'] = 'FAIL'
            try:
                page.screenshot(path=str(folder / 'failure.png'), full_page=False, timeout=timeout)
            except Exception as error:
                case['failure_screenshot_error'] = str(error)[:2000]
        else:
            case['status'] = 'PASS'
        save_json(folder / 'result.json', case)
        context.close()
    return case


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--state', type=Path, default=REPORTS / 'live-lectures' / 'benchmark_state.json')
    parser.add_argument('--output-dir', '--output', dest='output', type=Path,
                        help='New directory within reports; must not exist. --output is a compatibility alias.')
    parser.add_argument('--expected-delivery', type=Path,
                        help='Source-bundle verification report.json binding this UI check to the same ZIP/PDF artifact hashes')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--case', dest='selected_cases', action='append', choices=CASES,
                           help='Verify this ready case; repeat to select multiple cases')
    selection.add_argument('--cases', nargs='+', choices=CASES, help='Compatibility alias accepting multiple cases')
    parser.add_argument('--timeout-ms', type=int, default=30000)
    args = parser.parse_args(argv)
    args.cases = args.selected_cases or args.cases or list(CASES)
    base_url = args.base_url.rstrip('/')
    parsed = urlparse(base_url)
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        parser.error('--base-url must be an HTTP localhost origin without credentials, query, or path')
    if not 1000 <= args.timeout_ms <= 120000:
        parser.error('--timeout-ms must be between 1000 and 120000')
    if len(args.cases) != len(set(args.cases)):
        parser.error('--cases must not contain duplicate names')
    output = (args.output or REPORTS / ('live-ui-' + stamp() + '-' + uuid.uuid4().hex[:6])).resolve()
    if not output.is_relative_to(ALL_REPORTS.resolve()) or output == ALL_REPORTS.resolve() or output.exists():
        parser.error('--output-dir must be a new child directory of reports')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'IN_PROGRESS', 'started_at': datetime.now(timezone.utc).isoformat(),
              'base_url': base_url, 'state_path': str(args.state.resolve()), 'output': str(output),
              'provider_under_test': 'live', 'model_api_test': 'NOT_RUN_BY_THIS_SCRIPT',
              'teacher_visual_review': 'NOT_RUN', 'formal_mathematical_proof': 'NOT_PERFORMED',
              'service_start_stop': 'NOT_PERFORMED', 'cases': []}
    save_json(output / 'report.json', report)
    try:
        raw = args.state.read_bytes()
        state = json.loads(raw)
        report['state_sha256'] = sha256(raw)
        report['workspace_from_state'] = state.get('workspace')
        expected_cases = None
        if args.expected_delivery:
            expected_bytes = args.expected_delivery.read_bytes()
            expected_report = json.loads(expected_bytes)
            expected_cases = {item['case']: item for item in expected_report['cases']}
            require(all(name in expected_cases for name in args.cases), 'Expected delivery report is missing selected cases')
            report.update(expected_delivery_path=str(args.expected_delivery.resolve()),
                          expected_delivery_sha256=sha256(expected_bytes))
        report['browser_executable'] = edge_executable()
        require(report['browser_executable'], 'Microsoft Edge executable not found')
        save_json(output / 'selected-runs.json', {name: state.get('cases', {}).get(name, {}).get('run_id') for name in args.cases})
        from playwright.sync_api import sync_playwright
        with sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, executable_path=report['browser_executable'],
                env={key: value for key, value in os.environ.items() if not key.startswith('MATH_AGENT_') and key != 'OPENAI_API_KEY'})
            try:
                for name in args.cases:
                    run_id = state.get('cases', {}).get(name, {}).get('run_id')
                    if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
                        report['cases'].append({'name': name, 'status': 'FAIL', 'error': 'Missing or invalid run_id in state', 'teacher_visual_review': 'NOT_RUN'})
                    else:
                        report['cases'].append(verify_case(browser, base_url, name, run_id, output / name, args.timeout_ms,
                                                         expected_cases[name] if expected_cases is not None else None))
                    save_json(output / 'report.json', report)
                    print(f'{name}: {report["cases"][-1]["status"]}; evidence {output / name}', flush=True)
            finally:
                browser.close()
        report['status'] = 'PASS' if report['cases'] and all(case['status'] == 'PASS' for case in report['cases']) else 'FAIL'
    except Exception as error:
        report.update(status='FAIL', fatal_error={'type': type(error).__name__, 'message': str(error)[:4000]})
        (output / 'failure-traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['artifact_get_count'] = sum(len(case.get('artifacts', [])) for case in report['cases'])
        report['artifact_hash_pass_count'] = sum(item['status'] == 'PASS' for case in report['cases'] for item in case.get('artifacts', []))
        save_json(output / 'report.json', report)
        lines = ['# Read-only real-delivery UI verification', '', f'Automated result: **{report["status"]}**.', '',
                 'Existing live-provider runs were inspected through the actual local application. This script did not invoke a model, start/stop services, confirm/retry tasks, or submit reviews. Teacher visual/mathematics acceptance: **NOT_RUN**.', '',
                 '| Case | Automated result | Artifact GET / SHA checks |', '| --- | --- | --- |']
        for case in report['cases']:
            checked = case.get('artifacts', [])
            lines.append(f'| {case["name"]} | {case["status"]} | {sum(item["status"] == "PASS" for item in checked)}/{len(checked)} |')
        lines += ['', 'Each case folder retains partial/failure checks, console/page errors, screenshots, HTTP/hash evidence, before/after run snapshots, and one downloaded PDF/source ZIP when available. Every published PNG is downloaded and hashed; only first/last preview images are captured as screenshots, so this is not page-by-page human visual approval.', '', '[Detailed report](report.json)']
        (output / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'output': str(output), 'teacher_visual_review': 'NOT_RUN'}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
