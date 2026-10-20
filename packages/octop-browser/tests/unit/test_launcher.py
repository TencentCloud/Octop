"""Tests for octop_browser.cdp.launcher.find_chrome auto-discovery."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop_browser.cdp.launcher import (
    _find_playwright_chromium,
    _get_ws_url,
    _parse_pw_revision,
    _should_disable_dev_shm,
    _should_disable_gpu,
    _tail_stderr,
    terminate_browser,
)


def test_parse_pw_revision_valid():
    assert _parse_pw_revision("chromium-1223") == 1223
    assert _parse_pw_revision("chromium-9999") == 9999


def test_parse_pw_revision_invalid():
    assert _parse_pw_revision("not-a-version") == -1
    assert _parse_pw_revision("chromium") == -1


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="Layout differs on Windows; covered by separate path branch.",
)
def test_find_playwright_chromium_picks_highest_revision(monkeypatch, tmp_path):
    """Given two installed Chromium revisions, pick the newer one."""
    # Pretend $PLAYWRIGHT_BROWSERS_PATH points at our tmp dir
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))

    if sys.platform == "darwin":
        platform_subdir = "chrome-mac/Chromium.app/Contents/MacOS"
        binary_name = "Chromium"
    else:
        platform_subdir = "chrome-linux64"
        binary_name = "chrome"

    # Old revision
    old_dir = tmp_path / "chromium-1000" / platform_subdir
    old_dir.mkdir(parents=True)
    (old_dir / binary_name).write_text("#!/bin/sh\nexit 0\n")
    (old_dir / binary_name).chmod(0o755)

    # New revision
    new_dir = tmp_path / "chromium-1500" / platform_subdir
    new_dir.mkdir(parents=True)
    (new_dir / binary_name).write_text("#!/bin/sh\nexit 0\n")
    (new_dir / binary_name).chmod(0o755)

    found = _find_playwright_chromium()
    assert found is not None
    assert "chromium-1500" in found
    assert "chromium-1000" not in found


def test_find_playwright_chromium_returns_none_when_missing(monkeypatch, tmp_path):
    """No installs anywhere → returns None."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "empty"))
    # Also redirect HOME so the default ~/.cache/ms-playwright is empty too.
    monkeypatch.setenv("HOME", str(tmp_path))
    # On macOS the default uses ~/Library/Caches; redirect via HOME above.
    assert _find_playwright_chromium() is None


async def test_terminate_browser_uses_browser_cdp_endpoint(monkeypatch, tmp_path):
    from octop_browser.cdp import launcher

    sent: list[dict[str, object]] = []
    profile = SimpleNamespace(
        name="test",
        data_dir=tmp_path / "test",
        cdp_port=9222,
    )

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def json(self, content_type=None):
            return {"webSocketDebuggerUrl": "ws://localhost/devtools/browser/1"}

    class WebSocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send_json(self, payload):
            sent.append(payload)

    class Session:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def get(self, url):
            return Response()

        def ws_connect(self, url):
            return WebSocket()

    port_checks = iter([True, False])

    async def port_in_use(host, port):
        return next(port_checks)

    monkeypatch.setattr(launcher, "_port_in_use_at", port_in_use)
    monkeypatch.setattr(launcher.aiohttp, "ClientSession", Session)

    assert await terminate_browser(profile, cdp_host="localhost")
    assert sent == [{"id": 1, "method": "Browser.close"}]


async def test_terminate_browser_refuses_remote_host(tmp_path):
    profile = SimpleNamespace(
        name="test",
        data_dir=tmp_path / "test",
        cdp_port=9222,
    )
    assert not await terminate_browser(profile, cdp_host="browser.example")


def test_playwright_exe_candidates_windows_prefers_cft(monkeypatch, tmp_path):
    """Chrome-for-Testing (chrome-win64) wins over the legacy chrome-win layout."""
    from octop_browser.cdp.launcher import _playwright_exe_candidates

    monkeypatch.setattr(sys, "platform", "win32")
    candidates = _playwright_exe_candidates(tmp_path)

    assert candidates[0] == tmp_path / "chrome-win64" / "chrome.exe"
    assert tmp_path / "chrome-win" / "chrome.exe" in candidates


