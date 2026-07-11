"""Tests for octop.infra.setup.service."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from octop.infra.setup import service as service_mod
from octop.infra.setup.service import (
    ServiceRuntime,
    install_service,
    launchd_bootstrap_target,
    launchd_domain,
    render_launchd_plist,
    render_systemd_unit,
    resolve_run_as_user,
    resolve_service_home,
    resolve_service_scope,
    restart_service,
    stop_service,
    unit_path,
)
from octop.infra.utils import posix_compat as pwd

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX service management")


def _runtime(tmp_path: Path) -> ServiceRuntime:
    octop_bin = tmp_path / "bin" / "octop"
    octop_bin.parent.mkdir(parents=True)
    octop_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    return ServiceRuntime(
        mode="systemd",
        host="0.0.0.0",
        port=9000,
        home=tmp_path,
        octop_bin=octop_bin,
        run_as_user=getpass.getuser(),
    )


def test_resolve_octop_executable_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_octop = tmp_path / "fake-octop"
    fake_octop.write_text("#!/bin/sh\n", encoding="utf-8")
    python_dir = tmp_path / "python-only"
    python_dir.mkdir()
    python = python_dir / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "empty-home"))
    monkeypatch.setattr(sys, "executable", str(python))
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake_octop))

    assert service_mod.resolve_octop_executable() == fake_octop


def test_render_systemd_unit_user_scope(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    unit = render_systemd_unit(runtime, user_unit=True)
    assert "OCTOP_SERVICE_MODE=systemd" in unit
    assert "OCTOP_SYSTEMD_USER=1" in unit
    assert "WantedBy=default.target" in unit
    assert f"User={getpass.getuser()}" not in unit
    assert f"ExecStart={runtime.octop_bin} run\n" in unit
    assert "--host" not in unit


def test_render_systemd_unit_system_scope(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    unit = render_systemd_unit(runtime, user_unit=False)
    assert f"User={getpass.getuser()}" in unit
    assert 'Environment="HOME=' in unit
    assert "WantedBy=multi-user.target" in unit
    assert "OCTOP_SYSTEMD_USER=1" not in unit


def test_render_systemd_unit_system_scope_uses_runtime_scope_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``--scope system`` must emit ``User=`` even when the installer is non-root.

    Previously we consulted ``_systemd_is_user_unit()`` which returned True
    before any system unit existed, so the first install omitted ``User=`` and
    systemd ran the daemon as root.
    """
    import getpass

    user = getpass.getuser()
    account_home = Path(pwd.getpwnam(user).pw_dir)
    runtime = replace(_runtime(tmp_path), run_as_user=user, scope="system")

    unit = render_systemd_unit(runtime)
    assert f"User={user}" in unit
    assert f'Environment="HOME={account_home}"' in unit
    assert f"Environment=OCTOP_HOME={tmp_path}" in unit
    assert "WorkingDirectory=" not in unit
    assert "WantedBy=multi-user.target" in unit


def test_render_systemd_unit_system_scope_omits_user_for_root(tmp_path: Path) -> None:
    """When running as root under a system unit, drop the User= line so that
    restrictive systemd builds don't force a degraded environment."""
    runtime = replace(_runtime(tmp_path), run_as_user="root")
    unit = render_systemd_unit(runtime, user_unit=False)
    assert "User=root" not in unit
    assert "WantedBy=multi-user.target" in unit


