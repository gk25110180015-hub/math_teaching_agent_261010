"""Beamer budget controls with real browser/HTTP and an isolated MOCK workspace."""
import json
from pathlib import Path
import time

import pytest

from math_agent.store import Store
from math_agent.util import now, uid
from test_browser_workflows import (
    local_services, browser_page, expect, wait_for_plan, submit_recommended,
    accepted_compile_artifacts,
)

pytestmark = pytest.mark.e2e


def test_beamer_prebuild_configuration_and_visible_quality_blocked_increase(browser_page, local_services, tmp_path):
    page = browser_page
    source = tmp_path / 'lecture.tex'
    source.write_text(r'''\documentclass{ctexart}
\usepackage{amsmath,amssymb,amsthm}
\newtheorem{definition}{定义}
\begin{document}
\section{数列极限}
\begin{definition}各项取值相同的数列称为常数数列。例如 $a_n=1$ 是常数数列。\end{definition}
\end{document}
''', encoding='utf-8')
    page.locator('#workflow').select_option('beamer.from_tex')
    page.locator('#provider').select_option('mock')
    page.locator('#source-file').set_input_files(str(source))
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    rid = page.evaluate("localStorage.getItem('math-agent-run')")
    before = page.request.get(f'/api/runs/{rid}').json()
    assert before['workflow_id'] == 'beamer.from_tex' and before['budget']['can_configure']
    page.locator('#budget-requests').fill('80')
    page.locator('#budget-local_repairs_per_unit').fill('0')
    page.locator('#budget-global_repair_rounds').fill('0')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 80')
    configured = page.request.get(f'/api/runs/{rid}').json()
    for key in ('status', 'plan', 'approval', 'jobs', 'request_count'):
        assert configured[key] == before[key]
    assert configured['budget']['local_repairs_per_unit'] == configured['budget']['global_repair_rounds'] == 0
    page.locator('#confirm-plan').click()
    page.locator('#execute-plan').wait_for()
    page.reload()
    expect(page.locator('#budget-requests')).to_have_value('80')
    expect(page.locator('#budget-local_repairs_per_unit')).to_have_value('0')
    expect(page.locator('#budget-global_repair_rounds')).to_have_value('0')
    confirmed = page.request.get(f'/api/runs/{rid}').json()
    page.locator('#budget-requests').fill('160')
    page.locator('#budget-local_repairs_per_unit').fill('3')
    page.locator('#budget-global_repair_rounds').fill('4')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 160')
    saved = page.request.get(f'/api/runs/{rid}').json()
    assert saved['approval'] == confirmed['approval'] and saved['jobs'] == confirmed['jobs']

    # Only the isolated browser-test DB: model the live QUALITY_BLOCKED state.
    # Lease the synthetic build ourselves so the background worker cannot claim it.
    runtime = Path(json.loads((local_services[1] / 'context.json').read_text(encoding='utf-8'))['workspace'])
    store = Store(runtime / 'w' / 'agent.db')
    jid = uid()
    with store.transaction() as connection:
        connection.execute('INSERT INTO jobs(id,run_id,kind,build_key,status,lease_owner,lease_deadline,fencing_token,attempt,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (jid, rid, 'build', 'synthetic-quality-' + jid, 'running', 'budget-quality-fixture', time.time() + 300, 1, 1, now()))
        job = dict(connection.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())
    for _ in range(2):
        store.count_request(job, 160, {'fixture': 'SYNTHETIC_COUNTER_NO_API_REQUEST'})
    store.finish(job, 'BLOCKED', 'compile.global', {'code': 'QUALITY_BLOCKED',
        'message': '离线界面回归：模拟编译质量阻塞；不是预算耗尽，未调用真实模型。'})
    page.reload()
    expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status', 'BLOCKED')
    blocked = page.request.get(f'/api/runs/{rid}').json()
    assert blocked['budget']['can_increase'] and not blocked['budget']['can_configure']
    assert page.locator('#budget-editor').evaluate('(element) => element.open')
    expect(page.locator('#budget-configuration-policy')).to_contain_text('只能提高上限')
    for key in ('requests', 'local_repairs_per_unit', 'global_repair_rounds'):
        expect(page.locator('#budget-' + key)).to_be_visible()
    page.locator('#budget-panel').screenshot(path=str(local_services[1] / 'beamer-quality-blocked-budget.png'))
    page.locator('#budget-requests').fill('180')
    page.locator('#budget-local_repairs_per_unit').fill('5')
    page.locator('#budget-global_repair_rounds').fill('6')
    page.locator('#budget-note').fill('离线测试：明确提高三项预算，保留请求计数及原计划审批。')
    page.locator('#save-budget').click()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 180')
    after = page.request.get(f'/api/runs/{rid}').json()
    for key in ('status', 'request_count', 'approval', 'plan', 'error', 'jobs', 'artifacts', 'reviews'):
        assert after[key] == blocked[key], key
    assert after['budget']['local_repairs_per_unit'] == 5 and after['budget']['global_repair_rounds'] == 6
    assert after['budget']['request_count'] == blocked['request_count']
    page.reload()
    expect(page.locator('#budget-requests')).to_be_visible()
    expect(page.locator('#budget-summary')).to_contain_text('/ 上限 180')
    expect(page.locator('#retry-run')).to_be_enabled()
    page.locator('#retry-run').click()
    expect(page.locator('[data-testid=run-status]')).not_to_have_attribute('data-status', 'BLOCKED')
    accepted_compile_artifacts(page)
    resumed = page.request.get(f'/api/runs/{rid}').json()
    assert resumed['approval'] == blocked['approval']
    assert resumed['budget']['requests'] == 180
    assert resumed['budget']['local_repairs_per_unit'] == 5
    assert resumed['budget']['global_repair_rounds'] == 6
    assert resumed['request_count'] == blocked['request_count'] and resumed['reviews'] == []
    (local_services[1] / 'beamer-budget-evidence.json').write_text(json.dumps({
        'provider': 'mock', 'real_api': 'NOT_RUN', 'synthetic_failure': 'QUALITY_BLOCKED',
        'synthetic_requests': 2, 'prebuild_configured': configured['budget'],
        'blocked_budget': blocked['budget'], 'increased_budget': after['budget'],
        'approval_preserved': True, 'automatic_execution_on_save': False,
        'retry_status': resumed['status'], 'compilation': 'ACTUAL_WINDOWS_XELATEX',
        'teacher_review': 'NOT_RUN',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
