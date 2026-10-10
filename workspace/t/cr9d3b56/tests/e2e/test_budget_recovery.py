"""MOCK browser budget recovery with real Windows TeX and hash-checked drafts.

The exhausted request count is a labelled synthetic fixture, not model traffic.
No teacher reviews or live API requests are submitted.
"""
import json
from pathlib import Path
import time

import pytest

from math_agent.store import Store
from math_agent.util import AgentError, digest
from test_browser_workflows import (
    local_services, browser_page, expect, wait_for_plan, submit_recommended,
    confirm_execute_refresh, accepted_compile_artifacts,
)

pytestmark = pytest.mark.e2e


def test_explicit_budget_increase_preserves_approval_and_partial_drafts(browser_page, local_services):
    page = browser_page
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('数列极限：预算恢复界面测试')
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    accepted_compile_artifacts(page)
    rid = page.evaluate("localStorage.getItem('math-agent-run')")
    assert rid
    completed = page.request.get(f'/api/runs/{rid}').json()
    assert completed['input']['provider'] == 'mock' and completed['reviews'] == []
    runtime = Path(json.loads((local_services[1] / 'context.json').read_text(encoding='utf-8'))['workspace'])
    store = Store(runtime / 'w' / 'agent.db')
    limit = completed['budget']['requests']
    # ONLY this isolated test DB: create an exhausted counter without sending
    # requests, then use the real Store guard and worker failure transition.
    with store.transaction() as connection:
        job = dict(connection.execute("SELECT * FROM jobs WHERE run_id=? AND kind='build' ORDER BY created_at DESC LIMIT 1", (rid,)).fetchone())
        connection.execute("UPDATE jobs SET status='running',lease_owner=?,lease_deadline=?,fencing_token=fencing_token+1 WHERE id=?",
            ('synthetic-budget-browser-fixture', time.time() + 300, job['id']))
        connection.execute('UPDATE runs SET request_count=? WHERE id=?', (limit, rid))
        job = dict(connection.execute('SELECT * FROM jobs WHERE id=?', (job['id'],)).fetchone())
    with pytest.raises(AgentError) as error:
        store.count_request(job, limit, {'fixture': 'SYNTHETIC_COUNTER_NO_API_REQUEST'})
    assert error.value.code == 'BUDGET_EXHAUSTED'
    store.finish(job, 'BLOCKED', 'fixture.budget_exhausted', {'code': error.value.code,
        'message': '界面测试：模拟请求计数耗尽，未发送这些模型请求。'})
    page.reload()
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', 'BLOCKED')
    expect(page.locator('#budget-summary')).to_contain_text(f'已用 {limit} / 上限 {limit}')
    expect(page.locator('#retry-run')).to_be_disabled()
    expect(page.locator('#partial-checkpoints')).to_be_visible()
    expect(page.locator('#partial-checkpoints')).to_contain_text('全文仍未完成')
    partials = page.request.get(f'/api/runs/{rid}/partials').json()
    assert partials and all(part['teacher_review'] == 'NOT_RUN' for part in partials)
    assert all(part['plan_binding'] == 'UNKNOWN' for part in partials)
    downloaded = []
    for part in partials:
        assert part['status'] == 'PARTIAL'
        assert {file['kind'] for file in part['downloads']} == {'pdf', 'source', 'checkpoint'}
        for file in part['downloads']:
            result = page.request.get(file['url'])
            assert result.status == 200 and digest(result.body()) == file['sha256']
            assert result.headers['x-math-agent-status'] == 'PARTIAL'
            downloaded.append({'name': file['name'], 'sha256': file['sha256'], 'http_status': result.status})
    page.locator('[data-partial-section]').first.locator('summary').click()
    expect(page.locator('[data-partial-section]').first).to_contain_text('当前计划关联未核验')
    page.screenshot(path=str(local_services[1] / 'budget-blocked-partial.png'), full_page=True)
    before = page.request.get(f'/api/runs/{rid}').json()
    page.locator('#budget-requests').fill(str(limit + 1))
    page.locator('#budget-note').fill('测试用户明确增加一次请求；保留既有审批与累计计数。')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text(f'已用 {limit} / 上限 {limit + 1}')
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', 'BLOCKED')
    expect(page.locator('#retry-run')).to_be_enabled()
    after = page.request.get(f'/api/runs/{rid}').json()
    assert after['budget']['version'] == 1
    for key in ('request_count', 'approval', 'error', 'jobs', 'artifacts', 'reviews'):
        assert after[key] == before[key], key
    assert after['reviews'] == []
    page.reload()
    expect(page.locator('#budget-summary')).to_contain_text(f'已用 {limit} / 上限 {limit + 1}')
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', 'BLOCKED')
    page.screenshot(path=str(local_services[1] / 'budget-increased-no-execution.png'), full_page=True)
    page.locator('#retry-run').click()
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', 'AWAITING_USER_REVIEW', timeout=120_000)
    resumed = page.request.get(f'/api/runs/{rid}').json()
    # Retry deliberately retains previous artifact versions. Select the new
    # report by its ID rather than the original single-build helper's name.
    previous_ids = {artifact['artifact_id'] for artifact in before['artifacts']}
    new_artifacts = [artifact for artifact in resumed['artifacts'] if artifact['artifact_id'] not in previous_ids]
    report_artifact = next(artifact for artifact in new_artifacts if artifact['name'] == 'quality_report.json')
    report = page.request.get(f"/api/artifacts/{report_artifact['artifact_id']}").json()
    assert report['compile']['status'] == 'PASS'
    assert report['layout']['evidence']['all_rendered'] is True
    assert sum(artifact['media_type'] == 'image/png' for artifact in new_artifacts) == report['layout']['evidence']['page_count']
    assert any(artifact['media_type'] == 'application/pdf' for artifact in new_artifacts)
    assert any(artifact['name'] == 'source_bundle.zip' for artifact in new_artifacts)
    for artifact in new_artifacts:
        result = page.request.get(f"/api/artifacts/{artifact['artifact_id']}")
        assert result.status == 200 and digest(result.body()) == artifact['sha256']
    assert page.locator('.page-review').count() == sum(artifact['media_type'] == 'image/png' for artifact in resumed['artifacts'])
    assert resumed['request_count'] == limit and resumed['approval'] == before['approval']
    assert resumed['reviews'] == [] and resumed['budget']['requests'] == limit + 1
    (local_services[1] / 'budget-flow-evidence.json').write_text(json.dumps({
        'status': 'PASS', 'provider': 'mock', 'real_api': 'NOT_RUN', 'teacher_review': 'NOT_RUN',
        'compilation': 'ACTUAL_WINDOWS_XELATEX', 'request_counter_fixture': 'SYNTHETIC_NO_MODEL_CALLS',
        'run_id': rid, 'old_limit': limit, 'new_limit': limit + 1,
        'request_count_preserved': limit, 'no_automatic_execution': True,
        'approval_preserved': True, 'partial_downloads': downloaded,
        'final_status': resumed['status'], 'final_artifact_count': len(resumed['artifacts']),
        'new_artifact_count': len(new_artifacts), 'new_page_count': report['layout']['evidence']['page_count'],
    }, ensure_ascii=False, indent=2), encoding='utf-8')