def test_probe_health_with_retry_uses_default_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry helper should default to a generous budget so callers don't
    need to tune it for slow service startups."""
    attempts: list[int] = []

    def _fake_probe(host: str, port: int) -> tuple[bool, str]:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 5:
            return False, "connection refused"
        return True, "{'ok': true}"

    monkeypatch.setattr(service_mod, "probe_health", _fake_probe)
    monkeypatch.setattr(service_mod.time, "sleep", lambda _s: None)

    # Call without overriding defaults — they should give us ≥5 attempts.
    ok, detail = service_mod.probe_health_with_retry("127.0.0.1", 8088)
    assert ok is True
    assert len(attempts) == 5
    assert "ok" in detail


def test_install_service_systemd_user_uses_systemctl_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = replace(_runtime(tmp_path), scope="user")
    calls: list[list[str]] = []

    def _fake_systemd_run(rt: ServiceRuntime, *args: str) -> object:
        assert rt.scope == "user"
        calls.append(list(args))

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: False)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_systemd_run", _fake_systemd_run)
    monkeypatch.setattr(service_mod, "_systemd_enable_linger", lambda _rt: None)

    install_service(runtime)
    assert calls[0] == ["daemon-reload"]
    assert calls[1] == ["enable", "octop"]


def test_render_systemd_unit_includes_service_mode(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    unit = render_systemd_unit(runtime, user_unit=True)
    assert "OCTOP_SERVICE_MODE=systemd" in unit
    assert "ExecStart=" in unit
    assert f"ExecStart={runtime.octop_bin} run\n" in unit
    assert "--host" not in unit
    assert "--port" not in unit


def test_render_launchd_plist_includes_service_mode(tmp_path: Path) -> None:
    runtime = replace(_runtime(tmp_path), mode="launchd")
    plist = render_launchd_plist(runtime)
    assert "<key>OCTOP_SERVICE_MODE</key>" in plist
    assert "<string>launchd</string>" in plist
    assert "<string>run</string>" in plist
    assert "<string>--host</string>" not in plist
    assert "<string>--port</string>" not in plist


def test_stop_service_noop_when_not_installed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    stop_service(runtime)


def test_restart_service_requires_install(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(RuntimeError, match="not installed"):
        restart_service(runtime)


def test_install_service_launchd_force_reload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = replace(_runtime(tmp_path), mode="launchd")
    calls: list[list[str]] = []

    def _fake_run_cmd(cmd: list[str], *, use_sudo: bool) -> object:
        calls.append(cmd)

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_run_cmd", _fake_run_cmd)

    install_service(runtime, force=True)
    assert ["launchctl", "bootout", "system/octop"] in calls
    assert any(cmd[:3] == ["launchctl", "bootstrap", "system"] for cmd in calls)


def test_install_service_launchd_force_reload_tolerates_unloaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`bootout` returns non-zero when nothing is loaded; install must not crash.

    Regression: previously we raised on the bootout step whenever the service
    was not yet registered, which made the `force` reinstall path brittle.
    macOS launchd reports this as "Could not find specified service" — the
    string we tolerate must include that phrasing.
    """
    runtime = replace(_runtime(tmp_path), mode="launchd")
    calls: list[list[str]] = []

    def _fake_run_cmd(cmd: list[str], *, use_sudo: bool) -> object:
        calls.append(cmd)

        class _Proc:
            def __init__(self) -> None:
                # bootout pretends nothing is loaded; bootstrap succeeds.
                if cmd[:2] == ["launchctl", "bootout"]:
                    self.returncode = 1
                    self.stderr = "Could not find specified service"
                else:
                    self.returncode = 0
                    self.stderr = ""
                self.stdout = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_run_cmd", _fake_run_cmd)

    install_service(runtime, force=True)  # must not raise
    assert any(cmd[:3] == ["launchctl", "bootout", "system/octop"] for cmd in calls)
    # ... and bootstrap must still run afterwards.
    assert any(cmd[:3] == ["launchctl", "bootstrap", "system"] for cmd in calls)


