"""Stop a turn that repeats one tool call with the same arguments.

A normal turn may call many different tools. This middleware only counts a
streak of the same tool and the same arguments. A different tool, different
arguments, or a model reply with no tool call starts the streak over.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, NotRequired, override

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.channels.untracked_value import UntrackedValue

_STREAK_KEY = "tool_call_streak"


class ConsecutiveToolCallState(AgentState[Any]):
    """Run-local streak. ``UntrackedValue`` drops it at the next user turn."""

    tool_call_streak: NotRequired[Annotated[dict[str, Any], UntrackedValue, PrivateStateAttr]]


def tool_call_signature(tool_call: dict[str, Any]) -> str:
    """Stable identity of one tool invocation: name plus arguments."""
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args")
    payload = args if isinstance(args, dict) else {"__args__": args}
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = str(payload)
    return f"{name}\n{encoded}"


class ConsecutiveToolCallMiddleware(AgentMiddleware[ConsecutiveToolCallState, Any, Any]):
    """End the turn when one identical tool call repeats past ``limit``."""

    state_schema = ConsecutiveToolCallState

    def __init__(self, *, limit: int) -> None:
        super().__init__()
        if limit < 1:
            msg = f"limit must be at least 1, got {limit}"
            raise ValueError(msg)
        self.limit = limit

    @hook_config(can_jump_to=["end"])
    @override
    def after_model(
        self,
        state: ConsecutiveToolCallState,
        runtime: Any,
    ) -> dict[str, Any] | None:
        del runtime
        messages = state.get("messages", [])
        if not messages:
            return None

        last_ai: AIMessage | None = None
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                last_ai = message
                break
        if last_ai is None:
            return None

        raw_streak = state.get(_STREAK_KEY)
        streak: dict[str, Any] = raw_streak if isinstance(raw_streak, dict) else {}
        if not last_ai.tool_calls:
            if not streak.get("count"):
                return None
            return {_STREAK_KEY: {"signature": "", "count": 0}}

        signature = str(streak.get("signature") or "")
        count = int(streak.get("count") or 0)
        blocked: list[dict[str, Any]] = []
        exceeded_name = ""
        exceeded_count = 0
        for tool_call in last_ai.tool_calls:
            call = dict(tool_call)
            next_signature = tool_call_signature(call)
            if next_signature == signature:
                count += 1
            else:
                signature = next_signature
                count = 1
            if count > self.limit:
                blocked.append(call)
                if not exceeded_name:
                    exceeded_name = str(call.get("name") or "")
                    exceeded_count = count

        if not blocked:
            return {_STREAK_KEY: {"signature": signature, "count": count}}

        blocked_ids = {str(call.get("id") or "") for call in blocked}
        artificial: list[ToolMessage | AIMessage] = [
            ToolMessage(
                content=(
                    "Tool call limit exceeded. Do not repeat this tool call "
                    "with the same arguments."
                ),
                tool_call_id=str(call.get("id") or ""),
                name=call.get("name"),
                status="error",
            )
            for call in blocked
        ]
        artificial.extend(
            ToolMessage(
                content=(
                    "Execution stopped before this tool call could run because "
                    "a repeated tool call in the same batch exceeded the limit."
                ),
                tool_call_id=str(tool_call.get("id") or ""),
                name=tool_call.get("name"),
                status="error",
            )
            for tool_call in last_ai.tool_calls
            if str(tool_call.get("id") or "") not in blocked_ids
        )
        shown = exceeded_name or "tool"
        artificial.append(
            AIMessage(
                content=(
                    "[tool_call_repeat]\n"
                    f"tool: {shown}\n"
                    f"count: {exceeded_count}\n"
                    f"limit: {self.limit}"
                )
            )
        )
        return {
            _STREAK_KEY: {"signature": signature, "count": count},
            "jump_to": "end",
            "messages": artificial,
        }

    @hook_config(can_jump_to=["end"])
    async def aafter_model(
        self,
        state: ConsecutiveToolCallState,
        runtime: Any,
    ) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
