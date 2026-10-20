"""Tests for ToolGuardMiddleware approval flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop_harness.middleware.tool_guard import ToolGuardMiddleware
from octop_harness.security.tool_guard import ToolGuardEngine


def _request(tool_name: str = "bash", command: str = "rm -rf /") -> ToolCallRequest:
    req = MagicMock(spec=ToolCallRequest)
    req.tool_call = {
        "name": tool_name,
        "args": {"command": command},
        "id": "call-1",
        "type": "tool_call",
    }
    return req


@pytest.mark.asyncio
async def test_require_approval_interrupt_then_approve_executes_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octop_harness.middleware.tool_guard.interrupt",
        lambda _req: {"decisions": [{"type": "approve"}]},
    )
    middleware = ToolGuardMiddleware(enabled=True, mode="require_approval")
    handler = AsyncMock(return_value=ToolMessage(content="ok", tool_call_id="call-1"))

    result = await middleware.awrap_tool_call(_request(), handler)

    handler.assert_awaited_once()
    assert isinstance(result, ToolMessage)
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_require_approval_interrupt_then_reject_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octop_harness.middleware.tool_guard.interrupt",
        lambda _req: {"decisions": [{"type": "reject", "message": "too risky"}]},
    )
    middleware = ToolGuardMiddleware(enabled=True, mode="require_approval")
    handler = AsyncMock()

    result = await middleware.awrap_tool_call(_request(), handler)

    handler.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.content == "too risky"


@pytest.mark.asyncio
async def test_block_mode_does_not_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _fail_interrupt(_req: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {"decisions": [{"type": "approve"}]}

    monkeypatch.setattr("octop_harness.middleware.tool_guard.interrupt", _fail_interrupt)
    middleware = ToolGuardMiddleware(enabled=True, mode="block")
    handler = AsyncMock()

    result = await middleware.awrap_tool_call(_request(), handler)

    assert called is False
    handler.assert_not_awaited()
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_require_approval_passes_hitl_request_to_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, object]] = []

    def _capture(req: dict[str, object]) -> dict[str, object]:
        captured.append(req)
        return {"decisions": [{"type": "approve"}]}

    monkeypatch.setattr("octop_harness.middleware.tool_guard.interrupt", _capture)
    middleware = ToolGuardMiddleware(enabled=True, mode="require_approval")
    handler = AsyncMock(return_value=ToolMessage(content="ok", tool_call_id="call-1"))

    await middleware.awrap_tool_call(_request(), handler)

    assert len(captured) == 1
    assert captured[0]["action_requests"][0]["name"] == "bash"  # type: ignore[index]
    assert captured[0]["review_configs"][0]["allowed_decisions"] == ["approve", "reject"]  # type: ignore[index]


def test_engine_block_mode_does_not_use_require_approval_path() -> None:
    engine = ToolGuardEngine(enabled=True, mode="block")
    result = engine.guard("bash", {"command": "ls -la"})
    assert result is not None
    assert result.is_safe
    assert not engine.should_block(result)
