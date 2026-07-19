"""Tests for `octop service`."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.infra.setup.service import (
    ServiceRuntime,
    ServiceStatus,
    launchd_domain,
    unit_path,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX service management")


def _runtime(tmp_path: Path, *, mode: str = "systemd", scope: str = "system") -> ServiceRuntime:
    octop_bin = tmp_path / "bin" / "octop"
    octop_bin.parent.mkdir(parents=True)
    octop_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    return ServiceRuntime(
        mode=mode,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=8088,
        home=tmp_path,
        octop_bin=octop_bin,
        run_as_user=getpass.getuser(),
        scope=scope,  # type: ignore[arg-type]
    )


def test_service_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["service", "--help"])
    assert result.exit_code == 0
    for cmd in ("start", "stop", "restart", "status"):
        assert cmd in result.output


def test_service_start_installs_and_starts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import octop.cli.commands.service as service_cmd

    runtime = _runtime(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(service_cmd, "build_runtime", lambda **kw: runtime)
    monkeypatch.setattr(
        service_cmd,
        "install_service",
        lambda rt, force=False: calls.append(f"install:{force}"),
    )
    monkeypatch.setattr(service_cmd, "start_service", lambda rt: calls.append("start"))
    monkeypatch.setattr(
        service_cmd,
        "collect_service_status",
        lambda rt, check_health=True, health_retries=1, health_delay_seconds=1.5: ServiceStatus(
            mode="systemd",
            installed=True,
            active=True,
            enabled=True,
            detail="active",
            health_ok=True,
            health_detail="{'ok': true}",
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "start"])
    assert result.exit_code == 0, result.output
    assert calls == ["install:False", "start"]
    assert "active=True" in result.output


def test_service_start_emits_diagnostic_hint_when_health_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On health-check failure, surface a hint pointing to the service logs so
    users don't have to dig through launchd/systemd docs."""
    import octop.cli.commands.service as service_cmd

    runtime = _runtime(tmp_path)
    monkeypatch.setattr(service_cmd, "build_runtime", lambda **kw: runtime)
    monkeypatch.setattr(service_cmd, "install_service", lambda rt, force=False: None)
    monkeypatch.setattr(service_cmd, "start_service", lambda rt: None)
    monkeypatch.setattr(
        service_cmd,
        "collect_service_status",
        lambda rt, check_health=True, health_retries=1, health_delay_seconds=1.5: ServiceStatus(
            mode="systemd",
            installed=True,
            active=True,
            enabled=True,
            detail="active",
            health_ok=False,
            health_detail="connection refused",
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "start"])
    # `start` is warn-only, so exit code stays 0 but the hint must appear.
    assert result.exit_code == 0, result.output
    assert "connection refused" in result.output
    assert "journalctl -u octop" in result.output


def test_service_status_exits_when_health_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import octop.cli.commands.service as service_cmd

    runtime = _runtime(tmp_path)
    monkeypatch.setattr(service_cmd, "build_runtime", lambda **kw: runtime)
    monkeypatch.setattr(
        service_cmd,
        "collect_service_status",
        lambda rt, check_health=True, health_retries=1, health_delay_seconds=1.5: ServiceStatus(
            mode="systemd",
            installed=True,
            active=True,
            enabled=True,
            detail="active",
            health_ok=False,
            health_detail="connection refused",
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "status"])
    assert result.exit_code == 1
    assert "connection refused" in result.output


def test_service_start_forwards_user_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`--scope user` must reach build_runtime so the user-domain path is used."""
    import octop.cli.commands.service as service_cmd

    runtime = _runtime(tmp_path, mode="launchd", scope="user")
    captured_kwargs: dict[str, object] = {}

    def _fake_build_runtime(**kwargs: object) -> ServiceRuntime:
        captured_kwargs.update(kwargs)
        return runtime

    monkeypatch.setattr(service_cmd, "build_runtime", _fake_build_runtime)
    monkeypatch.setattr(service_cmd, "install_service", lambda rt, force=False: None)
    monkeypatch.setattr(service_cmd, "start_service", lambda rt: None)
    monkeypatch.setattr(
        service_cmd,
        "collect_service_status",
        lambda rt, check_health=True, health_retries=1, health_delay_seconds=1.5: ServiceStatus(
            mode="launchd",
            installed=True,
            active=True,
            enabled=True,
            detail="running",
            health_ok=True,
            health_detail="{'ok': true}",
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "start", "--scope", "user"])
    assert result.exit_code == 0, result.output
    assert captured_kwargs.get("scope") == "user"
    # And the output must tell the user where the plist lives.
    assert str(unit_path("launchd", scope="user", run_as_user=runtime.run_as_user)) in result.output
    assert launchd_domain("user") in result.output


def test_service_status_shows_plist_and_domain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`status` must report plist path and launchd domain so users can see
    which scope is being inspected."""
    import octop.cli.commands.service as service_cmd

    runtime = _runtime(tmp_path, mode="launchd", scope="user")
    monkeypatch.setattr(service_cmd, "build_runtime", lambda **kw: runtime)
    monkeypatch.setattr(
        service_cmd,
        "collect_service_status",
        lambda rt, check_health=True, health_retries=1, health_delay_seconds=1.5: ServiceStatus(
            mode="launchd",
            installed=True,
            active=True,
            enabled=True,
            detail="running",
            health_ok=True,
            health_detail="{'ok': true}",
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["service", "status", "--scope", "user"])
    assert result.exit_code == 0, result.output
    assert str(unit_path("launchd", scope="user", run_as_user=runtime.run_as_user)) in result.output
    assert launchd_domain("user") in result.output


def test_service_status_rejects_garbage_scope() -> None:
    """Click-level validation — unknown scopes never reach build_runtime."""
    runner = CliRunner()
    result = runner.invoke(cli, ["service", "status", "--scope", "nonsense"])
    assert result.exit_code != 0
    assert "scope" in result.output.lower()
