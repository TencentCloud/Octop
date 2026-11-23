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

from octop.infra.agents.threads.artifact import (
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
    thread. A team file-target turn stamps the host agent, because the bytes
    were written on the host workspace.
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
        request = self._rewrite_plan_path(request)
        result = handler(request)
        self._record(request, result)
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        request = self._rewrite_plan_path(request)
        result = await handler(request)
        self._record(request, result)
        return result

    def _rewrite_plan_path(self, request: ToolCallRequest) -> ToolCallRequest:
        from octop.infra.agents.conversation_mode import workspace_plan_path

        tool_call = request.tool_call
        name = str(tool_call.get("name") or "").rsplit("/", 1)[-1]
        if name not in {"write_file", "edit_file"}:
            return request
        raw_args = tool_call.get("args")
        if not isinstance(raw_args, dict):
            return request
        path = raw_args.get("file_path") or raw_args.get("path")
        if not isinstance(path, str) or not path.strip():
            return request
        rewritten = workspace_plan_path(path.strip(), self._workspace_dir)
        if rewritten == path:
            return request
        key = "file_path" if "file_path" in raw_args else "path"
        tool_call["args"] = {**raw_args, key: rewritten}
        return request

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
            workspace_dir=self._artifact_workspace(),
        )
        if not paths:
            return
        agent_id = self._producer_agent_id()
        self._append(thread_id, paths, agent_id=agent_id)
        room = peer_room_thread_id(thread_id)
        if room:
            self._append(room, paths, agent_id=agent_id)
        self._maybe_record_pending_plan(thread_id, paths)

    def _file_target(self) -> tuple[str, Path] | None:
        from octop.infra.agents.teams.file_target import BRIDGE_TARGET_KEY, DIR_KEY, HOST_KEY

        try:
            configurable = dict(get_config().get("configurable") or {})
        except RuntimeError:
            return None

        host_id = configurable.get(HOST_KEY)
        directory = configurable.get(DIR_KEY)
        bridge_id = configurable.get(BRIDGE_TARGET_KEY)
        if not isinstance(directory, str) or not directory.strip():
            return None
        folder = Path(directory.strip())
        if isinstance(host_id, str) and host_id.strip():
            return host_id.strip(), folder
        if isinstance(bridge_id, str) and bridge_id.strip():
            return self._agent_id, folder
        return None

    def _artifact_workspace(self) -> Path:
        target = self._file_target()
        if target is None:
            return self._workspace_dir
        return target[1]

    def _producer_agent_id(self) -> str:
        target = self._file_target()
        if target is None:
            return self._agent_id
        return target[0]

    def _append(self, thread_id: str, paths: Sequence[str], *, agent_id: str) -> None:
        try:
            self._threads.append_artifacts(
                thread_id,
                paths,
                agent_id=agent_id,
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
