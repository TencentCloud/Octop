"""Unit tests for built-in mobile LangChain tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langgraph.config import var_child_runnable_config

from octop.config import CapabilitiesConfig, MobileCapabilities, OctopConfig
from octop.infra.control.mobile.tools import build_mobile_tools

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-payload"


@contextmanager
def _configurable(**kwargs: object):
    token = var_child_runnable_config.set({"configurable": kwargs})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def _enabled_config() -> OctopConfig:
    return OctopConfig(
        capabilities=CapabilitiesConfig(
            mobile=MobileCapabilities(
                enabled=True,
                backend="physical",
                probed_at="2026-01-01T00:00:00Z",
            )
        )
    )


def _tool_by_name(tools: list, name: str):
    for tool in tools:
        if tool.name == name:
            return tool
    raise KeyError(name)


def test_build_mobile_tools_empty_when_disabled() -> None:
    cfg = OctopConfig()
    tools = build_mobile_tools(cfg, user_repo=MagicMock())
    assert tools == []


def test_build_mobile_tools_registers_when_adb_present() -> None:
    user_repo = MagicMock()
    with patch("octop.infra.control.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    names = {t.name for t in tools}
    assert "mobile_screenshot" in names
    assert "mobile_tap" in names
    assert "mobile_handoff_to_user" in names


@pytest.mark.asyncio
async def test_mobile_tap_requires_permission() -> None:
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["browser"])
    with patch("octop.infra.control.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    tap_tool = _tool_by_name(tools, "mobile_tap")
    with (
        _configurable(user="1", user_is_admin=False, locale="en"),
        patch("octop.infra.control.mobile.tools.mobile_status") as status,
    ):
        status.return_value = MagicMock(setup_state="ready", ok=True)
        out = await tap_tool.ainvoke({"x": 10, "y": 20})
    data = json.loads(out)
    assert "error" in data
    assert "permission" in data["error"]


@pytest.mark.asyncio
async def test_mobile_tap_success() -> None:
    from octop.infra.control.mobile.agent_control import set_mobile_agent_control

    set_mobile_agent_control(enabled=True, device="emulator-5554")
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["mobile"])
    with patch("octop.infra.control.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    tap_tool = _tool_by_name(tools, "mobile_tap")
    try:
        with (
            _configurable(user="1", user_is_admin=False, locale="en", agent_id="agent1"),
            patch("octop.infra.control.mobile.tools.mobile_status") as status,
            patch("octop.infra.control.mobile.tools.list_devices", return_value=["emulator-5554"]),
            patch("octop.infra.control.mobile.tools.tap", return_value=True) as tap_fn,
        ):
            status.return_value = MagicMock(setup_state="ready", ok=True)
            out = await tap_tool.ainvoke({"x": 100, "y": 200})
        data = json.loads(out)
        assert data["ok"] is True
        tap_fn.assert_called_once()
    finally:
        set_mobile_agent_control(enabled=False, device=None)


@pytest.mark.asyncio
async def test_mobile_handoff_admin_bypass() -> None:
    user_repo = MagicMock()
    with patch("octop.infra.control.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    handoff = _tool_by_name(tools, "mobile_handoff_to_user")
    with _configurable(user="1", user_is_admin=True, locale="en"):
        out = await handoff.ainvoke({"reason": "login captcha"})
    data = json.loads(out)
    assert data["handoff"] is True
    assert "login captcha" in data["message"]


def _local_workspace(tmp_path):
    from octop_harness.backends import resolve_backend
    from octop_harness.backends.workspace import BackendWorkspace

    from octop.infra.backend.compat import adapt_backend_protocol

    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    spec = {"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": True}
    return BackendWorkspace(
        adapt_backend_protocol(resolve_backend(spec, workspace_dir=ws_root)), ws_root
    )


async def _screenshot_tool(workspace_for):
    user_repo = MagicMock()
    with patch("octop.infra.control.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(
            _enabled_config(), user_repo=user_repo, workspace_for=workspace_for
        )
    return _tool_by_name(tools, "mobile_screenshot")


async def _invoke_screenshot(tool: object) -> dict:
    from octop.infra.control.mobile.agent_control import set_mobile_agent_control

    set_mobile_agent_control(enabled=True, device="emulator-5554")
    try:
        with (
            _configurable(user="1", user_is_admin=True, locale="en", agent_id="agent1"),
            patch("octop.infra.control.mobile.tools.mobile_status") as status,
            patch("octop.infra.control.mobile.tools.list_devices", return_value=["emulator-5554"]),
            patch("octop.infra.control.mobile.tools.screencap_png", return_value=_PNG_BYTES),
        ):
            status.return_value = MagicMock(setup_state="ready", ok=True)
            return json.loads(await tool.ainvoke({}))
    finally:
        set_mobile_agent_control(enabled=False, device=None)


@pytest.mark.asyncio
async def test_mobile_screenshot_lands_in_agent_workspace(tmp_path, monkeypatch) -> None:
    """Regression for #2334: the PNG must land in the agent's real workspace,
    never in the default ``{OCTOP_HOME}/agents/<id>/`` host dir."""
    from octop.infra.utils.paths import PathLayout

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    workspace = _local_workspace(tmp_path)
    tool = await _screenshot_tool(lambda agent_id: workspace if agent_id == "agent1" else None)

    data = await _invoke_screenshot(tool)

    assert data["path"].startswith("mobile-screenshots/mobile_") and data["path"].endswith(".png")
    saved = workspace.workspace_dir / data["path"]
    assert saved.read_bytes() == _PNG_BYTES
    default_dir = PathLayout.from_env().agent_workspace("agent1") / "mobile-screenshots"
    assert not default_dir.exists()


@pytest.mark.asyncio
async def test_mobile_screenshot_unique_names_same_second(tmp_path) -> None:
    workspace = _local_workspace(tmp_path)
    tool = await _screenshot_tool(lambda agent_id: workspace)

    first = await _invoke_screenshot(tool)
    second = await _invoke_screenshot(tool)

    assert first["path"] != second["path"]
    assert (workspace.workspace_dir / first["path"]).read_bytes() == _PNG_BYTES
    assert (workspace.workspace_dir / second["path"]).read_bytes() == _PNG_BYTES


@pytest.mark.asyncio
async def test_mobile_screenshot_base64_without_workspace() -> None:
    tool = await _screenshot_tool(None)

    data = await _invoke_screenshot(tool)

    assert "image_base64" in data
    assert "path" not in data
