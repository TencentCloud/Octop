"""Local Laya install planning, log redaction, and failure reporting."""

from __future__ import annotations

import json
import shlex
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from octop.infra.agents.settings.laya_runtime import (
    LAYA_ENDPOINT,
    LAYA_VERSION,
    LayaRuntime,
    child_env,
    compatible_python,
    format_install_command,
    install_commands,
    redact,
    serve_bin,
    venv_python,
)


def test_compatible_python_prefers_312_over_octop_314() -> None:
    def which(name: str) -> str | None:
        if name == "python3.12":
            return "/usr/bin/python3.12"
        return None

    chosen = compatible_python(which=which, current_version=(3, 14))
    assert chosen == Path("/usr/bin/python3.12")


def test_compatible_python_rejects_314_when_nothing_else_exists() -> None:
    assert compatible_python(which=lambda _name: None, current_version=(3, 14)) is None


def test_format_install_command_matches_the_automatic_steps(tmp_path: Path) -> None:
    python = tmp_path / "python3.12"
    text = format_install_command(python, tmp_path)
    for argv in install_commands(python, venv_python(tmp_path)):
        assert shlex.join(argv) in text
    assert f"laya[serve]=={LAYA_VERSION}" in text
    assert "https://download.pytorch.org/whl/cpu" in text
    assert "LAYA_MODELS=multilingual" in text
    assert shlex.quote(str(serve_bin(tmp_path))) in text


def test_install_commands_use_cpu_torch_and_pinned_laya(tmp_path: Path) -> None:
    python = tmp_path / "venv" / "bin" / "python"
    commands = install_commands(Path("python3"), python)
    assert commands[0][:3] == ["python3", "-m", "venv"]
    assert commands[2][-2:] == ["--index-url", "https://download.pytorch.org/whl/cpu"]
    assert commands[3][-1] == f"laya[serve]=={LAYA_VERSION}"


def test_child_env_does_not_forward_api_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAYA_API_KEY", "secret-value")
    monkeypatch.setenv("HF_TOKEN", "hf-secret")
    env = child_env(tmp_path)
    assert "LAYA_API_KEY" not in env
    assert "HF_TOKEN" not in env
    assert env["LAYA_HOST"] == "127.0.0.1"
    assert env["LAYA_MODELS"] == "multilingual"
    assert "secret-value" not in env.values()


def test_redact_hides_credentials() -> None:
    assert "secret-value" not in redact("LAYA_API_KEY=secret-value")
    assert "[redacted]" in redact("Authorization: Bearer secret-value")


async def _events(runtime: LayaRuntime) -> list[dict[str, object]]:
    parsed: list[dict[str, object]] = []

    async def _collect() -> AsyncIterator[str]:
        async for chunk in runtime.install_events("en"):
            yield chunk

    async for chunk in _collect():
        for line in chunk.splitlines():
            if line.startswith("data: "):
                parsed.append(json.loads(line[6:]))
    return parsed


@pytest.mark.asyncio
async def test_install_reports_ready_and_keeps_log(tmp_path: Path) -> None:
    binary = serve_bin(tmp_path)
    started = False

    async def runner(
        argv: list[str],
        _env: dict[str, str],
        _emit: object,
    ) -> int:
        if any(part.startswith("laya[serve]==") for part in argv):
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("laya", encoding="utf-8")
        return 0

    async def starter() -> None:
        nonlocal started
        started = True

    runtime = LayaRuntime(
        tmp_path,
        runner=runner,
        health_check=lambda: started,
        port_busy=lambda: False,
        starter=starter,
        health_timeout=1,
        poll_interval=0.01,
    )
    events = await _events(runtime)
    assert started is True
    assert events[-1]["success"] is True
    assert events[-1]["endpoint"] == LAYA_ENDPOINT
    assert (tmp_path / "install.log").is_file()
    status = await runtime.status()
    assert status["phase"] == "running"
    assert status["logs"]


@pytest.mark.asyncio
async def test_install_keeps_failure_log_when_port_is_busy(tmp_path: Path) -> None:
    called = False

    async def runner(
        _argv: list[str],
        _env: dict[str, str],
        _emit: object,
    ) -> int:
        nonlocal called
        called = True
        return 0

    runtime = LayaRuntime(
        tmp_path,
        runner=runner,
        health_check=lambda: False,
        port_busy=lambda: True,
    )
    events = await _events(runtime)
    assert called is False
    assert events[-1]["success"] is False
    assert any("8000" in str(item.get("log", "")) for item in events)
    status = await runtime.status()
    assert status["phase"] == "failed"


@pytest.mark.asyncio
async def test_install_explains_missing_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.agents.settings.laya_runtime.compatible_python",
        lambda: None,
    )
    runtime = LayaRuntime(
        tmp_path,
        health_check=lambda: False,
        port_busy=lambda: False,
    )
    events = await _events(runtime)
    assert events[-1]["success"] is False
    assert any("3.12" in str(item.get("log", "")) for item in events)


@pytest.mark.asyncio
async def test_install_reports_disk_shortage_without_downloading(tmp_path: Path) -> None:
    runtime = LayaRuntime(
        tmp_path,
        health_check=lambda: False,
        port_busy=lambda: False,
        free_bytes=lambda: 1024,
    )
    events = await _events(runtime)
    assert events[-1]["success"] is False
    assert any("GB" in str(item.get("log", "")) for item in events)
