"""Browser end-to-end checks for the viz dashboard (optional harness).

Runs only when Playwright is installed (``pip install playwright`` +
``playwright install chromium``); otherwise the whole module skips —
Playwright is deliberately NOT a project dependency. It drives the real
rendered dashboard in a headless browser and asserts the keyboard / ARIA
behaviour the unit suite can only pin structurally.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cataforge.application.viz import html
from tests.cli.test_viz_cmd import _make_dashboard_project

pytestmark = pytest.mark.slow


@pytest.fixture
def dashboard_page(tmp_path: Path) -> Iterator[Any]:
    pw = pytest.importorskip("playwright.sync_api")
    _make_dashboard_project(tmp_path)
    out = tmp_path / "index.html"
    out.write_text(html.render_dashboard(tmp_path), encoding="utf-8")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # playwright installed but no browser binaries
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(out.as_uri())
        yield page
        browser.close()


class TestDashboardBrowser:
    def test_landmarks_and_roving_tabindex(self, dashboard_page: Any) -> None:
        page = dashboard_page
        assert page.locator("h1").count() == 1
        assert page.locator("main").count() == 1
        lists = page.locator('[role="tablist"]')
        assert lists.count() == 3
        for i in range(lists.count()):
            # roving tabindex: exactly one tabbable entry point per tablist
            assert lists.nth(i).locator('[role="tab"][tabindex="0"]').count() == 1

    def test_arrow_key_moves_tab_focus(self, dashboard_page: Any) -> None:
        page = dashboard_page
        first = page.locator('[role="tablist"]').first.locator('[role="tab"]').first
        first.focus()
        page.keyboard.press("ArrowRight")
        focused = page.evaluate("document.activeElement.id")
        assert focused and focused != first.get_attribute("id")

    def test_omnibox_combobox_keyboard_selection(self, dashboard_page: Any) -> None:
        page = dashboard_page
        omni = page.locator("#omni")
        omni.fill("research")  # the framework graph seeds the entity index
        page.wait_for_timeout(300)  # input debounce
        assert omni.get_attribute("aria-expanded") == "true"
        page.keyboard.press("ArrowDown")
        assert omni.get_attribute("aria-activedescendant") == "omni_opt_0"
        page.keyboard.press("Enter")
        assert page.locator(".panel.active").count() == 1

    def test_inspector_focus_cycle(self, dashboard_page: Any) -> None:
        page = dashboard_page
        page.evaluate("window.__viz.inspect({id:'x',label:'X'},null)")
        assert page.evaluate("document.activeElement.id") == "inspector"
        page.keyboard.press("Escape")
        assert page.evaluate("document.getElementById('inspector').hidden") is True

    def test_narrow_viewport_no_horizontal_overflow(self, dashboard_page: Any) -> None:
        page = dashboard_page
        page.set_viewport_size({"width": 320, "height": 800})
        assert page.evaluate("document.documentElement.scrollWidth") <= 320