def test_playwright_exe_candidates_macos_prefers_cft(monkeypatch, tmp_path):
    """macOS probes the Chrome-for-Testing bundle before legacy Chromium.app."""
    from octop_browser.cdp.launcher import _playwright_exe_candidates

    monkeypatch.setattr(sys, "platform", "darwin")
    candidates = _playwright_exe_candidates(tmp_path)

    assert candidates[0].name == "Google Chrome for Testing"
    legacy = tmp_path.joinpath(
        "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"
    )
    assert legacy in candidates


def test_find_playwright_chromium_windows_cft_layout(monkeypatch, tmp_path):
    """A Playwright install written by a current release is discoverable."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))

    exe = tmp_path / "chromium-1187" / "chrome-win64" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("stub")

    assert _find_playwright_chromium() == str(exe)


def test_chrome_paths_win_expands_env_roots(monkeypatch, tmp_path):
    """Windows candidates are derived from the Program Files env vars."""
    from octop_browser.cdp.launcher import _chrome_paths_win

    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    paths = _chrome_paths_win()

    expected = tmp_path / "pf" / "Google" / "Chrome" / "Application" / "chrome.exe"
    assert paths[0] == str(expected)
    assert any(p.endswith("msedge.exe") for p in paths)


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="Linux falls back to chrome-linux when chrome-linux64 is absent.",
)
def test_find_playwright_chromium_falls_back_to_old_layout(monkeypatch, tmp_path):
    """Older Playwright builds use chrome-linux/ instead of chrome-linux64/."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    old_layout = tmp_path / "chromium-900" / "chrome-linux"
    old_layout.mkdir(parents=True)
    binary = old_layout / "chrome"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    found = _find_playwright_chromium()
    assert found is not None
    assert Path(found) == binary


# ---------------------------------------------------------------------------
# --no-sandbox auto-detection
# ---------------------------------------------------------------------------


def test_no_sandbox_env_override_truthy(monkeypatch):
    """``BROWSER_USE_NO_SANDBOX=1`` forces --no-sandbox unconditionally."""
    from octop_browser.cdp.launcher import _should_disable_sandbox

    monkeypatch.setenv("BROWSER_USE_NO_SANDBOX", "1")
    assert _should_disable_sandbox() is True
    monkeypatch.setenv("BROWSER_USE_NO_SANDBOX", "true")
    assert _should_disable_sandbox() is True
    monkeypatch.setenv("BROWSER_USE_NO_SANDBOX", "yes")
    assert _should_disable_sandbox() is True


def test_no_sandbox_env_override_falsy(monkeypatch):
    """``BROWSER_USE_NO_SANDBOX=0`` force-disables auto-detect even on
    container hosts where the kernel would otherwise refuse user
    namespaces."""
    from octop_browser.cdp.launcher import _should_disable_sandbox

    monkeypatch.setenv("BROWSER_USE_NO_SANDBOX", "0")
    assert _should_disable_sandbox() is False
    monkeypatch.setenv("BROWSER_USE_NO_SANDBOX", "false")
    assert _should_disable_sandbox() is False


def test_no_sandbox_off_on_macos(monkeypatch):
    """On macOS / Windows we never need --no-sandbox."""
    from octop_browser.cdp import launcher as _l

    monkeypatch.delenv("BROWSER_USE_NO_SANDBOX", raising=False)
    monkeypatch.setattr(_l.sys, "platform", "darwin")
    assert _l._should_disable_sandbox() is False
    monkeypatch.setattr(_l.sys, "platform", "win32")
    assert _l._should_disable_sandbox() is False


def test_user_namespaces_available_returns_bool():
    """Direct probe — just verify it returns a bool without crashing."""
    from octop_browser.cdp.launcher import _user_namespaces_available

    assert isinstance(_user_namespaces_available(), bool)