def test_launchd_bootstrap_tolerates_already_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Idempotent re-runs: bootstrap returns non-zero when the service is
    already loaded — the CLI/install path must treat that as success."""
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    captured: list[list[str]] = []

    def _fake_launchctl_run(scope: str, *args: str) -> object:
        captured.append([scope, *args])

        class _Proc:
            returncode = 1
            stdout = ""
            stderr = "Service already loaded"

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: False)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_launchctl_run", _fake_launchctl_run)

    install_service(runtime)  # must not raise on "already loaded" stderr
    assert any(args[:2] == ["user", "bootstrap"] for args in captured)


def test_probe_health_with_retry_succeeds_on_second_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"n": 0}

    def _fake_probe(host: str, port: int) -> tuple[bool, str]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return False, "connection refused"
        return True, "{'ok': true}"

    monkeypatch.setattr(service_mod, "probe_health", _fake_probe)
    monkeypatch.setattr(service_mod.time, "sleep", lambda _s: None)

    ok, detail = service_mod.probe_health_with_retry("127.0.0.1", 8088, attempts=3)
    assert ok is True
    assert attempts["n"] == 2
    assert "ok" in detail


# --- Scope / launchd user-domain support ----------------------------------


def test_resolve_service_scope_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "user")
    assert resolve_service_scope() == "user"
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "system")
    assert resolve_service_scope() == "system"
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "auto")
    assert resolve_service_scope() in ("user", "system")  # depends on euid


def test_resolve_service_scope_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown values are treated as 'auto' rather than crashing the CLI."""
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "nonsense")
    assert resolve_service_scope() in ("user", "system")


def test_launchd_domain_user_vs_system() -> None:
    """User agents run in the gui/$UID domain, system agents in system/."""
    user = launchd_domain("user")
    assert user.startswith("gui/")
    assert user.endswith("/octop")
    assert launchd_domain("system") == "system/octop"


def test_launchd_bootstrap_target_must_be_qualified() -> None:
    """`launchctl bootstrap` rejects bare `user`/`system` — must be `gui/$UID`."""
    target = launchd_bootstrap_target("user")
    assert target.startswith("gui/")
    assert "/" not in target.replace("gui/", "", 1)  # no service id suffix
    assert launchd_bootstrap_target("system") == "system"
    assert launchd_bootstrap_target("user") != "user"  # the bug we just fixed


