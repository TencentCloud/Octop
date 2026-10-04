"""Unit tests for built-in mobile LangChain tools."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
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
    from octop.infra.mobile.agent_control import set_mobile_agent_control

    set_mobile_agent_control(enabled=True, device="emulator-5554")
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["mobile"])
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo)
    tap_tool = _tool_by_name(tools, "mobile_tap")
    try:
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
    finally:
        set_mobile_agent_control(enabled=False, device=None)


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


# A real ``adb exec-out screencap -p`` payload is a multi-megabyte PNG; keep the
# test payload small but non-trivial so the write is still a genuine disk write.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * (256 * 1024)


@pytest.mark.asyncio
async def test_mobile_screenshot_writes_off_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.mobile.agent_control import set_mobile_agent_control

    set_mobile_agent_control(enabled=True, device="emulator-5554")
    user_repo = MagicMock()
    user_repo.get.return_value = SimpleNamespace(is_admin=False, permissions=["mobile"])
    paths = MagicMock()
    paths.agent_workspace.return_value = tmp_path
    with patch("octop.infra.mobile.tools.find_adb", return_value="/adb"):
        tools = build_mobile_tools(_enabled_config(), user_repo=user_repo, paths=paths)
    shot = _tool_by_name(tools, "mobile_screenshot")

    loop_thread = threading.get_ident()
    write_threads: list[int] = []
    mkdir_threads: list[int] = []
    real_write_bytes = Path.write_bytes
    real_mkdir = Path.mkdir

    def spy_write_bytes(self: Path, data: bytes) -> int:
        write_threads.append(threading.get_ident())
        return real_write_bytes(self, data)

    def spy_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        mkdir_threads.append(threading.get_ident())
        real_mkdir(self, mode, parents, exist_ok)

    monkeypatch.setattr(Path, "write_bytes", spy_write_bytes)
    monkeypatch.setattr(Path, "mkdir", spy_mkdir)

    try:
        with (
            _configurable(user="1", user_is_admin=False, locale="en", agent_id="agent1"),
            patch("octop.infra.mobile.tools.mobile_status") as status,
            patch("octop.infra.mobile.tools.list_devices", return_value=["emulator-5554"]),
            patch("octop.infra.mobile.tools.screencap_png", return_value=_PNG_BYTES),
        ):
            status.return_value = MagicMock(setup_state="ready", ok=True)
            out = await shot.ainvoke({})
        data = json.loads(out)
        assert data["path"].startswith("mobile-screenshots/")
        assert (tmp_path / data["path"]).read_bytes() == _PNG_BYTES
    finally:
        set_mobile_agent_control(enabled=False, device=None)

    assert write_threads, "the screenshot must be written to disk"
    assert mkdir_threads, "the screenshot directory must be created"
    assert loop_thread not in write_threads, "screenshot writes must run off the event loop"
    assert loop_thread not in mkdir_threads, "screenshot mkdirs must run off the event loop"
