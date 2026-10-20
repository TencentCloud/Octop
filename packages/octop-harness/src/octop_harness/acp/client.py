"""ACP client callback for delegated external agents."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, NoReturn

from octop_harness.acp.models import ACPRunnerConfig, SuspendedPermission
from octop_harness.acp.permissions import ACPPermissionAdapter

MessageHandler = Callable[[dict[str, Any], bool], Awaitable[None]]


class ACPHostedClient:
    def __init__(
        self,
        *,
        runner_name: str,
        runner_config: ACPRunnerConfig,
        cwd: str,
    ) -> None:
        self.runner_name = runner_name
        self.tool_parse_mode = runner_config.tool_parse_mode
        self._permission_adapter = ACPPermissionAdapter(cwd=cwd)
        self._on_message: MessageHandler | None = None
        self._assistant_text = ""
        self._pending_permission: SuspendedPermission | None = None
        self._permission_future: asyncio.Future[Any] | None = None
        self._permission_requested = asyncio.Event()

    @property
    def pending_permission(self) -> SuspendedPermission | None:
        return self._pending_permission

    def update_cwd(self, cwd: str) -> None:
        self._permission_adapter = ACPPermissionAdapter(cwd=cwd)

    def start_prompt(self, on_message: MessageHandler) -> None:
        self._on_message = on_message
        self._assistant_text = ""
        self._pending_permission = None
        self._permission_requested.clear()

    def resume_prompt(self, on_message: MessageHandler) -> None:
        self._on_message = on_message
        self._permission_requested.clear()

    async def wait_for_permission_request(self) -> None:
        await self._permission_requested.wait()

    def resolve_permission(self, option_id: str) -> None:
        if self._pending_permission is None or self._permission_future is None:
            raise ValueError("No pending ACP permission request.")
        selected = self._permission_adapter.resolve_option_by_id(
            self._pending_permission.options,
            option_id,
        )
        if selected is None:
            raise ValueError(
                "respond requires the exact selected permission option id from the provided options.",
            )
        if not self._permission_future.done():
            self._permission_future.set_result(
                self._permission_adapter.selected_response(selected),
            )

    async def request_permission(
        self,
        options: list[Any],
        session_id: str,
        tool_call: Any,
        **_: Any,
    ) -> Any:
        _session_id = session_id
        suspended = self._permission_adapter.build_suspended_permission(
            runner=self.runner_name,
            tool_call=tool_call,
            options=options,
        )
        await self._emit_message(
            {
                "type": "permission_request",
                "title": suspended.summary or suspended.tool_name,
                "options": suspended.options,
                "tool_kind": suspended.tool_kind,
                "tool_name": suspended.tool_name,
            },
            True,
        )
        if self._permission_adapter.is_hard_blocked(tool_call):
            return self._permission_adapter.cancelled_response()

        self._pending_permission = suspended
        self._permission_requested.set()
        self._permission_future = asyncio.get_running_loop().create_future()
        try:
            return await self._permission_future
        finally:
            self._pending_permission = None
            self._permission_future = None
            self._permission_requested.clear()

    async def session_update(self, session_id: str, update: Any, **_: Any) -> None:
        from acp.schema import (
            AgentMessageChunk,
            AgentPlanUpdate,
            AgentThoughtChunk,
            AvailableCommandsUpdate,
            CurrentModeUpdate,
            ToolCallProgress,
            ToolCallStart,
            UserMessageChunk,
        )

        _session_id = session_id
        if isinstance(update, AgentMessageChunk):
            await self._accumulate_assistant_content(update.content)
            return

        if isinstance(update, AgentThoughtChunk):
            return

        if isinstance(update, ToolCallStart | ToolCallProgress):
            event = self._tool_event_from_state(update)
            if event is not None:
                await self._emit_message(event, True)
            return

        if isinstance(
            update,
            CurrentModeUpdate | AgentPlanUpdate | AvailableCommandsUpdate | UserMessageChunk,
        ):
            return

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _ = params
        self._unsupported_method(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        _ = params
        self._unsupported_method(method)

    def _unsupported_method(self, method: str) -> NoReturn:
        from acp import RequestError

        raise RequestError(code=-32601, message=f"Unsupported ACP extension method: {method}")

    async def finish_prompt(self) -> dict[str, Any] | None:
        if self._assistant_text:
            return {"type": "text", "text": self._assistant_text, "is_chunk": False}
        return None

    async def _emit_message(self, payload: dict[str, Any], is_last: bool) -> None:
        if self._on_message is None:
            return
        await self._on_message(payload, is_last)

    async def _accumulate_assistant_content(self, content: Any) -> None:
        text = self._extract_text_from_content(content)
        if text:
            self._merge_assistant_text(text)

    def _merge_assistant_text(self, text: str) -> None:
        if not text or text == self._assistant_text:
            return
        if not self._assistant_text:
            self._assistant_text = text
            return
        if text.startswith(self._assistant_text):
            self._assistant_text = text
            return
        self._assistant_text = self._assistant_text + text

    def _extract_text_from_content(self, content: Any) -> str:
        if hasattr(content, "text") and isinstance(getattr(content, "text", None), str):
            return str(content.text)
        if isinstance(content, list):
            return "".join(part for part in (self._extract_text_from_content(item) for item in content) if part)
        if isinstance(content, dict) and content.get("type") == "text":
            return str(content.get("text") or "")
        return ""

    def _tool_event_from_state(self, update: Any) -> dict[str, Any] | None:
        from acp.schema import ToolCallStart

        call_id = str(getattr(update, "tool_call_id", "") or "")
        if not call_id:
            return None
        title = str(getattr(update, "title", None) or "unknown")
        kind = str(getattr(update, "kind", None) or "other")
        return {
            "type": "tool_start" if isinstance(update, ToolCallStart) else "tool_update",
            "name": title,
            "call_id": call_id,
            "title": title,
            "kind": kind,
            "detail": title,
        }