def test_install_service_uses_bootstrap_target_not_bare_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: bootstrap must pass `gui/$UID`, never the bare scope name."""
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    captured: list[list[str]] = []

    def _fake_launchctl_run(scope: str, *args: str) -> object:
        captured.append([scope, *args])

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: False)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_launchctl_run", _fake_launchctl_run)

    install_service(runtime)
    assert captured, "bootstrap was not invoked"
    scope_passed, verb, target, _path = captured[0]
    assert scope_passed == "user"
    assert verb == "bootstrap"
    assert target == launchd_bootstrap_target("user")
    assert target != "user"  # the old, broken behaviour


def test_unit_path_launchd_user_is_under_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """User-scope macOS installs land in ~/Library/LaunchAgents (writable, no sudo)."""
    monkeypatch.setattr(service_mod, "is_root", lambda: False)
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "user")
    path = unit_path("launchd")
    assert path == Path.home() / "Library" / "LaunchAgents" / "octop.plist"


def test_unit_path_launchd_system_is_under_library(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "system")
    path = unit_path("launchd")
    assert path == Path("/Library/LaunchDaemons/octop.plist")


def test_render_launchd_plist_user_scope_omits_username(tmp_path: Path) -> None:
    """launchd rejects `<key>UserName</key>` for user-domain agents."""
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    plist = render_launchd_plist(runtime)
    assert "<key>UserName</key>" not in plist
    assert f"<string>{getpass.getuser()}</string>" not in plist  # run_as_user should not leak


def test_render_launchd_plist_system_scope_includes_username(tmp_path: Path) -> None:
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="system")
    plist = render_launchd_plist(runtime)
    assert "<key>UserName</key>" in plist
    assert f"<string>{getpass.getuser()}</string>" in plist


def test_install_service_launchd_user_no_sudo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """User-scope install on macOS must not invoke sudo for bootstrap."""
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    calls: list[tuple[str, list[str]]] = []

    def _fake_launchctl_run(scope: str, *args: str) -> object:
        calls.append((scope, list(args)))

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: False)
    monkeypatch.setattr(service_mod, "_write_unit", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_launchctl_run", _fake_launchctl_run)

    install_service(runtime)
    assert calls  # bootstrap was called
    scope_passed, bootstrap_args = calls[0]
    assert scope_passed == "user"
    assert bootstrap_args[0] == "bootstrap"
    assert bootstrap_args[1] == launchd_bootstrap_target("user")


def test_start_service_launchd_user_does_not_use_sudo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    captured: list[tuple[str, list[str]]] = []

    def _fake_launchctl_run(scope: str, *args: str) -> object:
        captured.append((scope, list(args)))

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(service_mod, "_launchctl_run", _fake_launchctl_run)
    monkeypatch.setattr(service_mod, "_wait_for_startup", lambda: None)

    start_service = service_mod.start_service
    start_service(runtime)
    scope_passed, args = captured[0]
    assert scope_passed == "user"
    assert args[:2] == ["kickstart", "-k"]
    assert args[2] == launchd_domain("user")


def test_restart_service_waits_for_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """restart must apply the same startup grace as start, otherwise the
    health probe races the new process."""
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    sleeps: list[float] = []

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(
        service_mod,
        "_launchctl_run",
        lambda rt, *a: type("_P", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(service_mod.time, "sleep", lambda s: sleeps.append(s))

    restart_service(runtime)
    # launchd restart: bootout → _wait_for_stop polls → bootstrap → _wait_for_startup
    assert service_mod._STARTUP_GRACE_SECONDS in sleeps  # noqa: SLF001


def test_resolve_run_as_user_root_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "root")
    assert resolve_run_as_user() == "root"


def test_resolve_run_as_user_normal_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_mod, "is_root", lambda: False)
    monkeypatch.setenv("USER", "ubuntu")
    assert resolve_run_as_user() == "ubuntu"


def test_resolve_run_as_user_root_always_returns_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # Root with SUDO_USER set still returns "root" — service runs as root.
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setenv("SUDO_USER", "ubuntu")
    monkeypatch.setenv("USER", "root")
    assert resolve_run_as_user() == "root"


def test_resolve_service_home_uses_passwd_not_effective_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sudo install as root must still target the invoking user's ~/.octop."""
    monkeypatch.delenv("OCTOP_HOME", raising=False)
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setenv("SUDO_USER", "ubuntu")
    assert resolve_service_home(run_as_user="ubuntu") == Path("/home/ubuntu") / ".octop"


def test_resolve_service_home_root_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTOP_HOME", raising=False)
    assert resolve_service_home(run_as_user="root") == Path(pwd.getpwnam("root").pw_dir) / ".octop"


def test_build_runtime_root_always_system_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Root with SUDO_USER must still produce a system-scope unit for root,
    # not a user-scope unit for the original invoker.
    root_home = tmp_path / "root-home"
    root_home.mkdir()
    octop_bin = root_home / ".octop" / "bin" / "octop"
    octop_bin.parent.mkdir(parents=True)
    octop_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setenv("SUDO_USER", "ubuntu")
    monkeypatch.setenv("USER", "root")
    monkeypatch.delenv("OCTOP_HOME", raising=False)
    monkeypatch.setattr(
        service_mod.pwd,
        "getpwnam",
        lambda name: type("Pw", (), {"pw_dir": str(root_home)})(),
    )
    monkeypatch.setattr(service_mod, "resolve_bind_options", lambda home=None: ("0.0.0.0", 443))

    runtime = service_mod.build_runtime(mode="systemd", scope="system")
    assert runtime.run_as_user == "root"
    assert runtime.scope == "system"

    unit = render_systemd_unit(runtime, user_unit=False)
    assert "User=" not in unit  # no User= line when running as root
    assert "WantedBy=multi-user.target" in unit


