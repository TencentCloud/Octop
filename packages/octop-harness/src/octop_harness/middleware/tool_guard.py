"""Middleware that scans tool parameters before execution."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command, interrupt

from octop_harness.security.tool_guard.engine import (
    ToolGuardEngine,
    ToolGuardMode,
    ToolGuardResult,
    build_tool_guard_hitl_request,
    format_block_message,
)

logger = logging.getLogger(__name__)


class ToolGuardMiddleware(AgentMiddleware[Any, Any]):
    """Block, warn, or pause for human approval on risky shell command parameters."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        mode: ToolGuardMode = "block",
        rules_dir: Path | str | None = None,
    ) -> None:
        super().__init__()
        self._engine = ToolGuardEngine(enabled=enabled, mode=mode, rules_dir=rules_dir)

    def configure(self, *, enabled: bool | None = None, mode: ToolGuardMode | None = None) -> None:
        self._engine.configure(enabled=enabled, mode=mode)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        tool_name = str(tool_call.get("name", ""))
        raw_params = tool_call.get("args") or {}
        params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

        result = self._engine.guard(tool_name, params)
        if result is None:
            return await handler(request)

        if self._engine.mode == "require_approval" and self._engine.should_block(result):
            return await self._await_approval(request, handler, result)

        if self._engine.should_block(result):
            message = format_block_message(result, mode=self._engine.mode)
            logger.warning(
                "Tool guard blocked %s (%d finding(s), mode=%s)",
                tool_name,
                len(result.findings),
                self._engine.mode,
            )
            return ToolMessage(
                content=message,
                tool_call_id=str(tool_call.get("id", "")),
                status="error",
            )

        if result.findings and self._engine.mode == "warn":
            logger.warning(
                "Tool guard warnings for %s: %s",
                tool_name,
                [f.rule_id for f in result.findings],
            )

        return await handler(request)

    async def _await_approval(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
        result: ToolGuardResult,
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        tool_name = str(tool_call.get("name", ""))
        hitl_request = build_tool_guard_hitl_request(result)
        logger.warning(
            "Tool guard paused %s for approval (%d finding(s))",
            tool_name,
            len(result.findings),
        )
        response = interrupt(hitl_request)
        decisions = response.get("decisions") if isinstance(response, dict) else None
        if not isinstance(decisions, list) or not decisions:
            msg = "Tool guard approval did not receive a human decision."
            raise ValueError(msg)

        decision = decisions[0]
        if not isinstance(decision, dict):
            msg = f"Unexpected tool guard approval decision: {decision!r}"
            raise ValueError(msg)

        if decision.get("type") == "approve":
            return await handler(request)

        reject_message = decision.get("message")
        if not isinstance(reject_message, str) or not reject_message.strip():
            reject_message = (
                f"Tool call rejected after security review for `{tool_name}` (command guard detected risky parameters)."
            )
        return ToolMessage(
            content=reject_message,
            tool_call_id=str(tool_call.get("id", "")),
            status="error",
        )


__all__ = ["ToolGuardMiddleware"]
