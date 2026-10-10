"""Read-only Edge checks of the three-model UI on an already running service.

No POST, model call, task creation, retry, budget change or review is permitted.
This checks configured profiles and their presentation, not API availability.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import traceback
from urllib.parse import urlparse
import uuid

from verify_live_delivery_ui import edge_executable, require, sha256


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "reports" / "iteration3"
MODELS = ["gpt6", "deepseek-flash", "deepseek-v4-pro"]


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        parser.error("Use a localhost HTTP origin only")
    output = (args.output or REPORTS / ("model-selection-readonly-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])).resolve()
    if not output.is_relative_to(REPORTS.resolve()) or output == REPORTS.resolve():
        parser.error("Output must be a new child directory of reports/iteration3")
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "IN_PROGRESS", "base_url": base, "started_at": datetime.now(timezone.utc).isoformat(),
              "real_api": "NOT_RUN", "windows_compile": "NOT_RUN", "teacher_review": "NOT_RUN",
              "mutations": "FORBIDDEN", "checks": [], "network": [], "page_errors": [], "blocked_requests": []}
    executable = edge_executable()
    result["browser"] = executable
    result["source_sha256"] = {name: sha256((PROJECT / "src" / "math_agent" / "web" / "static" / name).read_bytes()) for name in ("app.js", "style.css", "index.html")}
    try:
        require(executable, "Microsoft Edge not found")
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as manager:
            browser = manager.chromium.launch(headless=True, executable_path=executable,
                env={key: value for key, value in os.environ.items() if not key.startswith("MATH_AGENT_") and key != "OPENAI_API_KEY"})
            try:
                for label, viewport in [("desktop", {"width": 1440, "height": 1100}), ("mobile", {"width": 390, "height": 844})]:
                    context = browser.new_context(base_url=base, viewport=viewport, locale="zh-CN", service_workers="block")
                    def guard(route):
                        req = route.request
                        if req.method == "GET" and req.url.startswith(base + "/"):
                            route.continue_()
                        else:
                            result["blocked_requests"].append({"method": req.method, "url": req.url})
                            route.abort("blockedbyclient")
                    context.route("**/*", guard)
                    page = context.new_page()
                    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
                    page.on("response", lambda response: result["network"].append({"method": response.request.method, "url": response.url, "http_status": response.status}))
                    page.goto(base, wait_until="domcontentloaded")
                    page.locator("#new-run-form").wait_for()
                    caps = context.request.get(base + "/api/capabilities").json()
                    models = caps["settings"]["models"]
                    require([model["id"] for model in models] == MODELS, "Backend model registry differs")
                    require(page.locator("#model-id option").evaluate_all("nodes => nodes.map(n => n.value)") == MODELS, "Dropdown model IDs differ")
                    expect(page.locator("#model-id")).to_have_value("gpt6")
                    expected_provider = "live" if any(model["configured"] for model in models) else "mock"
                    expect(page.locator("#provider")).to_have_value(expected_provider)
                    require(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Page has horizontal overflow")
                    page.screenshot(path=str(output / (label + "-default.png")), full_page=True)
                    # Selecting a dropdown changes only local presentation.
                    page.locator("#provider").select_option("live")
                    for model_id in MODELS:
                        page.locator("#model-id").select_option(model_id)
                        order = [model_id] + [item for item in MODELS if item != model_id]
                        expect(page.locator("#model-selection-help")).to_contain_text(" → ".join(order))
                    page.locator("#model-id").select_option("gpt6")
                    page.locator("#model-id").scroll_into_view_if_needed()
                    page.screenshot(path=str(output / (label + "-model-choice.png")), full_page=False)
                    result["checks"].append({"viewport": label, "default_model": "gpt6", "default_provider": expected_provider,
                        "model_ids": MODELS, "configured": {item["id"]: item["configured"] for item in models},
                        "fallback_help_for_all_choices": "PASS", "horizontal_overflow": False})
                    context.close()
            finally:
                browser.close()
        require(not result["page_errors"], "Browser JavaScript errors occurred")
        require(not result["blocked_requests"], "Browser attempted a forbidden request")
        require(all(row["method"] == "GET" for row in result["network"]), "Non-read-only request occurred")
        result["status"] = "PASS"
    except Exception as error:
        result.update(status="FAIL", error={"type": type(error).__name__, "message": str(error)[:4000]})
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_json(output / "report.json", result)
    print(json.dumps({"status": result["status"], "output": str(output), "model_calls": "NOT_RUN"}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
