"""Real Edge and Windows compilation; feedback assessment uses only the mock provider."""
import json

import pytest

from test_browser_workflows import (accepted_compile_artifacts, browser_page,
    confirm_execute_refresh, expect, local_services, submit_recommended, wait_for_plan)

pytestmark = [pytest.mark.e2e, pytest.mark.windows_compile]


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def test_current_feedback_receipts_are_visible_and_empty_next_round_retracts_them(browser_page, local_services):
    page, evidence = browser_page, local_services[1]
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('数列极限：逐项反馈回执浏览器验收')
    page.locator('#trusted-input').check()
    with page.expect_response(lambda response: response.url.endswith('/api/runs') and response.request.method == 'POST') as created:
        page.locator('#create-run').click()
    rid = created.value.json()['id']
    run_url = '/api/runs/' + rid
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    accepted_compile_artifacts(page)
    before = page.request.get(run_url).json()
    assert before.get('feedback_review') is None
    feedback = '1. 请补充夹逼计算训练。\n2. 请补充加减抵消的反例。\n3. 请说明经济模型的单位。'
    page.locator('#recheck-feedback').fill(feedback)
    with page.expect_response(lambda response: response.url.endswith(run_url+'/recheck') and response.request.method == 'POST') as submitted:
        page.locator('#recheck-run').click()
    assert submitted.value.status == 202
    job = submitted.value.json()
    page.wait_for_function("id => state.run?.jobs?.some(job => job.id === id && job.status === 'done')", arg=job['id'], timeout=180000)
    after = page.request.get(run_url).json()
    save(evidence/'receipt-before.json', before)
    save(evidence/'receipt-after.json', after)
    assert after['status'] == 'AWAITING_USER_REVIEW', after.get('error')
    receipt = after['feedback_review']
    assert receipt['job_id'] == job['id'] and receipt['status'] == 'reviewed'
    assert receipt['teacher_review'] == 'NOT_RUN' and receipt['mock'] is True
    assert [item['id'] for item in receipt['items']] == ['F1','F2','F3']
    assert all(item['status'] == 'rejected_not_supported' for item in receipt['items'])
    expect(page.locator('#feedback-review')).to_be_visible()
    expect(page.locator('#feedback-review')).to_contain_text('MOCK')
    for item in receipt['items']:
        row = page.locator('[data-feedback-id="'+item['id']+'"]')
        expect(row).to_contain_text('不适用')
        expect(row).to_contain_text(item['reason'])
    draft = '尚未提交的下一轮反馈草稿'
    page.locator('#recheck-feedback').fill(draft)
    page.evaluate('() => refreshRun(true)')
    expect(page.locator('#recheck-feedback')).to_have_value(draft)
    # Change only the receipt in one browser GET response. No server mutation:
    # timer polling must redraw a new receipt even if stage/jobs are unchanged.
    updated = json.loads(json.dumps(after))
    updated['feedback_review']['items'][0]['reason'] = '离线展示测试：新回执到达，任务的阶段和产物没有变化。'
    page.route('**'+run_url, lambda route: route.fulfill(status=200, content_type='application/json',
        body=json.dumps(updated, ensure_ascii=False)), times=1)
    expect(page.locator('[data-feedback-id="F1"]')).to_contain_text('新回执到达', timeout=10000)
    expect(page.locator('#recheck-feedback')).to_have_value(draft)
    page.screenshot(path=str(evidence/'receipt-visible-with-draft.png'), full_page=True)
    page.reload()
    expect(page.locator('#feedback-review')).to_contain_text('F3')
    # A fresh empty feedback action must withdraw previous-job receipts while
    # preserving their audit events and downloadable superseded deliveries.
    page.locator('#recheck-feedback').fill('')
    with page.expect_response(lambda response: response.url.endswith(run_url+'/recheck') and response.request.method == 'POST') as empty:
        page.locator('#recheck-run').click()
    assert empty.value.status == 202
    empty_job = empty.value.json()
    page.wait_for_function("id => state.run?.jobs?.some(job => job.id === id && job.status === 'done')", arg=empty_job['id'], timeout=180000)
    latest = page.request.get(run_url).json()
    assert latest['status'] == 'AWAITING_USER_REVIEW', latest.get('error')
    assert latest['feedback_review'] is None
    expect(page.locator('#feedback-review')).to_have_count(0)
    for key in ('approval','input_hash','plan','request_count','budget','reviews'):
        assert latest[key] == before[key], key
    assert latest['reviews'] == [] and latest['request_count'] == 0
    all_events = page.request.get(run_url+'/events').json()
    receipts = [value['payload'] for value in all_events if value['type']=='feedback.reviewed']
    assert receipts and all(value['job_id']==job['id'] for value in receipts)
    assert not any(value['type']=='human.review' for value in all_events)
    assert not any(url.endswith('/reviews') for url in posts)
    report = next(value for value in latest['artifacts'] if value['name']=='quality_report.json' and value['status']!='superseded')
    quality = page.request.get('/api/artifacts/'+report['artifact_id']).json()
    assert quality['compile']['status']=='PASS' and quality['compile']['passes'] >= 2
    save(evidence/'receipt-after-empty.json', latest)
    save(evidence/'receipt-events.json', all_events)
    save(evidence/'receipt-browser-result.json', {'status':'PASS','run_id':rid,'feedback_job_id':job['id'],
        'empty_feedback_job_id':empty_job['id'],'real_edge':'PASS','windows_compile':'PASS',
        'model_provider':'MOCK','real_api':'NOT_RUN','human_review_posts':0,
        'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN'})
