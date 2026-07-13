"""Tests for browser profile prep / uninstall helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from octop.infra.browser.setup import (
    _probe_dir_writable,
    chrome_source_for_path,
    clear_profile_locks,
    ensure_chrome_runtime_env,
    ensure_profile_writable,
    recover_stale_profile,
    resolve_browser_display,
    uninstall_browser_stream,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only runtime dirs")


def test_clear_profile_locks_removes_singleton_files(tmp_path: Path) -> None:
    profile = tmp_path / "default"
    profile.mkdir()
    (profile / "SingletonLock").write_text("lock")
    (profile / "SingletonCookie").write_text("cookie")
    expected = {"SingletonLock", "SingletonCookie"}
    try:
        (profile / "SingletonSocket").symlink_to(tmp_path / "nonexistent-socket")
        expected.add("SingletonSocket")
    except OSError:
        (profile / "SingletonSocket").write_text("socket")
        expected.add("SingletonSocket")

    cleared = clear_profile_locks(profile)

    assert set(cleared) == expected
    assert not (profile / "SingletonLock").exists()
    assert not (profile / "SingletonCookie").exists()
    assert not (profile / "SingletonSocket").exists()


def test_chrome_source_classifies_playwright_and_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    cache = tmp_path / "ms-playwright"
    pw_chrome = (
        cache / "chromium-123" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    )
    pw_chrome.parent.mkdir(parents=True)
    pw_chrome.write_text("x")
    monkeypatch.setattr(browser_setup, "_playwright_cache_roots", lambda: [cache])

    assert chrome_source_for_path(str(pw_chrome)) == "playwright"
    assert chrome_source_for_path("/usr/bin/google-chrome") == "system"


@pytest.mark.asyncio
async def test_uninstall_only_removes_playwright_chromium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    cache = tmp_path / "ms-playwright"
    cdir = cache / "chromium-999"
    cdir.mkdir(parents=True)
    (cdir / "chrome").write_text("bin")
    harness = tmp_path / ".harness-browser" / "profiles" / "default"
    harness.mkdir(parents=True)
    (harness / "Preferences").write_text("{}")

    async def _close() -> int:
        return 0

    monkeypatch.setattr(browser_setup, "_playwright_cache_roots", lambda: [cache])
    monkeypatch.setattr(browser_setup, "_profiles_root", lambda: harness.parent)
    monkeypatch.setattr(browser_setup, "_close_harness_registry", _close)

    events: list[dict[str, object]] = []
    async for chunk in uninstall_browser_stream():
        assert chunk.startswith("data: ")
        events.append(json.loads(chunk[6:]))

    assert any(e.get("done") and e.get("success") for e in events)
    assert not cdir.exists()
    assert (harness / "Preferences").exists(), "harness profile must remain"


def test_recover_stale_profile_renames_and_recreates(tmp_path: Path) -> None:
    profile = tmp_path / "default"
    profile.mkdir()
    (profile / "Preferences").write_text("{}")
    (profile / "SingletonLock").write_text("stale")

    recover_stale_profile(profile)

    assert profile.is_dir()
    assert not (profile / "Preferences").exists()
    stale_dirs = list(tmp_path.glob("default.stale-*"))
    assert len(stale_dirs) == 1
    assert (stale_dirs[0] / "Preferences").exists()


@posix_only
def test_ensure_chrome_runtime_env_forces_tmp_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/0")
    path = ensure_chrome_runtime_env()
    assert path == Path(f"/tmp/runtime-harness-browser-{os.getuid()}")
    assert os.environ["XDG_RUNTIME_DIR"] == str(path)
    assert path.is_dir()
    assert os.access(path, os.W_OK | os.X_OK)


@posix_only
def test_resolve_browser_display_uses_x_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    monkeypatch.setattr(browser_setup.sys, "platform", "linux")
    sock_dir = tmp_path / "X11"
    sock_dir.mkdir()
    (sock_dir / "X99").touch()
    monkeypatch.setattr(
        browser_setup,
        "_x11_socket_path",
        lambda display: (
            sock_dir / f"X{display.lstrip(':').split('.')[0]}" if display.startswith(":") else None
        ),
    )
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(
        "octop.infra.desktop.setup._display_from_env_file",
        lambda: ":99",
    )
    display = resolve_browser_display()
    assert display == ":99"
    assert os.environ["DISPLAY"] == ":99"


def test_ensure_profile_writable_recreates_when_not_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    profile = tmp_path / "default"
    profile.mkdir()
    (profile / "Preferences").write_text("{}")

    # Simulate unwritable dir by making probe always fail once, then succeed
    # after recreate — easier: chmod 0 if posix.
    if os.name == "posix":
        os.chmod(profile, 0o000)
        monkeypatch.setattr(
            browser_setup,
            "_try_fix_ownership",
            lambda _p: None,
        )
        monkeypatch.setattr(browser_setup, "_under_root_home", lambda _p: False)
        try:
            result = ensure_profile_writable(profile)
            assert result == profile or "harness-browser-profiles" in str(result)
            assert _probe_dir_writable(result)
        finally:
            os.chmod(profile, 0o700)
            if profile.exists():
                os.chmod(profile, 0o700)
    else:
        assert ensure_profile_writable(profile) == profile


@posix_only
def test_ensure_profile_writable_relocates_root_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    profile = tmp_path / "under-root" / "default"
    profile.mkdir(parents=True)
    (profile / "Preferences").write_text("{}")
    monkeypatch.setattr(browser_setup.sys, "platform", "linux")
    monkeypatch.setattr(browser_setup, "_under_root_home", lambda _p: True)
    monkeypatch.setattr(
        browser_setup,
        "_relocate_profiles_root",
        lambda p: tmp_path / "relocated" / p.name,
    )
    (tmp_path / "relocated" / "default").mkdir(parents=True)

    result = ensure_profile_writable(profile)
    assert result == tmp_path / "relocated" / "default"