# ---------------------------------------------------------------------------
# Stderr capture & failure-message enrichment
# ---------------------------------------------------------------------------


def test_tail_stderr_decodes_and_truncates():
    """Long stderr blobs are returned tail-first with a truncation marker."""
    big = b"X" * 10_000 + b"END"
    out = _tail_stderr(io.BytesIO(big), max_bytes=128)
    assert out.endswith("END")
    assert out.startswith("...(truncated)")


def test_tail_stderr_handles_none_and_errors():
    """``None`` and unreadable files yield an empty string (best-effort)."""
    assert _tail_stderr(None) == ""
    closed = io.BytesIO(b"x")
    closed.close()
    assert _tail_stderr(closed) == ""


async def test_get_ws_url_surfaces_chrome_stderr_on_early_exit():
    """Chrome dies before binding → RuntimeError carries returncode + stderr tail.

    Polling MUST short-circuit on the first iteration (no HTTP attempts) so
    callers see the real cause within milliseconds instead of after the full
    ``launch_retries * launch_delay`` timeout budget.
    """
    poll_calls = {"n": 0}

    def fake_poll():
        poll_calls["n"] += 1
        return 127  # already dead

    fake_proc = SimpleNamespace(poll=fake_poll, returncode=127)
    stderr_io = io.BytesIO(
        b"./chrome: error while loading shared libraries: "
        b"libatk-bridge-2.0.so.0: cannot open shared object file: "
        b"No such file or directory\n"
    )

    with pytest.raises(RuntimeError) as exc:
        # Large retries to prove we exit on iteration 1, not after exhaustion.
        await _get_ws_url(
            port=65500,
            retries=20,
            delay=0.0,
            process=fake_proc,
            stderr_file=stderr_io,
        )
    msg = str(exc.value)
    assert "returncode=127" in msg
    assert "libatk-bridge-2.0.so.0" in msg
    # Proves we did not iterate all 20 retries.
    assert poll_calls["n"] == 1


async def test_get_ws_url_includes_stderr_tail_on_timeout():
    """Process is still alive but Chrome never binds → tail is appended to the
    'did not start' message so callers can still see Chrome's chatter."""
    fake_proc = SimpleNamespace(poll=lambda: None, returncode=None)
    stderr_io = io.BytesIO(b"some chromium chatter\n")
    with pytest.raises(RuntimeError) as exc:
        await _get_ws_url(
            port=65501,  # closed; aiohttp will fail every retry
            retries=2,
            delay=0.0,
            process=fake_proc,
            stderr_file=stderr_io,
        )
    msg = str(exc.value)
    assert "did not start" in msg
    assert "some chromium chatter" in msg


# ---------------------------------------------------------------------------
# --disable-gpu / --disable-dev-shm-usage flags
#
# These are needed in containerised / GPU-less environments. Without them
# Chrome's GPU process aborts (SwiftShader CreateCommandBuffer fails) and
# renderers never start, leaving the agent's CDP `Page.enable` hung on a
# 30-second timeout. Defaults match Playwright's launcher.
# ---------------------------------------------------------------------------


