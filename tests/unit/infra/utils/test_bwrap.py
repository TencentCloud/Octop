"""Tests for best-effort bubblewrap (``bwrap``) provisioning — all platforms."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from tests.support.bwrap_marks import linux_bwrap_only

from octop.infra.utils import bwrap as bwrap_mod
from octop.infra.utils.bwrap import ensure_bubblewrap


def test_ensure_skips_on_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "darwin")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: None)
    result = ensure_bubblewrap()
    assert result["status"] == "skipped"
    assert result["reason"] == "not_linux"


def test_ensure_skips_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "win32")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: None)
    result = ensure_bubblewrap()
    assert result["status"] == "skipped"
    assert result["reason"] == "not_linux"
    assert "Linux-only" in result["detail"]


def test_ensure_ready_when_bwrap_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "linux")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: "/usr/bin/bwrap")
    result = ensure_bubblewrap()
    assert result["status"] == "ready"
    assert result["reason"] == "already_present"


def test_ensure_degraded_when_no_package_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "linux")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: None)
    monkeypatch.setattr("octop.infra.utils.bwrap._detect_package_manager", lambda: None)
    result = ensure_bubblewrap()
    assert result["status"] == "degraded"
    assert result["reason"] == "no_package_manager"


def test_ensure_degraded_when_no_privilege(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "linux")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: None)
    monkeypatch.setattr("octop.infra.utils.bwrap._detect_package_manager", lambda: "apt")
    monkeypatch.setattr("octop.infra.utils.bwrap._can_install_without_password", lambda: False)
    result = ensure_bubblewrap()
    assert result["status"] == "degraded"
    assert result["reason"] == "no_privilege"


def test_ensure_installed_after_successful_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "linux")
    calls = {"n": 0}

    def which(name: str) -> str | None:
        if name != "bwrap":
            return None
        calls["n"] += 1
        return None if calls["n"] == 1 else "/usr/bin/bwrap"

    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", which)
    monkeypatch.setattr("octop.infra.utils.bwrap._detect_package_manager", lambda: "apt")
    monkeypatch.setattr("octop.infra.utils.bwrap._can_install_without_password", lambda: True)
    install = MagicMock(return_value=True)
    monkeypatch.setattr("octop.infra.utils.bwrap._install_bubblewrap", install)
    result = ensure_bubblewrap()
    assert result["status"] == "installed"
    assert result["reason"] == "install_ok"
    install.assert_called_once_with("apt")


def test_ensure_degraded_when_install_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.utils.bwrap.sys.platform", "linux")
    monkeypatch.setattr("octop.infra.utils.bwrap.shutil.which", lambda _n: None)
    monkeypatch.setattr("octop.infra.utils.bwrap._detect_package_manager", lambda: "dnf")
    monkeypatch.setattr("octop.infra.utils.bwrap._can_install_without_password", lambda: True)
    monkeypatch.setattr("octop.infra.utils.bwrap._install_bubblewrap", lambda _mgr: False)
    result = ensure_bubblewrap()
    assert result["status"] == "degraded"
    assert result["reason"] == "install_failed"


@pytest.mark.parametrize(
    ("manager", "binary", "expected_tail"),
    [
        ("apt", "apt-get", ["install", "-y", "-qq", "bubblewrap"]),
        ("dnf", "dnf", ["install", "-y", "bubblewrap"]),
        ("yum", "yum", ["install", "-y", "bubblewrap"]),
        ("pacman", "pacman", ["-Sy", "--noconfirm", "bubblewrap"]),
        ("zypper", "zypper", ["install", "-y", "bubblewrap"]),
    ],
)
def test_install_argv_shapes(
    monkeypatch: pytest.MonkeyPatch,
    manager: str,
    binary: str,
    expected_tail: list[str],
) -> None:
    """Argv tail is stable on every platform (uses mocked ``shutil.which``)."""
    monkeypatch.setattr(
        "octop.infra.utils.bwrap.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == binary else None,
    )
    argv = bwrap_mod._install_argv(manager, use_sudo=False)
    assert argv is not None
    assert argv[-len(expected_tail) :] == expected_tail


def test_install_argv_uses_passwordless_sudo_prefix_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "octop.infra.utils.bwrap.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in {"sudo", "dnf"} else None,
    )
    argv = bwrap_mod._install_argv("dnf", use_sudo=True)
    assert argv is not None
    assert argv[0].endswith("sudo")
    assert argv[1] == "-n"


def test_install_argv_returns_none_for_unknown_manager() -> None:
    assert bwrap_mod._install_argv("unknown", use_sudo=False) is None


@linux_bwrap_only
def test_ensure_bubblewrap_ready_when_installed() -> None:
    """Linux CI with bwrap: no package-manager side effects."""
    result = ensure_bubblewrap()
    assert result == {
        "status": "ready",
        "reason": "already_present",
        "detail": "",
    }
