"""Real Edge + local API/SQLite/worker/provider; synthetic HTTP responses only.

No external model call, teacher review, or TeX compilation is performed here.
The live code path is exercised with httpx.MockTransport and dummy credentials.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn

from math_agent.domain import LectureProposal
from math_agent.provider import CompatibleChatProvider, MockProvider
from math_agent.settings import Settings
from math_agent.web.app import create_app
from math_agent.worker import Worker
from test_browser_workflows import browser_executable, expect


pytestmark = pytest.mark.e2e
PROJECT = Path(__file__).resolve().parents[2]
MODELS = ("gpt6", "deepseek-flash", "deepseek-v4-pro")
PROVIDER_NAMES = {"gpt6": "gpt-6-astra", "deepseek-flash": "deepseek-flash", "deepseek-v4-pro": "deepseek-v4-pro"}


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def model_ui(tmp_path, monkeypatch, request):
    # Do not inherit any configured real credential, endpoint, or workspace.
    for name in list(os.environ):
        if name.startswith("MATH_AGENT_") or name == "OPENAI_API_KEY":
            monkeypatch.delenv(name)
    evidence_root = PROJECT / "reports" / "iteration3" / "model-selection-e2e"
    evidence = evidence_root / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    evidence.mkdir(parents=True, exist_ok=False)
    settings = Settings(workspace=tmp_path / "w", reference_root=PROJECT.parent,
                        api_key="dummy-gpt-browser-fixture", deepseek_api_key="dummy-deepseek-browser-fixture",
                        live_api_enabled=True, llm_streaming=False,
                        max_network_retries=0, max_schema_repair_attempts=0)
    state = {"status_by_model": {}, "requests": [], "checks": [], "test_name": request.node.name}
    proposal = MockProvider().generate("planner_lecture", {"topic": "模型路由浏览器合成测试"}, LectureProposal)

    def handle_http(incoming):
        body = json.loads(incoming.content)
        model = body["model"]
        code = state["status_by_model"].get(model, 200)
        state["requests"].append({"model": model, "http_status": code, "url": str(incoming.url),
                                  "stream": body.get("stream", False), "thinking": body.get("thinking"),
                                  "reasoning_effort": body.get("reasoning_effort")})
        if code != 200:
            return httpx.Response(code, json={"error": {"message": "SYNTHETIC gateway unavailable"}})
        return httpx.Response(200, json={"id": "synthetic-browser-model-test", "model": model,
            "choices": [{"message": {"role": "assistant", "content": json.dumps(proposal, ensure_ascii=False)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}})

    def provider_factory(*args, **kwargs):
        return CompatibleChatProvider(*args, **kwargs, transport=httpx.MockTransport(handle_http))

    monkeypatch.setattr("math_agent.pipeline.CompatibleChatProvider", provider_factory)
    app = create_app(settings)
    worker = Worker(settings)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started, "Isolated browser server failed to start"
    playwright = pytest.importorskip("playwright.sync_api")
    errors, forbidden = [], []
    executable = browser_executable()
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch(headless=True, executable_path=executable,
            env={key: value for key, value in os.environ.items() if not key.startswith("MATH_AGENT_") and key != "OPENAI_API_KEY"})
        context = browser.new_context(base_url=base, viewport={"width": 1440, "height": 1100}, locale="zh-CN", service_workers="block")
        def local_only(route):
            if route.request.url.startswith(base + "/"):
                route.continue_()
            else:
                forbidden.append(route.request.url)
                route.abort("blockedbyclient")
        context.route("**/*", local_only)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base)
            page.locator("#new-run-form").wait_for()
            state.update(page=page, worker=worker, app=app, settings=settings, evidence=evidence)
            yield state
        finally:
            try:
                page.screenshot(path=str(evidence / "final.png"), full_page=True)
                context.tracing.stop(path=str(evidence / "trace.zip"))
            finally:
                save_json(evidence / "evidence.json", {key: state[key] for key in ("test_name", "checks", "requests") } | {
                    "model_http_transport": "MOCK_TRANSPORT", "browser": executable,
                    "local_api_sqlite_worker": "ACTUAL", "real_api": "NOT_RUN", "windows_compile": "NOT_RUN",
                    "teacher_review": "NOT_RUN", "javascript_errors": errors, "external_browser_requests_blocked": forbidden})
                browser.close()
                server.should_exit = True
                thread.join(timeout=10)
    assert not errors, errors
    assert not forbidden, forbidden


def create_and_plan(fixture, model_id, select=True):
    page = fixture["page"]
    if select:
        page.locator("#model-id").select_option(model_id)
    page.locator("#topic").fill("模型选择与故障切换：" + model_id)
    page.locator("#trusted-input").check()
    with page.expect_response(lambda response: response.url.endswith("/api/runs") and response.request.method == "POST") as response:
        page.locator("#create-run").click()
    assert response.value.status == 201
    created = response.value.json()
    assert created["input"]["model_id"] == model_id
    page.locator("#preferred-model").wait_for()
    # Playwright's sync bridge owns an asyncio loop in the test thread. The
    # production worker is a separate process; use a separate thread here too.
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(fixture["worker"].tick).result(timeout=60)
    page.reload()
    page.locator("#decisions-form").wait_for(timeout=30000)
    run = page.request.get("/api/runs/" + created["id"]).json()
    assert run["status"] == "AWAITING_PLAN_INPUT", run.get("error")
    assert run["input"]["model_id"] == run["plan"]["model_id"] == model_id
    assert run["reviews"] == [] and run["approval"] is None
    save_json(fixture["evidence"] / "run.json", run)
    save_json(fixture["evidence"] / "events.json", page.request.get("/api/runs/" + created["id"] + "/events").json())
    return run


@pytest.mark.parametrize("model_id", MODELS)
def test_three_models_submit_and_restore_actual_selection(model_ui, model_id):
    page = model_ui["page"]
    expect(page.locator("#provider")).to_have_value("live")
    expect(page.locator("#model-id")).to_have_value("gpt6")
    assert page.locator("#model-id option").evaluate_all("nodes => nodes.map(node => node.value)") == list(MODELS)
    expect(page.locator("#model-selection-help")).to_contain_text("即时可用性以实际请求为准")
    page.screenshot(path=str(model_ui["evidence"] / "new-run-default.png"), full_page=True)
    # gpt6 verifies that submitting without touching the model control uses gpt6.
    run = create_and_plan(model_ui, model_id, select=model_id != "gpt6")
    assert [item["model"] for item in model_ui["requests"]] == [PROVIDER_NAMES[model_id]]
    if model_id.startswith("deepseek-"):
        assert model_ui["requests"][0]["thinking"] == {"type": "enabled"}
        assert model_ui["requests"][0]["reasoning_effort"] == "high"
        assert model_ui["requests"][0]["stream"] is False
    assert run["model_routing"]["last_model_id"] == model_id
    expect(page.locator("#preferred-model")).to_have_text(model_id)
    expect(page.locator("#last-model")).to_have_text(model_id)
    expect(page.locator("#last-successful-model")).to_have_text(model_id)
    expect(page.locator("#model-fallback-count")).to_have_text("0 次")
    page.reload()
    expect(page.locator("#preferred-model")).to_have_text(model_id)
    expect(page.locator("#last-model")).to_have_text(model_id)
    model_ui["checks"].append({"default_model": "gpt6", "submitted_model": model_id,
        "preferred_and_actual_restored": True, "request_count": run["request_count"]})


def test_http_504_then_503_automatically_reaches_third_model(model_ui):
    model_ui["status_by_model"] = {"gpt-6-astra": 504, "deepseek-flash": 503}
    run = create_and_plan(model_ui, "gpt6", select=False)
    page = model_ui["page"]
    assert [(item["model"], item["http_status"]) for item in model_ui["requests"]] == [
        ("gpt-6-astra", 504), ("deepseek-flash", 503), ("deepseek-v4-pro", 200)]
    routing = run["model_routing"]
    assert routing["preferred_model_id"] == "gpt6"
    assert routing["used_models"] == list(MODELS)
    assert routing["last_model_id"] == routing["last_successful_model_id"] == "deepseek-v4-pro"
    assert routing["fallback_count"] == 2 and run["request_count"] == 3
    expect(page.locator("#preferred-model")).to_have_text("gpt6")
    expect(page.locator("#last-model")).to_have_text("deepseek-v4-pro")
    expect(page.locator("#last-successful-model")).to_have_text("deepseek-v4-pro")
    expect(page.locator("#model-fallback-count")).to_have_text("2 次")
    expect(page.locator("#model-fallback-events li")).to_have_count(2)
    expect(page.locator("#model-fallback-events")).to_contain_text("gpt6 → deepseek-flash")
    expect(page.locator("#model-fallback-events")).to_contain_text("deepseek-flash → deepseek-v4-pro")
    assert page.locator("#model-routing").evaluate("element => element.scrollWidth <= element.clientWidth")
    page.locator("#model-routing").screenshot(path=str(model_ui["evidence"] / "automatic-fallback.png"))
    page.reload()
    expect(page.locator("#model-fallback-events li")).to_have_count(2)
    expect(page.locator("#last-model")).to_have_text("deepseek-v4-pro")
    model_ui["checks"].append({"synthetic_http_statuses": [504, 503, 200], "automatic_fallback_count": 2,
        "preferred_model_preserved": True, "failed_attempts_counted": True, "refresh_restored_events": True})


def test_mock_mode_does_not_call_selected_real_model(model_ui):
    page = model_ui["page"]
    page.locator("#provider").select_option("mock")
    expect(page.locator("#model-id")).to_be_disabled()
    run = create_and_plan(model_ui, "gpt6", select=False)
    assert run["input"]["provider"] == "mock" and model_ui["requests"] == []
    expect(page.locator("#last-model")).to_have_text("MOCK · 未调用真实模型")
    assert page.locator("#model-fallback-events").count() == 0
    model_ui["checks"].append({"mock_mode": True, "model_http_requests": 0})
