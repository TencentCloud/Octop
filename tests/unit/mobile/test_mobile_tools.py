"""Unit tests for built-in mobile LangChain tools."""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langgraph.config import var_child_runnable_config

from octop.config import CapabilitiesConfig, MobileCapabilities, OctopConfig
from octop.infra.mobile.tools import build_mobile_tools


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
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    names = {t.name for t in tools}
    assert "mobile_screenshot" in names
    assert "mobile_tap" in names
    assert "mobile_handoff_to_user" in names


@pytest.mark.asyncio
async def test_mobile_tap_requires_permission() -> None:
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["browser"])
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    tap_tool = _tool_by_name(tools, "mobile_tap")
    with (
        _configurable(user="1", user_is_admin=False, locale="en"),
        patch("octop.infra.mobile.tools.mobile_status") as status,
    ):
        status.return_value = MagicMock(setup_state="ready", ok=True)
        out = await tap_tool.ainvoke({"x": 10, "y": 20})
    data = json.loads(out)
    assert "error" in data
    assert "permission" in data["error"]


@pytest.mark.asyncio
async def test_mobile_tap_success() -> None:
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["mobile"])
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    tap_tool = _tool_by_name(tools, "mobile_tap")
    with (
        _configurable(user="1", user_is_admin=False, locale="en", agent_id="agent1"),
        patch("octop.infra.mobile.tools.mobile_status") as status,
        patch("octop.infra.mobile.tools.list_devices", return_value=["emulator-5554"]),
        patch("octop.infra.mobile.tools.tap", return_value=True) as tap_fn,
    ):
        status.return_value = MagicMock(setup_state="ready", ok=True)
        out = await tap_tool.ainvoke({"x": 100, "y": 200})
    data = json.loads(out)
    assert data["ok"] is True
    tap_fn.assert_called_once()


@pytest.mark.asyncio
async def test_mobile_handoff_admin_bypass() -> None:
    user_repo = MagicMock()
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    handoff = _tool_by_name(tools, "mobile_handoff_to_user")
    with _configurable(user="1", user_is_admin=True, locale="en"):
        out = await handoff.ainvoke({"reason": "login captcha"})
    data = json.loads(out)
    assert data["handoff"] is True
    assert "login captcha" in data["message"]
