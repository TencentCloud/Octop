"""Force browser tool calls onto the current user's isolated profile."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.utils.browser_media import parse_octop_user_id, user_browser_profile

logger = logging.getLogger(__name__)

_BROWSER_TOOL = "browser_use"
_MISSING_USER = (
    "browser_use blocked: the current turn has no Octop user id, "
    "so a browser profile cannot be isolated."
)


class ThreadOwner(Protocol):
    """Row surface needed to resolve a thread's owner."""

    @property
    def user_id(self) -> int: ...


class ThreadOwnerStore(Protocol):
    """Read-only thread lookup used when a turn carries no user id."""

    def get(self, thread_id: str) -> ThreadOwner | None: ...


def _thread_owner_user_id(
    configurable: dict[str, Any],
    thread_repo: ThreadOwnerStore | None,
) -> int | None:
    """Owner of the current thread, or ``None`` when it cannot be resolved.

    A resumed HITL turn rebuilds the runnable config with ``thread_id`` only, so
    the ``user`` key a normal turn carries is absent. The thread row already
    knows who owns the conversation (IM turns use the agent owner), which is the
    same identity ``user_browser_profile`` documents.
    """
    if thread_repo is None:
        return None
    raw_thread_id = configurable.get("thread_id")
    thread_id = raw_thread_id.strip() if isinstance(raw_thread_id, str) else ""
    if not thread_id:
        return None
    try:
        row = thread_repo.get(thread_id)
    except Exception:
        logger.warning("browser_use: thread owner lookup failed for %s", thread_id, exc_info=True)
        return None
    return parse_octop_user_id(getattr(row, "user_id", None))


def _resolve_user_id(
    configurable: dict[str, Any],
    thread_repo: ThreadOwnerStore | None,
) -> int | None:
    raw_user = configurable.get("user")
    user_id = parse_octop_user_id(raw_user)
    if user_id is not None:
        return user_id
    if raw_user is None or (isinstance(raw_user, str) and not raw_user.strip()):
        return _thread_owner_user_id(configurable, thread_repo)
    return None


def _bind_browser_profile(
    request: ToolCallRequest,
    *,
    thread_repo: ThreadOwnerStore | None = None,
) -> ToolCallRequest | ToolMessage:
    tool_call = request.tool_call
    if str(tool_call.get("name") or "") != _BROWSER_TOOL:
        return request

    configurable = dict(get_config().get("configurable") or {})
    user_id = _resolve_user_id(configurable, thread_repo)
    if user_id is None:
        logger.warning("browser_use blocked: configurable.user is missing or invalid")
        return ToolMessage(
            content=_MISSING_USER,
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )

    raw_args = tool_call.get("args")
    args = dict(raw_args) if isinstance(raw_args, dict) else {}
    args["profile"] = user_browser_profile(user_id)
    return request.override(tool_call={**tool_call, "args": args})


class BrowserProfileMiddleware(AgentMiddleware[Any, Any]):
    """Prevent model-selected profiles from crossing Octop user boundaries."""

    def __init__(self, *, thread_repo: ThreadOwnerStore | None = None) -> None:
        super().__init__()
        self._thread_repo = thread_repo

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        bound = _bind_browser_profile(request, thread_repo=self._thread_repo)
        if isinstance(bound, ToolMessage):
            return bound
        return handler(bound)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        bound = _bind_browser_profile(request, thread_repo=self._thread_repo)
        if isinstance(bound, ToolMessage):
            return bound
        return await handler(bound)


__all__ = ["BrowserProfileMiddleware", "ThreadOwner", "ThreadOwnerStore"]
