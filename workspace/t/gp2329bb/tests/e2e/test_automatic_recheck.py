"""Actual Edge + independent services + Windows XeLaTeX; mock models only.

Does not submit any human-review action or contact a remote model provider.
Run only after the automatic-recheck proposal has been applied to production.
"""
import hashlib
import json
import re

import pytest

from test_browser_workflows import (
    accepted_compile_artifacts,
    browser_page,
    confirm_execute_refresh,
    expect,
    local_services,
    submit_recommended,
    wait_for_plan,
)


pytestmark = [pytest.mark.e2e, pytest.mark.windows_compile]


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def test_recheck_real_click_preserves_downloadable_history_and_current_review_targets(browser_page, local_services):
    page = browser_page
    evidence = local_services[1]
    posts = []
    page.on('request', lambda request: posts.append(request.url)
            if request.method == 'POST' else None)
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('数列极限 · 自动复检与历史交付浏览器回归')
    page.locator('#trusted-input').check()
    with page.expect_response(lambda response: response.url.endswith('/api/runs')
                              and response.request.method == 'POST') as created:
        page.locator('#create-run').click()
    assert created.value.status == 201
    run_id = created.value.json()['id']
    run_url = '/api/runs/' + run_id
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    first_report, _ = accepted_compile_artifacts(page)
    before = page.request.get(run_url).json()
    save_json(evidence / 'automatic-recheck-before.json', before)
    save_json(evidence / 'automatic-recheck-initial-quality.json', first_report)
    old_artifacts = {artifact['artifact_id']: artifact for artifact in before['artifacts']}
    old_pages = {artifact_id for artifact_id, artifact in old_artifacts.items()
                 if artifact['media_type'] == 'image/png' and artifact['metadata'].get('physical_page')}
    assert old_pages and before['reviews'] == []
    assert before['input']['provider'] == 'mock'
    page.screenshot(path=str(evidence / 'automatic-recheck-before.png'), full_page=True)
    expect(page.locator('#recheck-run')).to_be_enabled()
    with page.expect_response(lambda response: response.url.endswith(run_url + '/recheck')
                              and response.request.method == 'POST') as rechecked:
        page.locator('#recheck-run').click()
    assert rechecked.value.status == 202
    job = rechecked.value.json()
    save_json(evidence / 'automatic-recheck-job.json', job)
    assert job['kind'] == 'build' and job['id'] not in {row['id'] for row in before['jobs']}

    # A browser refresh during the asynchronous build must restore the same run.
    page.reload()
    page.locator('#run-stage').wait_for()
    assert page.locator('#confirm-plan').count() == 0
    terminal = page.locator('[data-testid=run-status]')
    expect(terminal).to_have_attribute('data-status', re.compile(
        r'^(AWAITING_USER_REVIEW|FAILED|BLOCKED|COMPLETED|COMPLETED_WITH_WARNINGS)$'), timeout=180_000)
    after = page.request.get(run_url).json()
    save_json(evidence / 'automatic-recheck-after.json', after)
    assert after['status'] == 'AWAITING_USER_REVIEW', after.get('error')
    assert next(row for row in after['jobs'] if row['id'] == job['id'])['status'] == 'done'
    assert len(after['jobs']) == len(before['jobs']) + 1
    assert after['approval'] == before['approval']
    assert after['input_hash'] == before['input_hash']
    assert after['plan']['hash'] == before['plan']['hash']
    assert after['request_count'] == before['request_count'] == 0
    assert after['budget'] == before['budget']
    assert after['reviews'] == []

    historical = {artifact['artifact_id']: artifact for artifact in after['artifacts']
                  if artifact['status'] == 'superseded'}
    current = {artifact['artifact_id']: artifact for artifact in after['artifacts']
               if artifact['status'] != 'superseded'}
    assert set(historical) == set(old_artifacts) and current
    assert not set(current).intersection(old_artifacts)
    new_pages = {artifact_id for artifact_id, artifact in current.items()
                 if artifact['media_type'] == 'image/png' and artifact['metadata'].get('physical_page')}
    quality = [artifact for artifact in current.values() if artifact['name'] == 'quality_report.json']
    assert len(quality) == 1
    report = page.request.get('/api/artifacts/' + quality[0]['artifact_id']).json()
    save_json(evidence / 'automatic-recheck-new-quality.json', report)
    assert report['compile']['status'] == 'PASS'
    assert report['compile']['passes'] >= 2
    assert report['layout']['evidence']['all_rendered'] is True
    assert len(new_pages) == report['layout']['evidence']['page_count'] > 0

    # Restore again after completion, then exercise the actual history links.
    page.reload()
    page.locator('#recheck-run').wait_for()
    history = page.locator('#artifact-history')
    expect(history).to_be_visible()
    history.locator('summary').click()
    links = history.locator('a[data-historical-artifact-id]')
    assert links.count() == len(old_artifacts)
    downloads = []
    for link in links.all():
        artifact_id = link.get_attribute('data-historical-artifact-id')
        response = page.request.get(link.get_attribute('href'))
        observed = hashlib.sha256(response.body()).hexdigest()
        assert response.status == 200 and observed == old_artifacts[artifact_id]['sha256']
        downloads.append({'artifact_id': artifact_id, 'status': response.status, 'sha256': observed})
    save_json(evidence / 'automatic-recheck-history-downloads.json', downloads)
    rendered_pages = set(page.locator('.page-review').evaluate_all(
        "nodes => nodes.map(node => node.dataset.pageId)"))
    assert rendered_pages == new_pages and not rendered_pages.intersection(old_pages)
    assert page.locator('#approve-quality-report').count() == 1
    for link in page.locator('a[data-artifact-id]').all():
        assert link.get_attribute('data-artifact-id') in current
    preview = page.locator('iframe.pdf-preview')
    assert preview.count() == 1
    current_pdfs = {artifact_id for artifact_id, artifact in current.items()
                    if artifact['media_type'] == 'application/pdf'}
    assert preview.get_attribute('src').rsplit('/', 1)[-1] in current_pdfs
    for image in page.locator('.page-review img').all():
        response = page.request.get(image.get_attribute('src'))
        assert response.status == 200 and response.body().startswith(b'\x89PNG\r\n\x1a\n')

    events = page.request.get(run_url + '/events').json()
    save_json(evidence / 'automatic-recheck-events.json', events)
    assert len([event for event in events if event['type'] == 'checks.rerun_requested']) == 1
    assert not any(event['type'] in ('human.review', 'provider.request') for event in events)
    assert not any(url.endswith('/reviews') for url in posts)
    page.screenshot(path=str(evidence / 'automatic-recheck-history-and-current.png'), full_page=True)
    save_json(evidence / 'automatic-recheck-result.json', {
        'status': 'PASS', 'run_id': run_id, 'recheck_job_id': job['id'],
        'model_provider': 'MOCK', 'real_api': 'NOT_RUN',
        'windows_compile': 'PASS', 'initial_pages': len(old_pages), 'rechecked_pages': len(new_pages),
        'real_browser': 'PASS', 'historical_downloads_checked': len(downloads),
        'teacher_mathematics_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
        'human_review_posts': 0, 'request_count_preserved': after['request_count'],
        'approval_preserved': after['approval'] == before['approval']})
