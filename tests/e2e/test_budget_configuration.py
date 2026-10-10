"""Real browser controls, isolated MOCK workflow and actual TeX compilation."""
import io
import zipfile

import pytest

from math_agent.util import digest
from test_browser_workflows import (
    local_services, browser_page, expect, wait_for_plan, submit_recommended,
    accepted_compile_artifacts,
)

pytestmark = pytest.mark.e2e


def test_configure_before_execution_and_download_tex(browser_page, local_services):
    page = browser_page
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('最小二乘法：执行前预算与源码下载测试')
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    rid = page.evaluate("localStorage.getItem('math-agent-run')")
    before = page.request.get(f'/api/runs/{rid}').json()
    assert before['budget']['can_configure']
    page.locator('#budget-requests').fill('80')
    page.locator('#budget-local_repairs_per_unit').fill('0')
    page.locator('#budget-global_repair_rounds').fill('0')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 80')
    configured = page.request.get(f'/api/runs/{rid}').json()
    for key in ('status', 'plan', 'approval', 'jobs', 'request_count'):
        assert configured[key] == before[key], key
    assert configured['budget']['local_repairs_per_unit'] == 0
    assert configured['budget']['global_repair_rounds'] == 0
    page.reload()
    expect(page.locator('#budget-requests')).to_have_value('80')
    expect(page.locator('#budget-local_repairs_per_unit')).to_have_value('0')
    expect(page.locator('#budget-global_repair_rounds')).to_have_value('0')

    # Confirmation must retain both saved budgets and unsaved in-page edits.
    page.locator('#budget-requests').fill('160')
    page.locator('#confirm-plan').click()
    page.locator('#execute-plan').wait_for()
    expect(page.locator('#budget-requests')).to_have_value('160')
    confirmed = page.request.get(f'/api/runs/{rid}').json()
    assert confirmed['budget']['requests'] == 80
    page.locator('#execute-plan').click()
    expect(page.locator('#notice')).to_contain_text('预算修改尚未保存')
    after_unsaved = page.request.get(f'/api/runs/{rid}').json()
    assert after_unsaved['status'] == 'PLAN_CONFIRMED'
    assert after_unsaved['jobs'] == confirmed['jobs']
    page.locator('#budget-local_repairs_per_unit').fill('3')
    page.locator('#budget-global_repair_rounds').fill('4')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 160')
    saved = page.request.get(f'/api/runs/{rid}').json()
    for key in ('status', 'plan', 'approval', 'jobs', 'request_count'):
        assert saved[key] == confirmed[key], key
    page.reload()
    expect(page.locator('#budget-requests')).to_have_value('160')
    expect(page.locator('#budget-local_repairs_per_unit')).to_have_value('3')
    expect(page.locator('#budget-global_repair_rounds')).to_have_value('4')
    page.locator('#execute-plan').click()
    accepted_compile_artifacts(page)
    completed = page.request.get(f'/api/runs/{rid}').json()
    assert not completed['budget']['can_configure']
    assert completed['budget']['requests'] == 160
    assert completed['budget']['local_repairs_per_unit'] == 3
    assert completed['budget']['global_repair_rounds'] == 4
    assert completed['reviews'] == []
    assert page.locator('#budget-form').count() == 0

    files = {}
    for selector, name in [('#download-tex', 'lecture.tex'), ('#download-source-zip', 'source_bundle.zip'), ('#download-pdf', 'lecture.pdf')]:
        link = page.locator(selector)
        expect(link).to_be_visible()
        artifact = next(a for a in completed['artifacts'] if a['name'] == name and a['status'] != 'superseded')
        assert link.get_attribute('href') == f"/api/artifacts/{artifact['artifact_id']}"
        with page.expect_download() as download_info:
            link.click()
        downloaded = download_info.value
        assert downloaded.suggested_filename == name
        target = local_services[1] / name
        downloaded.save_as(target)
        files[name] = target.read_bytes()
        assert digest(files[name]) == artifact['sha256']
    with zipfile.ZipFile(io.BytesIO(files['source_bundle.zip'])) as archive:
        assert archive.read('lecture.tex') == files['lecture.tex']
    assert b'\\documentclass' in files['lecture.tex']
    assert files['lecture.pdf'].startswith(b'%PDF-')
    page.locator('#artifact-downloads').screenshot(path=str(local_services[1] / 'download-buttons.png'))
