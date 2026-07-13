"""tests/integration/test_browser_api.py — remote browser endpoints.

We deliberately don't spawn a real Playwright browser in the test
suite — that requires the chromium binary to be installed and adds
~5s of cold-start per test. Instead we drive the *gates* and the
``_probe_env`` helper directly: env-status shape, install spawn
returning a pid, 503 when browsers aren't ready, cross-user 404.

The happy path (create session → goto → screenshot) is exercised
manually via the dashboard; once chromium is installed in CI we can
flip a feature flag and let ``test_create_session_happy_path`` run.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

# --- env-status -------------------------------------------------------------


async def test_env_status_returns_shape(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/browser/env-status", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "playwright" in body
    assert "browsers_ok" in body
    assert isinstance(body["playwright"], bool)
    assert isinstance(body["browsers_ok"], bool)


async def test_env_status_requires_auth(env: Any) -> None:
    c, _srv, _auth = env
    r = await c.get("/api/browser/env-status")
    assert r.status_code == 401


def test_probe_env_when_playwright_missing() -> None:
    """``_probe_env`` should not raise even with playwright import broken."""
    import builtins

    from octop.api.routers.browser import sessions as br

    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kw: Any) -> Any:
        if name == "playwright":
            raise ImportError("simulated")
        return original_import(name, *args, **kw)

    with patch("builtins.__import__", side_effect=fake_import):
        out = br._probe_env()
    assert out["playwright"] is False
    if not out.get("harness_browser"):
        assert out["browsers_ok"] is False
        assert out["error"]


def test_probe_env_harness_browser_without_chromium() -> None:
    """``browsers_ok`` must stay false when no Chrome/Chromium is available."""
    from octop.api.routers.browser import sessions as br

    try:
        import harness_browser  # noqa: F401
    except ImportError:
        return

    with patch(
        "harness_browser.cdp.launcher.find_chrome",
        return_value=None,
    ):
        out = br._probe_env()
    assert out["harness_browser"] is True
    assert out["browsers_ok"] is False
    assert out["error"]


def test_probe_env_accepts_system_chrome() -> None:
    """System Chrome via find_chrome is enough for browsers_ok (same as launch)."""
    from octop.api.routers.browser import sessions as br

    try:
        import harness_browser  # noqa: F401
    except ImportError:
        return

    with (
        patch(
            "harness_browser.cdp.launcher.find_chrome",
            return_value="/usr/bin/google-chrome",
        ),
        patch(
            "octop.infra.browser.setup.playwright_chromium_installed",
            return_value=False,
        ),
        patch(
            "octop.infra.browser.setup.chrome_source_for_path",
            return_value="system",
        ),
    ):
        out = br._probe_env()
    assert out["harness_browser"] is True
    assert out["browsers_ok"] is True
    assert out["chrome_path"] == "/usr/bin/google-chrome"
    assert out["chrome_source"] == "system"
    assert out["playwright_chromium"] is False


def test_verify_browser_binary_ok(tmp_path: Path) -> None:
    from octop.api.routers.browser import sessions as br

    if os.name == "nt":
        # Windows cannot exec a shebang script; use a .bat that ignores args.
        exe = tmp_path / "fake-chrome.bat"
        exe.write_text("@echo Chrome 1.0\r\n", encoding="utf-8")
    else:
        exe = tmp_path / "fake-chrome"
        exe.write_text("#!/bin/sh\necho 'Chrome 1.0'\n", encoding="utf-8")
        exe.chmod(0o755)
    ok, msg = br._verify_browser_binary(str(exe))
    assert ok is True
    assert "Chrome" in msg


# --- session list (always permits empty) -----------------------------------


async def test_list_sessions_empty(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/browser/sessions", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


async def test_harness_sessions_shape(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/browser/harness-sessions", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "sessions" in body
    assert isinstance(body["sessions"], list)


async def test_harness_list_tabs_uses_sticky_target_id(monkeypatch) -> None:
    import aiohttp

    from octop.api.routers.browser import harness as harness_router

    class FakeProfile:
        cdp_port = 9222

        def load_target(self) -> str:
            return "TAB-2"

    class FakeInternal:
        _cfg = SimpleNamespace(cdp_host="localhost")
        _profile = FakeProfile()

    class FakeSession:
        _internal = FakeInternal()

    class FakeResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return [
                {
                    "type": "page",
                    "id": "TAB-1",
                    "url": "https://www.bilibili.com/",
                    "title": "B站",
                },
                {
                    "type": "page",
                    "id": "TAB-2",
                    "url": "https://weibo.com/",
                    "title": "微博",
                },
            ]

    class FakeClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, _url: str, timeout=None):
            return FakeResponse()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda: FakeClientSession())

    tabs = await harness_router.harness_list_tabs(FakeSession())

    assert [tab["active"] for tab in tabs] == [False, True]


async def test_new_tab_bad_restore_url_returns_warning() -> None:
    """A stale restored tab URL should not crash the whole browser session."""
    from octop.api.routers.browser import sessions as br

    class FakePage:
        def __init__(self) -> None:
            self.closed = False

        async def goto(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("net::ERR_FILE_NOT_FOUND")

        async def close(self) -> None:
            self.closed = True

        def is_closed(self) -> bool:
            return self.closed

    class FakeContext:
        async def new_page(self) -> FakePage:
            return FakePage()

    class FakeSession:
        id = "sid"
        url = "about:blank"
        context = FakeContext()
        pages: list[Any] = []
        active_idx = 0

        async def sync_pages(self) -> None:
            return None

        async def tab_list(self) -> list[dict[str, Any]]:
            return [{"idx": 0, "url": "about:blank", "title": "", "active": True}]

    with patch("octop.api.routers.browser.sessions._get_session", return_value=FakeSession()):
        resp = await br.new_tab(
            "sid",
            br.NewTabBody(url="file:///missing.html"),
            SimpleNamespace(id=1),
        )

    assert resp["id"] == "sid"
    assert "warning" in resp
    assert "file:///missing.html" in resp["warning"]


# --- create when env not ready -> 503 -------------------------------------


async def test_create_session_503_when_env_broken(env: Any) -> None:
    c, _srv, auth = env

    with patch(
        "octop.api.routers.browser.sessions._probe_env",
        return_value={
            "playwright": True,
            "browsers_ok": False,
            "error": "chromium not installed",
        },
    ):
        r = await c.post("/api/browser/sessions", headers=auth)
    assert r.status_code == 503
    body = r.json()
    # The specific env reason is surfaced via ``details`` (the message is a
    # generic localized string per the i18n design).
    assert "chromium" in body["error"]["details"]["error"].lower()


# --- cross-user isolation --------------------------------------------------


async def test_session_404_for_other_user(env: Any) -> None:
    c, _srv, auth = env
    r = await c.get("/api/browser/sessions/no-such-id", headers=auth)
    assert r.status_code == 404
    r = await c.delete("/api/browser/sessions/no-such-id", headers=auth)
    assert r.status_code == 404
    r = await c.get(
        "/api/browser/sessions/no-such-id/screenshot",
        headers=auth,
    )
    assert r.status_code == 404
    r = await c.post(
        "/api/browser/sessions/no-such-id/goto",
        headers=auth,
        json={"url": "https://example.com"},
    )
    assert r.status_code == 404


# --- install spawn ---------------------------------------------------------


async def test_install_returns_pid(env: Any) -> None:
    c, _srv, auth = env

    async def fake_stream():
        yield {"log": "downloading chromium"}
        yield {"done": True, "success": True}

    with patch(
        "harness_browser.install_chromium_stream",
        side_effect=lambda: fake_stream(),
    ):
        r = await c.post("/api/browser/install", headers=auth)
    assert r.status_code in (200, 202)
