"""Record workspace file paths onto ``threads.artifacts`` after successful tool calls."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.agents.thread_artifact import (
    extract_artifact_paths,
    is_artifact_tool_name,
)

logger = logging.getLogger(__name__)


class ArtifactThreadStore(Protocol):
    def append_artifacts(
        self,
        thread_id: str,
        paths: Sequence[str],
        *,
        agent_id: str = "",
    ) -> None: ...


def peer_room_thread_id(thread_id: str) -> str:
    """Caller room id for a peer thread (``room~callee``), else ``\"\"``."""
    tid = (thread_id or "").strip()
    if "~" not in tid:
        return ""
    room = tid.rsplit("~", 1)[0].strip()
    return room if room and room != tid else ""


def current_thread_id() -> str:
    try:
        configurable = dict(get_config().get("configurable") or {})
    except RuntimeError:
        return ""
    raw = configurable.get("thread_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


class ThreadArtifactsMiddleware(AgentMiddleware[Any, Any]):
    """Append successful file-producing tool paths onto the current thread row.

    Peer threads (``room~member``) also mirror the same paths onto the room
    thread, stamped with the producer ``agent_id`` so the team file dock can
    open them via the member workspace.
    """

    def __init__(
        self,
        *,
        thread_repo: ArtifactThreadStore,
        workspace_dir: Path,
        agent_id: str = "",
    ) -> None:
        super().__init__()
        self._threads = thread_repo
        self._workspace_dir = workspace_dir.expanduser()
        self._agent_id = (agent_id or "").strip()

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)
        self._record(request, result)
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        self._record(request, result)
        return result

    def _record(
        self,
        request: ToolCallRequest,
        result: ToolMessage | Command[Any],
    ) -> None:
        if isinstance(result, Command):
            return
        if not isinstance(result, ToolMessage):
            return
        if getattr(result, "status", None) == "error":
            return
        tool_call = request.tool_call
        name = str(tool_call.get("name") or "")
        if not is_artifact_tool_name(name):
            return
        thread_id = current_thread_id()
        if not thread_id:
            return
        raw_args = tool_call.get("args")
        paths = extract_artifact_paths(
            tool_name=name,
            args=raw_args if isinstance(raw_args, (str, Mapping)) else None,
            result=result.content,
            workspace_dir=self._workspace_dir,
        )
        if not paths:
            return
        self._append(thread_id, paths)
        room = peer_room_thread_id(thread_id)
        if room:
            self._append(room, paths)
        self._maybe_record_pending_plan(thread_id, paths)

    def _append(self, thread_id: str, paths: Sequence[str]) -> None:
        try:
            self._threads.append_artifacts(
                thread_id,
                paths,
                agent_id=self._agent_id,
            )
        except Exception:
            logger.warning(
                "Failed to append thread artifacts for %s",
                thread_id,
                exc_info=True,
            )

    def _maybe_record_pending_plan(self, thread_id: str, paths: Sequence[str]) -> None:
        from octop.infra.agents.conversation_mode import (  # noqa: PLC0415
            parse_conversation_mode,
            plan_relpath_from_artifact,
        )

        try:
            configurable = dict(get_config().get("configurable") or {})
        except RuntimeError:
            return
        mode = parse_conversation_mode(configurable.get("conversation_mode"))
        if mode != "plan":
            return
        rel = ""
        for path in paths:
            rel = plan_relpath_from_artifact(path)
            if rel:
                break
        if not rel:
            return
        setter = getattr(self._threads, "update_composer", None)
        if setter is None:
            return
        try:
            setter(thread_id, pending_plan_path=rel)
        except Exception:
            logger.warning(
                "Failed to record pending plan for %s",
                thread_id,
                exc_info=True,
            )


__all__ = [
    "ArtifactThreadStore",
    "ThreadArtifactsMiddleware",
    "current_thread_id",
    "peer_room_thread_id",
]
