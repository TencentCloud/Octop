"""tests/unit/gateway/test_turn_watchdog.py — TURN watchdog recovery logic."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from octop.infra.gateway.ws.turn_watchdog import TurnWatchdog
from octop.infra.gateway.ws.ws_hub import WebSocketHub


class _FakeAgentManager:
    def __init__(self) -> None:
        self.cancelled: list[tuple[str, str]] = []

    def cancel_stream(self, agent_id: str, thread_id: str) -> None:
        self.cancelled.append((agent_id, thread_id))


class _FakeSession:
    channel_id = "wx123"
    channel_type = "weixin"

    def to_channel_subject(self) -> str:
        return "subject-object"


class _FakeGateway:
    thread_registry: Any

    def __init__(self) -> None:
        self.pushed: list[tuple[str, str, str]] = []

    async def push_text(self, channel_type: str, channel_id: str, subject: str, text: str) -> None:
        self.pushed.append((channel_type, channel_id, text))


async def _scan(wd: TurnWatchdog) -> None:
    wd._scan_once()
    await asyncio.sleep(0.15)


@pytest.mark.asyncio
async def test_stall_recovery_pushes_error_done_and_cancels() -> None:
    hub = WebSocketHub()
    sent: list[dict[str, Any]] = []

    async def capture(frame: dict[str, Any]) -> None:
        sent.append(frame)

    hub.register("c1", capture, user_id=1)
    hub.subscribe("t1", "c1")
    hub.mark_turn_active("t1", agent_id="agentA")
    hub.get_active_turn("t1").last_progress_at -= 400

    am = _FakeAgentManager()
    wd = TurnWatchdog(hub=hub, agent_manager=am, stall_seconds=300, interval_seconds=60)
    await _scan(wd)

    assert [f.get("type") for f in sent] == ["error", "done"]
    assert am.cancelled == [("agentA", "t1")]
    assert not hub.is_turn_active("t1")


@pytest.mark.asyncio
async def test_healthy_turn_untouched() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("t3", agent_id="agentC")
    am = _FakeAgentManager()
    wd = TurnWatchdog(hub=hub, agent_manager=am, stall_seconds=300, interval_seconds=60)
    await _scan(wd)
    assert hub.is_turn_active("t3")
    assert am.cancelled == []


@pytest.mark.asyncio
async def test_tool_phase_uses_longer_stall_threshold() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("t1", agent_id="agentA")
    hub.mark_tool_state("t1", True)
    hub.get_active_turn("t1").last_progress_at -= 400  # > model stall, < tool stall

    am = _FakeAgentManager()
    wd = TurnWatchdog(
        hub=hub,
        agent_manager=am,
        stall_seconds=300,
        tool_stall_seconds=900,
        interval_seconds=60,
    )
    await _scan(wd)
    assert am.cancelled == []
    assert hub.is_turn_active("t1")


@pytest.mark.asyncio
async def test_model_phase_cap_excludes_tool_time() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("t2", agent_id="agentB")
    rec = hub.get_active_turn("t2")
    rec.started_at -= 7200
    rec.last_progress_at = time.monotonic() - 1
    rec.tool_budget_spent = 5400  # 1.5h in tools of 2h total

    am = _FakeAgentManager()
    wd = TurnWatchdog(
        hub=hub,
        agent_manager=am,
        stall_seconds=300,
        max_seconds=1800,
        interval_seconds=60,
    )
    await _scan(wd)
    assert am.cancelled == [("agentB", "t2")]


@pytest.mark.asyncio
async def test_notified_zombie_not_resurrected_and_force_cleared() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("t4", agent_id="agentD")
    rec = hub.get_active_turn("t4")
    rec.notified = True
    rec.notified_at = time.monotonic() - 200  # past grace

    am = _FakeAgentManager()
    wd = TurnWatchdog(
        hub=hub,
        agent_manager=am,
        stall_seconds=300,
        notified_grace_seconds=120,
        interval_seconds=60,
    )
    await _scan(wd)
    assert hub.get_active_turn("t4") is None, "zombie record must be force-cleared"

    # After cleanup, a fresh turn registers normally.
    hub.mark_turn_active("t4", agent_id="agentD")
    assert hub.is_turn_active("t4")


@pytest.mark.asyncio
async def test_im_turn_recovery_pushes_notice_and_cancels() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("thrX", agent_id="agentA", session_key="sk:im")
    hub.get_active_turn("thrX").last_progress_at -= 400

    am = _FakeAgentManager()

    class _Registry:
        def get_session(self, session_key: str) -> _FakeSession | None:
            return _FakeSession() if session_key == "sk:im" else None

    gw = _FakeGateway()
    gw.thread_registry = _Registry()
    wd = TurnWatchdog(
        hub=hub,
        agent_manager=am,
        stall_seconds=300,
        gateway=gw,
        interval_seconds=60,
    )
    await _scan(wd)

    assert am.cancelled == [("agentA", "thrX")]
    assert gw.pushed and gw.pushed[0][0] == "weixin"
    assert "超时" in gw.pushed[0][2]


@pytest.mark.asyncio
async def test_ws_turn_recovery_no_im_notice() -> None:
    hub = WebSocketHub()
    hub.mark_turn_active("thrY", agent_id="agentB")  # no session_key (dashboard WS)
    hub.get_active_turn("thrY").last_progress_at -= 400

    am = _FakeAgentManager()
    gw = _FakeGateway()
    gw.thread_registry = type("R", (), {"get_session": lambda self, sk: None})()
    wd = TurnWatchdog(
        hub=hub,
        agent_manager=am,
        stall_seconds=300,
        gateway=gw,
        interval_seconds=60,
    )
    await _scan(wd)

    assert am.cancelled == [("agentB", "thrY")]
    assert gw.pushed == []
