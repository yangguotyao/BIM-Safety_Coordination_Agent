#!/usr/bin/env python3
"""Browser-level verification for the BIM Safety Coordination demo.

Requires:
  pip install playwright
  a local Chrome/Chromium (CHROME_PATH or Playwright channel="chrome")

Usage:
  python ui_playwright.py
  RESET=1 python ui_playwright.py   # reset runtime fixtures first
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000")
CHROME = os.getenv("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    errors: list[str] = []
    checks: list[str] = []
    with sync_playwright() as p:
        if Path(CHROME).exists():
            browser = p.chromium.launch(
                executable_path=CHROME,
                headless=True,
                args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"],
            )
        else:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader"],
            )
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))

        def visit(path: str, wait: int = 1200) -> None:
            page.goto(BASE + path, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(wait)

        def status() -> str:
            return page.locator(".title-row .badge").first.inner_text().strip()

        def wait_status(label: str, timeout: int = 25) -> None:
            for _ in range(timeout * 2):
                if page.locator(".title-row .badge", has_text=label).count():
                    return
                page.wait_for_timeout(500)
            raise AssertionError(f"等待状态 {label} 超时；当前 {page.locator('.title-row').inner_text()[:200]}")

        if os.getenv("RESET") == "1":
            page.request.post(BASE + "/api/demo/reset")
            checks.append("reset runtime fixtures")

        visit("/")
        assert "Safety Case" in page.locator("h1").first.inner_text()
        checks.append("dashboard renders")
        page.screenshot(path=str(OUT / "ui-dashboard.png"))

        visit("/bim", 3500)
        assert page.locator("canvas").count() == 1
        assert page.locator("text=三维视图不可用").count() == 0
        canvas = page.locator("canvas").first
        box = canvas.bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55)
            page.wait_for_timeout(700)
        assert page.locator(".guid-line").count() == 1
        checks.append("3D canvas + WebGL + element inspector")
        page.screenshot(path=str(OUT / "ui-bim.png"))

        visit("/cases")
        page.get_by_role("button", name="新建案例").click()
        page.wait_for_timeout(400)
        page.locator(".modal input.input").first.fill("UI 验收自动化案例")
        page.get_by_role("button", name="创建并分析").click()
        page.wait_for_url("**/cases/CASE-*", timeout=20000)
        wait_status("待审核")
        checks.append("create case + real LangGraph analysis")
        page.screenshot(path=str(OUT / "ui-case-review.png"))

        page.locator(".tab", has_text="审核与措施").click()
        page.wait_for_timeout(400)
        page.get_by_role("button", name="批准控制措施").click()
        wait_status("已批准")
        checks.append("human approve")

        page.locator(".tab", has_text="实施与复核").click()
        page.wait_for_timeout(400)
        page.get_by_role("button", name="记录实施并进入整改").click()
        wait_status("整改中")
        checks.append("implementation record")

        page.get_by_role("button", name="补交证据").click()
        page.wait_for_timeout(400)
        page.locator(".add-evidence", has_text="EV-010").first.click()
        page.get_by_role("button", name="追加所选证据").click()
        wait_status("待复核")
        checks.append("after evidence")

        page.locator(".tab", has_text="实施与复核").click()
        page.wait_for_timeout(500)
        page.locator(".verify-evidence", has_text="EV-010").first.click()
        page.get_by_role("button", name="执行复核").click()
        wait_status("已关闭")
        assert "案例已关闭" in page.locator(".verify-head").inner_text()
        checks.append("verification pass -> closed")
        page.screenshot(path=str(OUT / "ui-case-closed.png"))

        page.locator(".tab", has_text="实施与复核").click()
        page.wait_for_timeout(500)
        page.locator(".reopen-box").scroll_into_view_if_needed()
        page.locator(".reopen-box .verify-evidence", has_text="EV-011").first.click()
        page.get_by_role("button", name="保留历史并重新打开").click()
        wait_status("已重开")
        checks.append("closed -> reopened with history")
        page.screenshot(path=str(OUT / "ui-case-reopened.png"))

        page.locator(".tab", has_text="事件").click()
        page.wait_for_timeout(300)
        events = page.locator(".timeline-top strong").all_inner_texts()
        assert "复核通过" in events and "重新打开案例" in events
        checks.append("event history retained")

        visit("/acceptance")
        assert page.locator(".test-card").count() == 12
        checks.append("12 acceptance cards")
        page.screenshot(path=str(OUT / "ui-acceptance.png"))

        visit("/knowledge")
        assert page.locator(".rule-item").count() >= 7
        checks.append("knowledge base")
        visit("/evidence")
        assert page.locator(".evidence-card").count() == 12
        checks.append("evidence gallery")
        visit("/agent")
        assert page.locator(".trace-row").count() >= 8
        checks.append("agent trace")
        page.screenshot(path=str(OUT / "ui-agent.png"))

        assert not errors, errors
        browser.close()

    print(json.dumps({"ok": True, "checks": checks, "errors": errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
