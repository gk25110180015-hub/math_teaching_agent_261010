"""Real Edge/Windows compiler with mock provider; no teacher-review submission."""
import json
import re

import pytest

from test_browser_workflows import (
    accepted_compile_artifacts, browser_page, confirm_execute_refresh, expect,
    local_services, submit_recommended, wait_for_plan,
)


pytestmark = [pytest.mark.e2e, pytest.mark.windows_compile]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def test_feedback_draft_survives_polling_rerender_and_error_then_submits_once(browser_page, local_services):
    page = browser_page
    evidence = local_services[1]
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('数列极限 · 复检意见草稿浏览器验收')
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
    accepted_compile_artifacts(page)
    before = page.request.get(run_url).json()
    save(evidence / 'feedback-before.json', before)
    assert before['input']['provider'] == 'mock' and before['reviews'] == []

    feedback = '请核查已批准的夹逼训练及两个重要极限的条件。\n请保留原有数学结论与教学范围。'
    field = page.locator('#recheck-feedback')
    expect(field).to_be_visible()
    assert field.get_attribute('maxlength') == '10000'
    field.fill(feedback)
    # Observe actual timer-driven polling, then deliberately force a rerender:
    # a stable AWAITING_USER_REVIEW response need not change the fingerprint.
    with page.expect_response(lambda response: response.url.endswith(run_url)
                              and response.request.method == 'GET'):
        page.wait_for_timeout(2500)
    expect(field).to_have_value(feedback)
    page.evaluate('() => refreshRun(true)')
    expect(page.locator('#recheck-feedback')).to_have_value(feedback)
    page.screenshot(path=str(evidence / 'feedback-after-poll-and-rerender.png'), full_page=True)

    # Intercept one request in the isolated browser. It cannot mutate server
    # state; HTTP 409 exercises the UI's forced refresh and draft retention.
    page.route('**' + run_url + '/recheck', lambda route: route.fulfill(
        status=409, content_type='application/json',
        body=json.dumps({'error': {'code': 'OFFLINE_SYNTHETIC_CONFLICT',
                                  'message': '离线测试：本次请求未写入服务器，请再次提交。'}}, ensure_ascii=False)), times=1)
    with page.expect_response(lambda response: response.url.endswith(run_url + '/recheck')) as rejected:
        page.locator('#recheck-run').click()
    assert rejected.value.status == 409
    expect(page.locator('#notice')).to_contain_text('本次请求未写入服务器')
    expect(page.locator('#recheck-feedback')).to_have_value(feedback)
    expect(page.locator('#recheck-run')).to_be_enabled()
    assert page.request.get(run_url).json() == before
    page.screenshot(path=str(evidence / 'feedback-after-synthetic-error.png'), full_page=True)

    with page.expect_response(lambda response: response.url.endswith(run_url + '/recheck')
                              and response.request.method == 'POST') as submitted:
        page.locator('#recheck-run').click()
    assert submitted.value.status == 202
    job = submitted.value.json()
    sent = submitted.value.request.post_data_json
    assert sent['feedback'] == feedback and sent['feedback_source'] == 'user'
    save(evidence / 'feedback-submitted-request.json', sent)
    save(evidence / 'feedback-job.json', job)
    # Do not reload here: an empty input after the next completion must result
    # from clearing the successful draft, rather than losing page memory.
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', re.compile(
        r'^(AWAITING_USER_REVIEW|FAILED|BLOCKED)$'), timeout=180_000)
    # An initial status update may still show the prior AWAITING_USER_REVIEW.
    page.wait_for_function("id => state.run?.jobs?.some(job => job.id === id && job.status === 'done')", arg=job['id'], timeout=180000)
    after = page.request.get(run_url).json()
    save(evidence / 'feedback-after.json', after)
    assert after['status'] == 'AWAITING_USER_REVIEW', after.get('error')
    expect(page.locator('#recheck-feedback')).to_have_value('')
    for key in ('approval', 'input_hash', 'plan', 'request_count', 'budget', 'reviews'):
        assert after[key] == before[key], key
    assert after['reviews'] == [] and after['request_count'] == 0
    current_report = next(value for value in after['artifacts']
                          if value['name'] == 'quality_report.json' and value['status'] != 'superseded')
    quality = page.request.get('/api/artifacts/' + current_report['artifact_id']).json()
    assert quality['compile']['status'] == 'PASS' and quality['compile']['passes'] >= 2
    assert quality['layout']['evidence']['all_rendered'] is True
    values = page.request.get(run_url + '/events').json()
    recorded = [value['payload'] for value in values if value['type'] == 'checks.rerun_requested']
    assert len(recorded) == 1 and recorded[0]['job_id'] == job['id']
    assert recorded[0]['feedback'] == feedback and recorded[0]['feedback_source'] == 'user'
    assert recorded[0]['plan_hash'] == before['approval']['hash']
    assert not any(value['type'] in ('human.review', 'provider.request') for value in values)
    assert not any(url.endswith('/reviews') for url in posts)
    save(evidence / 'feedback-events.json', values)
    save(evidence / 'feedback-result.json', {
        'status': 'PASS', 'run_id': run_id, 'job_id': job['id'], 'real_edge': 'PASS',
        'polling_preserves_draft': True, 'forced_rerender_preserves_draft': True,
        'synthetic_error_preserves_draft': True, 'successful_submit_clears_draft': True,
        'recorded_feedback_actions': 1, 'windows_compile': 'PASS',
        'model_provider': 'MOCK', 'real_api': 'NOT_RUN', 'human_review_posts': 0,
        'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'})