def test_should_disable_gpu_default_headless_true(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_DISABLE_GPU", raising=False)
    assert _should_disable_gpu(headless=True) is True


def test_should_disable_gpu_default_headed_false(monkeypatch):
    """In headed mode the user has a desktop and likely wants GPU acceleration."""
    monkeypatch.delenv("BROWSER_USE_DISABLE_GPU", raising=False)
    assert _should_disable_gpu(headless=False) is False


def test_should_disable_gpu_env_force_on(monkeypatch):
    """``BROWSER_USE_DISABLE_GPU=1`` forces --disable-gpu even in headed mode."""
    monkeypatch.setenv("BROWSER_USE_DISABLE_GPU", "1")
    assert _should_disable_gpu(headless=False) is True
    monkeypatch.setenv("BROWSER_USE_DISABLE_GPU", "true")
    assert _should_disable_gpu(headless=False) is True


def test_should_disable_gpu_env_force_off(monkeypatch):
    """``BROWSER_USE_DISABLE_GPU=0`` keeps GPU enabled even in headless mode
    (escape hatch for hosts with a working GPU + container)."""
    monkeypatch.setenv("BROWSER_USE_DISABLE_GPU", "0")
    assert _should_disable_gpu(headless=True) is False


def test_should_disable_dev_shm_default_linux(monkeypatch):
    """On Linux the default is to disable /dev/shm usage; containers ship with
    a 64 MiB tmpfs that's too small for Chrome's renderers."""
    monkeypatch.delenv("BROWSER_USE_DISABLE_DEV_SHM_USAGE", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert _should_disable_dev_shm() is True


def test_should_disable_dev_shm_default_macos(monkeypatch):
    """macOS has no /dev/shm semantics; the flag is harmless but unnecessary."""
    monkeypatch.delenv("BROWSER_USE_DISABLE_DEV_SHM_USAGE", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _should_disable_dev_shm() is False


def test_should_disable_dev_shm_env_force_off(monkeypatch):
    """``BROWSER_USE_DISABLE_DEV_SHM_USAGE=0`` keeps /dev/shm in play (escape
    hatch for hosts with a generous tmpfs)."""
    monkeypatch.setenv("BROWSER_USE_DISABLE_DEV_SHM_USAGE", "0")
    monkeypatch.setattr(sys, "platform", "linux")
    assert _should_disable_dev_shm() is False


def test_build_flags_headless_includes_gpu_and_shm_flags(monkeypatch, tmp_path):
    """End-to-end: a headless launch on Linux gets both flags by default."""
    from octop_browser.cdp.launcher import _build_flags
    from octop_browser.profile import Profile

    monkeypatch.delenv("BROWSER_USE_DISABLE_GPU", raising=False)
    monkeypatch.delenv("BROWSER_USE_DISABLE_DEV_SHM_USAGE", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    profile = Profile(name="t", data_dir=str(tmp_path), cdp_port=9999)
    flags = _build_flags(profile, headless=True)
    assert "--disable-gpu" in flags
    assert "--disable-dev-shm-usage" in flags


# ---------------------------------------------------------------------------
# get_page_ws_url — sticky / fallback target selection
# ---------------------------------------------------------------------------


class _FakeAiohttpResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self._payload


class _FakeAiohttpSession:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, _url, timeout=None):
        return _FakeAiohttpResp(self._payload)


class _FakeNoPagesThenNewSession:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        return _FakeAiohttpResp([])

    def put(self, url, timeout=None):
        self.calls.append(("PUT", url))
        return _FakeAiohttpResp(
            {
                "type": "page",
                "id": "CREATED",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://created",
            }
        )


def _patch_targets(monkeypatch, payload):
    """Make ``aiohttp.ClientSession()`` return *payload* from ``/json``."""
    from octop_browser.cdp import launcher as _l

    monkeypatch.setattr(
        _l.aiohttp, "ClientSession", lambda: _FakeAiohttpSession(payload)
    )


@pytest.fixture()
def fake_profile(tmp_path):
    from octop_browser.profile import Profile

    pdir = tmp_path / "profile"
    pdir.mkdir()
    return Profile(name="work", data_dir=pdir, cdp_port=9222)


async def test_get_page_ws_url_prefers_sticky_target(monkeypatch, fake_profile):
    """When the profile pinned a target and that target is still alive, use it."""
    from octop_browser.cdp.launcher import get_page_ws_url

    fake_profile.save_target("STICKY")
    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "OTHER",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://other",
            },
            {
                "type": "page",
                "id": "STICKY",
                "url": "https://example.com",
                "webSocketDebuggerUrl": "ws://sticky",
            },
        ],
    )
    ws = await get_page_ws_url(9222, profile=fake_profile)
    assert ws == "ws://sticky"
    # Stays sticky for the next call too.
    assert fake_profile.load_target() == "STICKY"