def test_systemctl_user_wraps_xdg_runtime_dir_for_root_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setattr(
        service_mod.pwd,
        "getpwnam",
        lambda _name: type("Pw", (), {"pw_uid": 1000, "pw_dir": "/home/ubuntu"})(),
    )
    cmd = service_mod._systemctl("user", "enable", "octop", run_as_user="ubuntu")
    assert cmd == [
        "sudo",
        "-u",
        "ubuntu",
        "env",
        "XDG_RUNTIME_DIR=/run/user/1000",
        "systemctl",
        "--user",
        "enable",
        "octop",
    ]


def test_auto_scope_root_always_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Root is always system scope, even when SUDO_USER is set.
    monkeypatch.setattr(service_mod, "is_root", lambda: True)
    monkeypatch.setenv("SUDO_USER", "ubuntu")
    assert resolve_service_scope() == "system"


def test_persist_bind_options_merges_config(tmp_path: Path) -> None:
    home = tmp_path / "octop"
    home.mkdir()
    (home / "config.json").write_text('{"log_level": "debug"}', encoding="utf-8")
    service_mod.persist_bind_options(home, host="0.0.0.0", port=443)
    data = json.loads((home / "config.json").read_text(encoding="utf-8"))
    assert data["bind_host"] == "0.0.0.0"
    assert data["port"] == 443
    assert data["log_level"] == "debug"


def test_build_runtime_picks_user_scope_for_non_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(service_mod, "is_root", lambda: False)
    monkeypatch.setenv("OCTOP_SERVICE_SCOPE", "auto")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "octop").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(service_mod, "resolve_bind_options", lambda home=None: ("127.0.0.1", 8088))

    runtime = service_mod.build_runtime(home=tmp_path, mode="launchd")
    assert runtime.scope == "user"


# --- _write_unit: sudo path must mkdir -p the parent directory --------


def test_write_unit_sudo_path_creates_parent_dir_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: when the unit destination is unwritable and not-yet-existing
    (e.g. `~/Library/LaunchAgents` on a fresh macOS account), the sudo branch
    must `mkdir -p` the parent *before* `cp`-ing the rendered file.  Skipping
    the mkdir made the first-ever install fail silently.
    """
    runtime = replace(_runtime(tmp_path), mode="launchd", scope="user")
    destination = unit_path("launchd", scope="user", run_as_user=runtime.run_as_user)

    cmds: list[list[str]] = []

    def _fake_run_cmd(cmd: list[str], *, use_sudo: bool) -> object:
        cmds.append(cmd)

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    # Force the sudo branch regardless of the on-disk state of ~/Library.
    monkeypatch.setattr(service_mod, "_needs_sudo", lambda _p: True)
    monkeypatch.setattr(service_mod, "os", _FakeOs(root=False))
    monkeypatch.setattr(service_mod, "_run_cmd", _fake_run_cmd)

    service_mod._write_unit(runtime)

    # mkdir -p of the parent must precede the cp that depends on it.
    mkdir_index = next(
        (i for i, c in enumerate(cmds) if c[:2] == ["mkdir", "-p"]),
        -1,
    )
    cp_index = next((i for i, c in enumerate(cmds) if c and c[0] == "cp"), -1)
    assert mkdir_index >= 0, f"mkdir -p was not invoked: {cmds}"
    assert cp_index > mkdir_index, f"cp must run after mkdir: {cmds}"
    # And the mkdir target is the unit's parent directory.
    assert str(destination.parent) in cmds[mkdir_index]


class _FakeOs:
    """Minimal stand-in for `os` so we can stub `geteuid` and `W_OK` checks."""

    def __init__(self, *, root: bool) -> None:
        self._root = root

    def geteuid(self) -> int:
        return 0 if self._root else 501

    def getuid(self) -> int:
        return 501

    def access(self, _path: object, _mode: int) -> bool:
        return False  # always unwritable → forces sudo path

    def unlink(self, _path: object) -> None:
        # The tmp file is `delete=False`, so this is called in `finally`.
        return None
