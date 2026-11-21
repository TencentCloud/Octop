"""Host ACP probe / install status, without spawning a real CLI."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.agents.settings import acp_host


@pytest.mark.asyncio
async def test_ready_when_handshake_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "linux")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: f"/bin/{name}")

    async def ok(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
        assert command == "opencode"
        assert args == ["acp"]
        assert env
        return True, ""

    monkeypatch.setattr(acp_host, "_handshake", ok)
    result = await acp_host.acp_host_status(runner="opencode", locale="zh")
    assert result["status"] == "ready"
    assert result["acp_ok"] is True
    assert result["can_auto_install"] is False
    assert "无需再安装" in result["agent_prompt"]
    assert "opencode.ai/v2/install" in result["scripts"]["linux"]
    assert result["scripts"]["win32"].startswith("#")


@pytest.mark.asyncio
async def test_missing_binary_skips_handshake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "darwin")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: None)
    monkeypatch.setattr(acp_host, "_shell_ok", lambda plat: True)

    async def boom(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise AssertionError("handshake should not run")

    monkeypatch.setattr(acp_host, "_handshake", boom)
    result = await acp_host.acp_host_status(runner="kimi_code", locale="en")
    assert result["status"] == "missing"
    assert result["reason"] == "command_missing"
    assert result["can_auto_install"] is True
    assert "install.sh" in result["install_script"]
    assert "Install Kimi Code" in result["agent_prompt"]


@pytest.mark.asyncio
async def test_adapter_requires_agent_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "linux")

    def which(name: str, env: dict[str, str]) -> str | None:
        _ = env
        return "/usr/bin/npx" if name == "npx" else None

    monkeypatch.setattr(acp_host, "_which", which)

    async def boom(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise AssertionError("handshake should not run")

    monkeypatch.setattr(acp_host, "_handshake", boom)
    result = await acp_host.acp_host_status(runner="claude_code")
    assert result["status"] == "missing"
    assert result["reason"] == "agent_missing"
    assert "claude.ai/install.sh" in result["scripts"]["darwin"]


@pytest.mark.asyncio
async def test_handshake_failure_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "linux")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: f"/bin/{name}")

    async def fail(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        return False, "timed out waiting for ACP initialize"

    monkeypatch.setattr(acp_host, "_handshake", fail)
    result = await acp_host.acp_host_status(
        runner="custom",
        command="my-agent",
        args=["--acp"],
        locale="en",
    )
    assert result["status"] == "degraded"
    assert result["reason"] == "handshake_timeout"
    assert result["install_script"] == ""
    assert result["can_auto_install"] is False
    assert "my-agent" in result["agent_prompt"]


@pytest.mark.asyncio
async def test_install_then_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "win32")
    monkeypatch.setattr(acp_host, "_shell_ok", lambda plat: True)
    present = {"ok": False}

    def which(name: str, env: dict[str, str]) -> str | None:
        _ = env
        if present["ok"] and name == "agent":
            return r"C:\agent.cmd"
        return None

    def install(script: str, plat: str) -> tuple[bool, str]:
        assert plat == "win32"
        assert "cursor.com/install?win32=true" in script
        present["ok"] = True
        return True, ""

    async def ok(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
        assert command == "agent"
        assert args == ["acp"]
        assert env
        return True, ""

    monkeypatch.setattr(acp_host, "_which", which)
    monkeypatch.setattr(acp_host, "_run_install", install)
    monkeypatch.setattr(acp_host, "_handshake", ok)
    result = await acp_host.acp_host_status(runner="cursor_cli", attempt_install=True, locale="zh")
    assert result["status"] == "installed"
    assert "irm" in result["scripts"]["win32"]


@pytest.mark.asyncio
async def test_ask_returns_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_which", lambda name, env: f"/bin/{name}")

    async def answer(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
        assert command == "opencode"
        assert args == ["acp"]
        assert env
        return True, "I am OpenCode."

    monkeypatch.setattr(acp_host, "_ask", answer)
    result = await acp_host.acp_host_ask(runner="opencode")
    assert result["ok"] is True
    assert result["prompt"] == "who are you?"
    assert result["text"] == "I am OpenCode."


@pytest.mark.asyncio
async def test_ask_skips_when_command_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_which", lambda name, env: None)

    async def boom(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise AssertionError("ask should not spawn")

    monkeypatch.setattr(acp_host, "_ask", boom)
    result = await acp_host.acp_host_ask(runner="kimi_code")
    assert result["ok"] is False
    assert result["reason"] == "command_missing"
    assert result["prompt"] == "who are you?"


@pytest.mark.asyncio
async def test_windows_opencode_skips_auto_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "win32")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: None)

    def install(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise AssertionError("opencode has no Windows auto installer")

    monkeypatch.setattr(acp_host, "_run_install", install)
    result = await acp_host.acp_host_status(runner="opencode", attempt_install=True)
    assert result["status"] == "skipped"
    assert result["can_auto_install"] is False
    assert "WSL" in result["install_script"]


def test_acp_sdk_error_reports_missing_runtime_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = SimpleNamespace(PROTOCOL_VERSION="1", spawn_agent_process=lambda **_: None)
    monkeypatch.setattr(
        acp_host,
        "importlib",
        SimpleNamespace(import_module=lambda _name: module),
    )
    error = acp_host._acp_sdk_error()
    assert "text_block" in error
    assert "agent-client-protocol>=0.11.0" in error


@pytest.mark.asyncio
async def test_handshake_skips_spawn_when_sdk_is_incompatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acp_host, "_acp_sdk_error", lambda: "incompatible ACP SDK")
    ok, detail = await acp_host._handshake("my-agent", ["--acp"], {})
    assert ok is False
    assert detail == "incompatible ACP SDK"


@pytest.mark.asyncio
async def test_probe_surfaces_incompatible_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "linux")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: f"/bin/{name}")
    monkeypatch.setattr(
        acp_host,
        "_acp_sdk_error",
        lambda: "incompatible ACP SDK: missing text_block",
    )
    result = await acp_host.acp_host_status(
        runner="custom",
        command="my-agent",
        args=["--acp"],
        locale="en",
    )
    assert result["status"] == "degraded"
    assert result["reason"] == "handshake_failed"
    assert "text_block" in result["detail"]


@pytest.mark.asyncio
async def test_qwen_code_launches_with_acp_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acp_host, "_platform_key", lambda: "darwin")
    monkeypatch.setattr(acp_host, "_which", lambda name, env: f"/bin/{name}")

    async def ok(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
        assert command == "qwen"
        assert args == ["--acp"]
        assert env
        return True, ""

    monkeypatch.setattr(acp_host, "_handshake", ok)
    result = await acp_host.acp_host_status(runner="qwen_code", locale="en")
    assert result["status"] == "ready"
    assert "npm install -g @qwen-code/qwen-code" in result["scripts"]["darwin"]