async def test_get_page_ws_url_clears_dead_sticky_target(monkeypatch, fake_profile):
    """If the cached id is no longer in /json, drop it and pick a live one."""
    from octop_browser.cdp.launcher import get_page_ws_url

    fake_profile.save_target("DEAD")
    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "ALIVE",
                "url": "https://example.com",
                "webSocketDebuggerUrl": "ws://alive",
            },
        ],
    )
    ws = await get_page_ws_url(9222, profile=fake_profile)
    assert ws == "ws://alive"
    assert fake_profile.load_target() == "ALIVE"


async def test_get_page_ws_url_does_not_steal_non_blank_when_blank_is_sticky(
    monkeypatch,
    fake_profile,
):
    """A sticky blank target represents the current controlled tab.

    Reattaching to the first non-blank page instead would make a later
    ``navigate`` overwrite an already-open site, which is perceived as
    "opened the wrong page".
    """
    from octop_browser.cdp.launcher import get_page_ws_url

    fake_profile.save_target("BLANK")
    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "REAL",
                "url": "https://already-open.example/",
                "webSocketDebuggerUrl": "ws://real",
            },
            {
                "type": "page",
                "id": "BLANK",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://blank",
            },
        ],
    )

    ws = await get_page_ws_url(9222, profile=fake_profile)

    assert ws == "ws://blank"
    assert fake_profile.load_target() == "BLANK"


async def test_get_page_ws_url_skips_about_blank(monkeypatch, fake_profile):
    """Without a sticky target, prefer the first non-about:blank page."""
    from octop_browser.cdp.launcher import get_page_ws_url

    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "BLANK1",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://blank1",
            },
            {
                "type": "page",
                "id": "REAL",
                "url": "https://example.com",
                "webSocketDebuggerUrl": "ws://real",
            },
            {
                "type": "page",
                "id": "BLANK2",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://blank2",
            },
        ],
    )
    ws = await get_page_ws_url(9222, profile=fake_profile)
    assert ws == "ws://real"
    assert fake_profile.load_target() == "REAL"


async def test_get_page_ws_url_falls_back_to_blank(monkeypatch, fake_profile):
    """If every page is about:blank, pick the first one rather than failing."""
    from octop_browser.cdp.launcher import get_page_ws_url

    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "B1",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://b1",
            },
            {
                "type": "page",
                "id": "B2",
                "url": "about:blank",
                "webSocketDebuggerUrl": "ws://b2",
            },
        ],
    )
    ws = await get_page_ws_url(9222, profile=fake_profile)
    assert ws == "ws://b1"


async def test_get_page_ws_url_no_pages_raises(monkeypatch, fake_profile):
    from octop_browser.cdp.launcher import get_page_ws_url

    _patch_targets(monkeypatch, [{"type": "background_page", "id": "BG"}])
    with pytest.raises(RuntimeError, match="No open page"):
        await get_page_ws_url(9222, profile=fake_profile)


async def test_get_page_ws_url_creates_blank_when_no_page_targets(
    monkeypatch,
    fake_profile,
):
    from octop_browser.cdp import launcher as _l
    from octop_browser.cdp.launcher import get_page_ws_url

    fake_session = _FakeNoPagesThenNewSession()
    monkeypatch.setattr(_l.aiohttp, "ClientSession", lambda: fake_session)

    ws = await get_page_ws_url(9222, profile=fake_profile)

    assert ws == "ws://created"
    assert fake_profile.load_target() == "CREATED"
    assert ("PUT", "http://localhost:9222/json/new?about:blank") in fake_session.calls
    assert (
        "GET",
        "http://localhost:9222/json/new?about:blank",
    ) not in fake_session.calls


async def test_get_page_ws_url_works_without_profile(monkeypatch):
    """Backwards compat: callers that don't supply a profile still get a URL."""
    from octop_browser.cdp.launcher import get_page_ws_url

    _patch_targets(
        monkeypatch,
        [
            {
                "type": "page",
                "id": "ANY",
                "url": "https://x",
                "webSocketDebuggerUrl": "ws://any",
            },
        ],
    )
    assert await get_page_ws_url(9222) == "ws://any"
