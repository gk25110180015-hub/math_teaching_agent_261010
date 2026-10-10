"""Download the app's own lecture and upload it unchanged to the Beamer workflow."""
import pytest

from test_browser_workflows import (
    local_services, browser_page, expect, wait_for_plan, submit_recommended,
    confirm_execute_refresh, accepted_compile_artifacts,
)

pytestmark = pytest.mark.e2e


def test_downloaded_lecture_tex_builds_beamer_with_exercises(browser_page, tmp_path):
    page = browser_page
    page.locator('#provider').select_option('mock')
    page.locator('#topic').fill('最小二乘法')
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    accepted_compile_artifacts(page)
    with page.expect_download() as info:
        page.locator('#download-tex').click()
    source = tmp_path / 'lecture.tex'
    info.value.save_as(source)
    assert r'\begin{exercise}' in source.read_text(encoding='utf-8')

    page.locator('#new-run').click()
    page.locator('#workflow').select_option('beamer.from_tex')
    page.locator('#provider').select_option('mock')
    page.locator('#source-file').set_input_files(str(source))
    if page.locator('#theme option[value=fduclassroom]').is_enabled():
        page.locator('#theme').select_option('fduclassroom')
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    expect(page.locator('#budget-requests')).to_be_visible()
    confirm_execute_refresh(page)
    report, converted = accepted_compile_artifacts(page)
    assert report['fidelity']['status'] == 'PASS'
    assert r'\begin{exercise}' in converted
    assert not any(issue.get('severity') == 'blocking' for issue in report['issues'])
    expect(page.locator('#download-tex')).to_have_text('下载课件 TeX')
    rid = page.evaluate("localStorage.getItem('math-agent-run')")
    assert page.request.get(f'/api/runs/{rid}').json()['reviews'] == []
