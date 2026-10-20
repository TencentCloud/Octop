"""Tests for Chrome launch pre-flight helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from octop_browser.cdp.launch_prep import (
    _alt_profiles_root,
    _probe_writable,
    _runtime_dir_for_uid,
    _temp_scope_token,
    clear_profile_locks,
    ensure_profile_writable,
    ensure_xdg_runtime_dir,
    prepare_chrome_launch,
)
from octop_browser.profile import Profile

linux_only = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux-only"
)


def test_clear_profile_locks(tmp_path: Path) -> None:
    profile_dir = tmp_path / "default"
    profile_dir.mkdir()
    (profile_dir / "SingletonLock").write_text("x")
    (profile_dir / "SingletonCookie").write_text("y")
    cleared = clear_profile_locks(profile_dir)
    assert "SingletonLock" in cleared
    assert not (profile_dir / "SingletonLock").exists()


@linux_only
def test_ensure_xdg_runtime_dir_sets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/0")
    env: dict[str, str] = {}
    path = ensure_xdg_runtime_dir(env)
    assert path is not None
    assert env["XDG_RUNTIME_DIR"] == str(path)
    assert path.as_posix().startswith("/tmp/runtime-octop-browser-")
    assert path.is_dir()


def test_ensure_xdg_runtime_dir_noop_on_non_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop_browser.cdp import launch_prep as prep

    monkeypatch.setattr(prep.sys, "platform", "win32")
    env: dict[str, str] = {"XDG_RUNTIME_DIR": "keep-me"}
    assert ensure_xdg_runtime_dir(env) is None
    assert env == {"XDG_RUNTIME_DIR": "keep-me"}


@linux_only
def test_ensure_profile_writable_relocates_root_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a profile under /root by patching the detector.
    from octop_browser.cdp import launch_prep as prep

    data = tmp_path / "root-home" / "default"
    data.mkdir(parents=True)
    profile = Profile(name="default", data_dir=data, cdp_port=9222)
    monkeypatch.setattr(prep, "_under_root_home", lambda _p: True)
    monkeypatch.setattr(prep, "_alt_profiles_root", lambda: tmp_path / "alt-profiles")
    monkeypatch.setenv("BROWSER_USE_PROFILES_DIR", str(tmp_path / "seed-profiles"))
    seed = str(tmp_path / "seed-profiles")

    updated = ensure_profile_writable(profile)
    assert updated.data_dir == tmp_path / "alt-profiles" / "default"
    assert updated.data_dir.is_dir()
    # Relocate must not pollute process-global profiles dir (multi-user hosts).
    assert os.environ.get("BROWSER_USE_PROFILES_DIR") == seed


@linux_only
def test_prepare_chrome_launch_injects_xdg(tmp_path: Path) -> None:
    data = tmp_path / "default"
    data.mkdir()
    profile = Profile(name="default", data_dir=data, cdp_port=9333)
    updated, env = prepare_chrome_launch(profile)
    assert "XDG_RUNTIME_DIR" in env
    assert env["XDG_RUNTIME_DIR"].startswith("/tmp/runtime-octop-browser-")
    assert updated.data_dir.exists()
    assert env["BROWSER_USE_PROFILES_DIR"] == str(updated.data_dir.parent)


@linux_only
def test_prepare_chrome_launch_env_reflects_relocate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop_browser.cdp import launch_prep as prep

    data = tmp_path / "root-home" / "default"
    data.mkdir(parents=True)
    profile = Profile(name="default", data_dir=data, cdp_port=9222)
    monkeypatch.setattr(prep, "_under_root_home", lambda _p: True)
    monkeypatch.setattr(prep, "_alt_profiles_root", lambda: tmp_path / "alt-profiles")
    monkeypatch.setenv("BROWSER_USE_PROFILES_DIR", str(tmp_path / "seed-profiles"))

    updated, env = prepare_chrome_launch(profile)
    assert updated.data_dir == tmp_path / "alt-profiles" / "default"
    assert env["BROWSER_USE_PROFILES_DIR"] == str(tmp_path / "alt-profiles")
    assert os.environ.get("BROWSER_USE_PROFILES_DIR") == str(tmp_path / "seed-profiles")


def test_probe_writable_skips_symlink_on_non_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop_browser.cdp import launch_prep as prep

    monkeypatch.setattr(prep.sys, "platform", "win32")

    def _forbid_symlink(self: Path, *args: object, **kwargs: object) -> None:
        raise AssertionError("symlink probe must not run on non-Linux")

    monkeypatch.setattr(Path, "symlink_to", _forbid_symlink)

    target = tmp_path / "profile"
    assert _probe_writable(target) is True
    assert target.is_dir()


def test_ensure_profile_writable_keeps_dir_when_symlink_fails_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#752: Windows symlink failure must not force a profile relocate."""
    from octop_browser.cdp import launch_prep as prep

    monkeypatch.setattr(prep.sys, "platform", "win32")
    monkeypatch.setenv("BROWSER_USE_PROFILES_DIR", str(tmp_path / "configured-root"))

    def _fail_symlink(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("SeCreateSymbolicLinkPrivilege required")

    monkeypatch.setattr(Path, "symlink_to", _fail_symlink)

    data = tmp_path / "configured-root" / "user-2"
    data.mkdir(parents=True)
    profile = Profile(name="user-2", data_dir=data, cdp_port=9223)

    updated = ensure_profile_writable(profile)
    assert updated.data_dir == data
    assert os.environ.get("BROWSER_USE_PROFILES_DIR") == str(
        tmp_path / "configured-root"
    )


def test_alt_profiles_root_uses_tempdir_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows must not use a literal /tmp path (drive-relative \\tmp\\...)."""
    from octop_browser.cdp import launch_prep as prep

    fake_tmp = tmp_path / "WinTemp"
    fake_tmp.mkdir()
    monkeypatch.setattr(prep.sys, "platform", "win32")
    monkeypatch.setattr(prep.tempfile, "gettempdir", lambda: str(fake_tmp))
    if hasattr(prep.os, "getuid"):
        monkeypatch.setattr(prep.os, "getuid", object())
    monkeypatch.setenv("USERNAME", "OctopUser")
    monkeypatch.delenv("USER", raising=False)

    profiles = _alt_profiles_root()
    runtime = _runtime_dir_for_uid()

    assert profiles == fake_tmp / "octop-browser-profiles-OctopUser"
    assert runtime == fake_tmp / "runtime-octop-browser-OctopUser"
    assert profiles.is_absolute()
    assert runtime.is_absolute()


def test_temp_scope_token_uses_username_when_getuid_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop_browser.cdp import launch_prep as prep

    if hasattr(prep.os, "getuid"):
        monkeypatch.setattr(prep.os, "getuid", object())
    monkeypatch.setenv("USERNAME", "OctopUser")
    monkeypatch.delenv("USER", raising=False)

    assert _temp_scope_token() == "OctopUser"
    assert _temp_scope_token(uid=3) == "3"


@linux_only
def test_probe_writable_still_probes_symlink_on_linux(tmp_path: Path) -> None:
    target = tmp_path / "profile"
    assert _probe_writable(target) is True
    assert not any(target.glob(".octop-link-*"))


@linux_only
def test_alt_profiles_root_stays_under_tmp_on_linux() -> None:
    root = _alt_profiles_root()
    assert root.as_posix().startswith("/tmp/octop-browser-profiles-")
