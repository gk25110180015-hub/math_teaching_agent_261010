"""Actual browser clicks against separate local server and worker processes.

These are MOCK provider tests with actual local TeX compilation where asserted.
A successful test does not imply real API or teacher mathematics/visual acceptance.
"""
from __future__ import annotations

import hashlib
import json
import io
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

import pytest

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.e2e
PROJECT = Path(__file__).resolve().parents[2]


def browser_executable() -> str | None:
    override = os.environ.get("MATH_AGENT_BROWSER_PATH")
    candidates = [
        override,
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    return next((p for p in candidates if p and Path(p).is_file()), None)


@pytest.fixture(scope="module")
def local_services(tmp_path_factory):
    evidence_root = Path(os.environ.get("MATH_AGENT_E2E_EVIDENCE_ROOT", PROJECT / "reports" / "e2e")).resolve()
    if not evidence_root.is_relative_to((PROJECT / "reports").resolve()):
        pytest.fail("E2E evidence must remain within this project's reports directory")
    evidence = evidence_root / time.strftime("%Y%m%d-%H%M%S")
    evidence.mkdir(parents=True, exist_ok=True)
    runtime = tmp_path_factory.mktemp("r")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("MATH_AGENT_"):
            env.pop(key)
    env.update({
        "MATH_AGENT_WORKSPACE": str(runtime / "w"),
        "MATH_AGENT_DATABASE_URL": "sqlite:///" + (runtime / "agent.db").as_posix(),
        "MATH_AGENT_REFERENCE_ROOT": str(PROJECT.parent),
        "MATH_AGENT_LIVE_API_ENABLED": "false",
        "MATH_AGENT_API_KEY": "",
        "MATH_AGENT_LLM_STREAMING": "false",
        "MATH_AGENT_PORT": str(port),
        "PYTHONUNBUFFERED": "1",
    })
    processes = []
    logs = []
    try:
        for role, args in [
            ("server", ["serve", "--host", "127.0.0.1", "--port", str(port)]),
            ("worker", ["worker", "--concurrency", "1"]),
        ]:
            log = (evidence / f"{role}.log").open("w", encoding="utf-8")
            logs.append(log)
            processes.append(subprocess.Popen(
                [sys.executable, "-m", "math_agent.cli", *args],
                cwd=PROJECT, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                pytest.fail(f"Local service exited; preserved logs: {evidence}")
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(.2)
        else:
            pytest.fail(f"Server startup timed out; preserved logs: {evidence}")
        (evidence / "context.json").write_text(json.dumps({
            "base_url": base, "workspace": str(runtime), "provider": "mock",
            "live_api_enabled": False, "api_key_in_child_environment": "EMPTY",
            "llm_streaming": False,
            "teacher_visual_review": "NOT_RUN", "browser": browser_executable(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        yield base, evidence
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == "nt":
                    taskkill = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
                    subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        for log in logs:
            log.close()


@pytest.fixture
def browser_page(local_services, request):
    playwright = pytest.importorskip("playwright.sync_api")
    executable = browser_executable()
    with playwright.sync_playwright() as manager:
        try:
            browser = manager.chromium.launch(headless=True, executable_path=executable)
        except playwright.Error as error:
            pytest.skip(f"Browser unavailable: {str(error)[:300]}")
        context = browser.new_context(base_url=local_services[0], viewport={"width": 1440, "height": 1100}, locale="zh-CN")
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(local_services[0])
        page.locator("#new-run-form").wait_for()
        yield page
        page.screenshot(path=str(local_services[1] / f"{request.node.name}.png"), full_page=True)
        context.tracing.stop(path=str(local_services[1] / f"{request.node.name}-trace.zip"))
        (local_services[1] / f"{request.node.name}-console.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
        browser.close()
        assert not errors, f"Browser JavaScript errors: {errors}"


def wait_for_plan(page):
    page.locator("#decisions-form").wait_for(timeout=60_000)


def submit_recommended(page):
    if page.locator("#use-recommended").count():
        page.locator("#use-recommended").click()
    page.locator("#save-decisions").click()
    expect(page.locator("#confirm-plan")).to_be_enabled()


def confirm_execute_refresh(page):
    page.locator("#confirm-plan").click()
    page.locator("#execute-plan").wait_for()
    page.reload()
    page.locator("#execute-plan").wait_for()
    assert page.locator("#confirm-plan").count() == 0
    page.locator("#execute-plan").click()
    expect(page.locator("[data-testid=run-status]")).not_to_have_attribute("data-status", "PLAN_CONFIRMED")
    page.reload()
    page.locator("#run-stage").wait_for()
    assert page.locator("#confirm-plan").count() == 0
    assert page.locator("#decisions-form").count() == 0


def accepted_compile_artifacts(page):
    # Human review remains pending. The test must not click human approval or
    # misclassify an arbitrary worker failure as a successful lifecycle.
    status = page.locator("[data-testid=run-status]")
    expect(status).to_have_attribute("data-status", re.compile(r"^(AWAITING_USER_REVIEW|FAILED|BLOCKED|COMPLETED|COMPLETED_WITH_WARNINGS)$"), timeout=120_000)
    error = page.locator(".error-panel").inner_text() if page.locator(".error-panel").count() else ""
    assert status.get_attribute("data-status") == "AWAITING_USER_REVIEW", error
    report_link = page.locator("a.artifact-link").filter(has_text="quality_report.json")
    report = page.request.get(report_link.get_attribute("href")).json()
    assert report["compile"]["status"] == "PASS"
    assert report["layout"]["evidence"]["all_rendered"] is True
    expected_pages = report["layout"]["evidence"]["page_count"]
    assert expected_pages > 0
    assert page.locator(".page-review").count() == expected_pages
    for image in page.locator(".page-review img").all():
        png = page.request.get(image.get_attribute("src"))
        assert png.status == 200 and png.body().startswith(b"\x89PNG\r\n\x1a\n")
    pdf_link = page.locator("a.artifact-link").filter(has_text="application/pdf")
    pdf = page.request.get(pdf_link.get_attribute("href"))
    assert pdf.status == 200 and pdf.body().startswith(b"%PDF-")
    bundle_link = page.locator("a.artifact-link").filter(has_text="source_bundle.zip")
    bundle = page.request.get(bundle_link.get_attribute("href"))
    assert bundle.status == 200
    with zipfile.ZipFile(io.BytesIO(bundle.body())) as archive:
        names = archive.namelist()
        assert any(name.endswith(".tex") for name in names)
        assert not any(".env" in name or name.endswith("agent.db") for name in names)
        source = "\n".join(archive.read(name).decode("utf-8") for name in names if name.endswith(".tex"))
    return report, source


def test_lecture_real_clicks_restore_confirmation(browser_page, local_services):
    page = browser_page
    expect(page.locator("#provider option[value=live]")).to_contain_text("未配置或未启用")
    page.locator("#provider").select_option("live")
    expect(page.locator("#provider-disclosure")).to_contain_text("当前真实 API 未配置或未启用")
    page.screenshot(path=str(local_services[1] / "live-unconfigured.png"), full_page=True)
    page.locator("#provider").select_option("mock")
    page.locator("#topic").fill("数列极限")
    page.locator("#difficulty").fill("经济学本科一年级微积分")
    assert not page.locator("#trusted-input").is_checked()
    page.locator("#trusted-input").check()
    page.locator("#create-run").click()
    wait_for_plan(page)
    assert page.locator("[data-question-id]").count() > 0
    for question in page.locator("[data-question-id]").all():
        assert question.locator(".choice input").last.get_attribute("value") == "CUSTOM"
        assert question.locator(".choice input:checked").count() == 0
    submit_recommended(page)
    page.get_by_text("本次计划变更（diff）", exact=True).wait_for()
    page.locator("#outline-editor > summary").click()
    page.locator("#outline-title").fill("数列极限 · 本科教学讲义")
    page.locator("#save-outline").click()
    page.get_by_role("heading", name="数列极限 · 本科教学讲义", exact=True).wait_for()
    confirm_execute_refresh(page)
    assert "MOCK" in page.locator("main").inner_text()
    _, source = accepted_compile_artifacts(page)
    assert "数列极限" in source


def test_beamer_exact_deletion_and_addition(browser_page, tmp_path):
    page = browser_page
    source = tmp_path / "中文 路径(样例).tex"
    source.write_text(r"""\documentclass{ctexart}
\usepackage{amsmath,amssymb,amsthm}
\newtheorem{definition}{定义}
\newtheorem{example}{例}
\begin{document}
\section{数列极限}
\begin{definition}若对任意 $\varepsilon>0$，存在 $N$，当 $n>N$ 时 $|a_n-a|<\varepsilon$，则称 $a_n$ 收敛于 $a$。\end{definition}
\begin{example}例 3：求 $\lim_{n\to\infty} 1/n$。\end{example}
\textbf{解：}由数列极限的定义，极限为 $0$。
\section{极限运算}
若 $a_n\to a$ 且 $b_n\to b$，则 $a_n+b_n\to a+b$。
\end{document}
""", encoding="utf-8")
    page.locator("#workflow").select_option("beamer.from_tex")
    assert page.locator("#theme option[value=fduclassroom]").count() == 1
    use_fdu = page.locator("#theme option[value=fduclassroom]").is_enabled()
    if use_fdu:
        page.locator("#theme").select_option("fduclassroom")
    page.locator("#source-file").set_input_files(str(source))
    page.locator("#trusted-input").check()
    page.locator("#create-run").click()
    wait_for_plan(page)
    if use_fdu:
        adaptations = page.locator('section[aria-label="模板适配说明"]')
        expect(adaptations).to_be_visible()
        expect(adaptations).to_contain_text("页眉只显示当前一级章节")
        expect(adaptations).to_contain_text("完整三态目录保留全部一级章节")
    if page.locator("#use-recommended").count():
        page.locator("#use-recommended").click()
    page.get_by_text("删除或调整原讲义内容", exact=True).click()
    example = page.locator(".unit").filter(has_text="例 3").first
    example.locator("input[type=checkbox]").check()
    deleted_id = example.locator("input").get_attribute("value")
    page.get_by_text("添加原讲义之外的内容", exact=True).click()
    page.locator("#add-content").click()
    page.get_by_label("新增内容", exact=True).fill("补充例题：求常数数列的极限。")
    page.get_by_label("插入位置", exact=True).select_option("S01")
    page.locator("#save-decisions").click()
    expect(page.locator("#confirm-plan")).to_be_enabled()
    assert deleted_id in page.locator("main").inner_text()
    page.get_by_text("删除授权与依赖影响", exact=True).wait_for()
    assert "补充例题" in page.locator("main").inner_text()
    confirm_execute_refresh(page)
    if use_fdu:
        expect(page.locator('section[aria-label="模板适配说明"]')).to_be_visible()
    report, generated = accepted_compile_artifacts(page)
    assert report["fidelity"]["status"] == "PASS"
    if use_fdu:
        assert r"\usetheme{fduclassroom}" in generated
    assert "补充例题：求常数数列的极限。" in generated
    assert "例 3：求" not in generated


def test_custom_input_is_saved_as_plan_effect(browser_page):
    page = browser_page
    page.locator("#topic").fill("无穷级数")
    page.locator("#trusted-input").check()
    page.locator("#create-run").click()
    wait_for_plan(page)
    page.locator("#use-recommended").click()
    question = page.locator("[data-question-id]").first
    question.locator("input[value=CUSTOM]").check()
    custom_text = "关键定理提供完整证明，并明确全部先修条件。"
    question.locator("textarea").fill(custom_text)
    page.locator("#save-decisions").click()
    page.get_by_text("本次计划变更（diff）", exact=True).wait_for()
    expect(page.locator("main")).to_contain_text(custom_text)
    page.reload()
    page.get_by_text("本次计划变更（diff）", exact=True).wait_for()
    expect(page.locator("main")).to_contain_text(custom_text)


def test_compile_failure_retry_does_not_return_to_confirmation(browser_page, tmp_path):
    page = browser_page
    source = tmp_path / "失败恢复(合成).tex"
    source.write_text(r"""\documentclass{ctexart}
\usepackage{amsmath,amsthm}
\newtheorem{definition}{定义}
\begin{document}
\section{编译失败回归}
\begin{definition}数列是以正整数为定义域的函数。\end{definition}
\undefinedMathAgentFailure
\end{document}
""", encoding="utf-8")
    page.locator("#workflow").select_option("beamer.from_tex")
    page.locator("#source-file").set_input_files(str(source))
    page.locator("#trusted-input").check()
    page.locator("#create-run").click()
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    page.locator("#retry-run").wait_for(timeout=120_000)
    assert page.locator("#confirm-plan").count() == 0
    assert page.locator(".error-panel").count() == 1
    report_link = page.locator("a.artifact-link").filter(has_text="quality_report.json")
    report_link.wait_for()
    report = page.request.get(report_link.get_attribute("href")).json()
    assert report["compile"]["status"] == "FAIL"
    assert any(issue["rule_id"] == "UNDEFINED_CONTROL_SEQUENCE" for issue in report["compile"]["issues"])
    expect(page.locator(".error-panel")).to_contain_text("QUALITY_BLOCKED")
    expect(page.locator(".error-panel")).to_contain_text("UNDEFINED_CONTROL_SEQUENCE")
    expect(page.locator(".error-panel")).to_contain_text("Undefined control sequence")
    page.reload()
    page.locator("#retry-run").wait_for()
    with page.expect_response(lambda response: response.url.endswith("/retry") and response.request.method == "POST") as retried:
        page.locator("#retry-run").click()
    assert retried.value.status == 202
    page.reload()
    page.locator("#run-stage").wait_for()
    assert page.locator("#confirm-plan").count() == 0
    assert page.locator("#decisions-form").count() == 0


def test_uploaded_article_fonts_lists_and_nested_proof_compile(browser_page, tmp_path):
    page = browser_page
    source = tmp_path/'图中文字与长证明.tex'
    source.write_text(r'''\documentclass{ctexart}
\newenvironment{extra}{\par\textbf{选读}}{\par}
\begin{document}\section{微分}
\begin{center}\begin{tikzpicture}
\node at (0,0) {\scriptsize $\Delta y-\mathrm{d}y$};
\end{tikzpicture}\end{center}
\begin{itemize}[leftmargin=2em]\item 成本 $C(x)$。\item 收入 $R(x)$。\end{itemize}
\begin{extra}\begin{proofdetail}
''' + ('完整推导步骤。'+r'\[a+b=c\]'+'\n\n')*12+
        r'\end{proofdetail}\end{extra}\end{document}', encoding='utf-8')
    original = source.read_bytes()
    page.locator('#workflow').select_option('beamer.from_tex')
    page.locator('#source-file').set_input_files(str(source))
    page.locator('#trusted-input').check()
    page.locator('#create-run').click()
    wait_for_plan(page)
    submit_recommended(page)
    confirm_execute_refresh(page)
    report, generated = accepted_compile_artifacts(page)
    assert report['fidelity']['status'] == 'PASS'
    assert r'\scriptsize' not in generated
    assert r'\footnotesize $\Delta y-\mathrm{d}y$' in generated
    assert '[leftmargin=2em]' not in generated
    assert generated.count(r'\[a+b=c\]') == 12
    assert source.read_bytes() == original
    audit = page.locator('a.artifact-link').filter(has_text='presentation_adaptations.json')
    assert page.request.get(audit.get_attribute('href')).status == 200


def test_reference_bibliography_opt_in_preserves_sources(browser_page, local_services, tmp_path):
    page = browser_page
    manuscript = PROJECT.parent / "大学数学（一）(1).tex"
    if not manuscript.is_file():
        pytest.skip("The local complete manuscript is required for provenance-backed bibliography E2E")
    manuscript_bytes = manuscript.read_bytes()
    manuscript_text = manuscript_bytes.decode("utf-8-sig")
    manuscript_hash = hashlib.sha256(manuscript_bytes).hexdigest()
    source = tmp_path / "书目回归.tex"
    source_bytes = r"""\documentclass{ctexart}
\usepackage{amsmath,amssymb,amsthm}
\newtheorem{definition}{定义}
\begin{document}
\section{引用来源核对}
\begin{definition}函数是两个集合之间满足唯一对应条件的映射。\end{definition}
土壤性质的背景材料见文献\cite{BradyWeil}。
\end{document}
""".encode("utf-8")
    source.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    page.locator("#workflow").select_option("beamer.from_tex")
    bibliography = page.locator("#reference-bibliography")
    expect(bibliography).to_be_enabled()
    assert not bibliography.is_checked()
    bibliography.check()
    page.locator("#provider").select_option("mock")
    page.locator("#source-file").set_input_files(str(source))
    page.locator("#trusted-input").check()
    with page.expect_response(lambda response: response.url.endswith("/api/runs") and response.request.method == "POST") as created:
        page.locator("#create-run").click()
    assert created.value.status == 201
    run_id = created.value.json()["id"]
    wait_for_plan(page)
    run = page.request.get(f"/api/runs/{run_id}").json()
    payload = run["input"]
    enrichment = run["plan"]["source_enrichment"]
    assert payload["provider"] == "mock" and payload["use_reference_bibliography"] is True
    assert enrichment == payload["source_enrichment"]
    assert enrichment["added_keys"] == ["BradyWeil"]
    assert enrichment["unresolved_keys"] == [] and enrichment["conflicting_keys"] == []
    assert enrichment["original_upload_sha256"] == source_hash
    assert enrichment["manuscript_bytes_sha256"] == manuscript_hash
    assert enrichment["manuscript_text_sha256"] == hashlib.sha256(manuscript_text.encode("utf-8")).hexdigest()
    assert enrichment["authorization"] == "explicit_input_option_pending_plan_confirmation"
    entry = enrichment["entries"][0]
    assert entry["key"] == "BradyWeil" and entry["source_file"] == manuscript.name
    assert entry["raw_tex"] == manuscript_text[entry["start"]:entry["end"]]
    assert "The Nature and Properties of Soils" in entry["raw_tex"]
    assert entry["sha256"] == hashlib.sha256(entry["raw_tex"].encode("utf-8")).hexdigest()
    assert payload["source_key"] != payload["original_source_key"]
    runtime = Path(json.loads((local_services[1] / "context.json").read_text(encoding="utf-8"))["workspace"]) / "w"
    original_snapshot = runtime / payload["original_source_key"] / payload["main_file"]
    original_upload = runtime / payload["original_upload_key"]
    prepared_source = runtime / payload["source_key"] / payload["main_file"]
    assert original_snapshot.read_bytes() == source_bytes
    assert original_upload.read_bytes() == source_bytes
    # Universal newline reading is appropriate for the generated text; the exact
    # input and manuscript byte hashes are verified independently above/below.
    assert entry["raw_tex"].replace("\r\n", "\n") in prepared_source.read_text(encoding="utf-8")
    provenance = page.locator("details").filter(has=page.locator("summary").filter(has_text="从完整原稿补齐的书目与出处（本次确认范围）"))
    expect(provenance).to_have_attribute("open", "")
    for visible_value in ["BradyWeil", manuscript.name, source_hash, manuscript_hash, entry["sha256"], "The Nature and Properties of Soils"]:
        expect(provenance).to_contain_text(visible_value)
    page.screenshot(path=str(local_services[1] / "bibliography-plan.png"), full_page=True)
    previous_plan_hash = run["plan"]["hash"]
    page.reload()
    wait_for_plan(page)
    expect(provenance).to_be_visible()
    restored = page.request.get(f"/api/runs/{run_id}").json()
    assert restored["plan"]["hash"] == previous_plan_hash
    assert restored["input"]["use_reference_bibliography"] is True
    assert restored["plan"]["source_enrichment"] == enrichment
    submit_recommended(page)
    confirm_execute_refresh(page)
    report, generated = accepted_compile_artifacts(page)
    assert report["fidelity"]["status"] == "PASS"
    assert r"\cite{BradyWeil}" in generated
    # The Windows renderer may translate the trailing line break while writing
    # generated TeX. The bibliographic body itself must remain byte-for-byte text.
    assert entry["raw_tex"].rstrip("\r\n") in generated
    assert not any("UNRESOLVED" in issue.get("rule_id", "") for issue in report["compile"].get("issues", []))
    completed = page.request.get(f"/api/runs/{run_id}").json()
    assert completed["status"] == "AWAITING_USER_REVIEW" and completed["reviews"] == []
    plan_artifact = next(artifact for artifact in completed["artifacts"] if artifact["name"] == "plan.json")
    delivered_plan = page.request.get(f"/api/artifacts/{plan_artifact['artifact_id']}").json()
    assert delivered_plan["source_enrichment"] == enrichment
    assert original_snapshot.read_bytes() == original_upload.read_bytes() == source.read_bytes() == source_bytes
    assert hashlib.sha256(manuscript.read_bytes()).hexdigest() == manuscript_hash
    (local_services[1] / "bibliography-verification.json").write_text(json.dumps({
        "run_id": run_id, "provider": "mock", "status": completed["status"],
        "source_upload_sha256": source_hash, "manuscript_bytes_sha256": manuscript_hash,
        "entry_sha256": entry["sha256"], "added_keys": enrichment["added_keys"],
        "source_file": manuscript.name, "source_lines": [entry["start_line"], entry["end_line"]],
        "originals_unchanged": True, "refresh_preserved": True,
        "compile": report["compile"]["status"], "fidelity": report["fidelity"]["status"],
        "physical_pages": report["layout"]["evidence"]["page_count"],
        "all_page_pngs_downloaded": True, "pdf_downloaded": True, "source_zip_downloaded": True,
        "teacher_visual_review": "NOT_RUN", "real_api": "NOT_RUN",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
