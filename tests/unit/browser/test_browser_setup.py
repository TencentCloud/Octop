"""Tests for browser profile prep / uninstall helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from stat import S_IMODE

import pytest

from octop.infra.browser.setup import (
    _probe_dir_writable,
    _relocated_profiles_root_for_uid,
    _runtime_dir_for_uid,
    _temp_scope_token,
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
    # Linux uses /tmp/<uid>; other POSIX (e.g. macOS) uses tempfile + pid.
    assert path == _runtime_dir_for_uid()
    assert os.environ["XDG_RUNTIME_DIR"] == str(path)
    assert path.is_dir()
    assert os.access(path, os.W_OK | os.X_OK)
    assert S_IMODE(path.stat().st_mode) == 0o700


def test_non_linux_temp_dirs_use_gettempdir_with_stable_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows must not use a literal /tmp path (drive-root PermissionError)."""
    from octop.infra.browser import setup as browser_setup

    fake_tmp = tmp_path / "WinTemp"
    fake_tmp.mkdir()
    monkeypatch.setattr(browser_setup.sys, "platform", "win32")
    monkeypatch.setattr(browser_setup.tempfile, "gettempdir", lambda: str(fake_tmp))

    runtime = _runtime_dir_for_uid(uid=7)
    profiles = _relocated_profiles_root_for_uid(uid=7)

    assert runtime == fake_tmp / "runtime-harness-browser-7"
    assert profiles == fake_tmp / "harness-browser-profiles-7"
    # Same inputs → same paths across "process restarts" (no pid in the name).
    assert _runtime_dir_for_uid(uid=7) == runtime
    assert _relocated_profiles_root_for_uid(uid=7) == profiles


def test_temp_scope_token_uses_username_when_getuid_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.browser import setup as browser_setup

    # Simulate Windows: getuid absent / not callable.
    monkeypatch.setattr(browser_setup.os, "getuid", object())
    monkeypatch.setenv("USERNAME", "OctopUser")
    monkeypatch.delenv("USER", raising=False)

    assert _temp_scope_token() == "OctopUser"
    assert _temp_scope_token(uid=3) == "3"


def test_probe_dir_writable_skips_symlink_on_non_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    monkeypatch.setattr(browser_setup.sys, "platform", "win32")

    def _forbid_symlink(self: Path, *args: object, **kwargs: object) -> None:
        raise AssertionError("symlink probe must not run on non-Linux")

    monkeypatch.setattr(Path, "symlink_to", _forbid_symlink)

    target = tmp_path / "profile"
    assert _probe_dir_writable(target) is True
    assert target.is_dir()


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


@posix_only
def test_resolve_browser_display_clears_stale_display(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale $DISPLAY without an X socket must not force headed Chrome."""
    from octop.infra.browser import setup as browser_setup

    monkeypatch.setattr(browser_setup.sys, "platform", "linux")
    sock_dir = tmp_path / "X11"
    sock_dir.mkdir()
    monkeypatch.setattr(
        browser_setup,
        "_x11_socket_path",
        lambda display: (
            sock_dir / f"X{display.lstrip(':').split('.')[0]}" if display.startswith(":") else None
        ),
    )
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        "octop.infra.desktop.setup._display_from_env_file",
        lambda: None,
    )

    assert resolve_browser_display() is None
    assert "DISPLAY" not in os.environ


def test_ensure_profile_writable_recreates_when_not_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.browser import setup as browser_setup

    profile = tmp_path / "default"
    profile.mkdir()
    (profile / "Preferences").write_text("{}")

    if os.name == "posix":
        os.chmod(profile, 0o000)
        monkeypatch.setattr(browser_setup, "_under_root_home", lambda _p: False)
        try:
            result = ensure_profile_writable(profile)
            assert result == profile or "harness-browser-profiles" in str(result)
            assert _probe_dir_writable(result)
        finally:
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


@posix_only
def test_ensure_profile_writable_never_chmods_system_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for #84: profile prep must not chmod / or /tmp."""
    from octop.infra.browser import setup as browser_setup

    chmod_targets: list[str] = []
    real_chmod = os.chmod

    def tracking_chmod(path: str | bytes | os.PathLike[str], mode: int) -> None:
        text = os.fspath(path)
        chmod_targets.append(text)
        if text in ("/", "/tmp"):
            raise AssertionError(f"must not chmod system path {path}")
        return real_chmod(path, mode)

    monkeypatch.setattr(os, "chmod", tracking_chmod)
    monkeypatch.setattr(browser_setup, "_under_root_home", lambda _p: False)
    monkeypatch.setattr(browser_setup, "_probe_dir_writable", lambda _p: True)

    profile = Path(f"/tmp/harness-browser-profiles-{os.getuid()}") / "default"
    ensure_profile_writable(profile)

    # Profile prep no longer chmod/chown at all — recreate/relocate only.
    assert chmod_targets == []


def test_octop_browser_profiles_dir_shared(tmp_path: Path) -> None:
    from octop.infra.utils.browser_media import (
        BROWSER_PROFILES_REL,
        octop_browser_profiles_dir,
    )
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout(root=tmp_path / "octop")
    dest = octop_browser_profiles_dir(paths)
    assert dest == paths.root / BROWSER_PROFILES_REL
    assert dest.is_dir()
    # Shared root — not under any agent workspace.
    assert "agents" not in dest.parts


def test_configure_browser_profiles_dir_sets_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.utils.browser_media import configure_browser_profiles_dir

    monkeypatch.delenv("BROWSER_USE_PROFILES_DIR", raising=False)
    root = tmp_path / "browser-profiles"
    result = configure_browser_profiles_dir(root)
    assert result == root.resolve()
    assert root.is_dir()
    assert os.environ["BROWSER_USE_PROFILES_DIR"] == str(root.resolve())


def test_legacy_profiles_migrated_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.utils import browser_media as media
    from octop.infra.utils.paths import PathLayout

    # Do not rely on HOME/USERPROFILE — Path.home() differs on Windows.
    legacy_root = tmp_path / "legacy-profiles"
    legacy = legacy_root / "default"
    legacy.mkdir(parents=True)
    (legacy / "Preferences").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(media, "legacy_harness_profiles_dir", lambda: legacy_root)

    paths = PathLayout(root=tmp_path / "octop")
    dest = media.octop_browser_profiles_dir(paths)
    assert (dest / "default" / "Preferences").read_text(encoding="utf-8") == "{}"
    assert not legacy.exists()

    # Second call must not fail when legacy is empty/gone.
    media.octop_browser_profiles_dir(paths)
    assert (dest / "default" / "Preferences").exists()


@posix_only
def test_under_root_home_exempts_octop_home(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.browser import setup as browser_setup
    from octop.infra.utils.paths import PathLayout

    if not Path("/root").is_dir():
        pytest.skip("/root not available")

    monkeypatch.setattr(browser_setup.sys, "platform", "linux")

    def _fake_from_env() -> PathLayout:
        return PathLayout(root=Path("/root/.octop"))

    monkeypatch.setattr(
        "octop.infra.utils.paths.PathLayout.from_env",
        staticmethod(_fake_from_env),
    )

    assert browser_setup._under_root_home(Path("/root/.octop/browser-profiles/default")) is False
    assert browser_setup._under_root_home(Path("/root/.harness-browser/profiles/default")) is True
