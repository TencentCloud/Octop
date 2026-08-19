"""Record workspace file paths onto ``threads.artifacts`` after successful tool calls."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.gateway.media.backend_files import extract_workspace_rel

logger = logging.getLogger(__name__)

ARTIFACT_TOOL_BASES = frozenset(
    {
        "write_file",
        "edit_file",
        "send_file",
        "send_file_to_user",
        "desktop_screenshot",
    }
)

_PATH_KEYS = (
    "path",
    "file_path",
    "filepath",
    "dest",
    "target_path",
    "output_path",
)

_PATH_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9._+-]{0,11}$")
_ABS_OCTOP_RE = re.compile(r"(?:/[\w.-]+)*/\.octop/agents/[^\s\"'<>]+", re.IGNORECASE)
_REL_DIR_RE = re.compile(
    r"(?:^|[\s\"'`])((?:outbound|inbound|generated)/[^\s\"'<>]+)",
    re.IGNORECASE,
)


class ArtifactThreadStore(Protocol):
    def append_artifacts(self, thread_id: str, paths: Sequence[str]) -> None: ...


def tool_name_base(name: str) -> str:
    trimmed = (name or "").strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def is_artifact_tool_name(name: str | None) -> bool:
    base = tool_name_base(name or "").lower()
    return base in ARTIFACT_TOOL_BASES


def normalize_artifact_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    rel = extract_workspace_rel(raw)
    if rel:
        raw = rel
    else:
        marker = "/.octop/agents/"
        idx = raw.lower().find(marker)
        if idx >= 0:
            rest = raw[idx + len(marker) :]
            slash = rest.find("/")
            if slash >= 0:
                raw = rest[slash + 1 :].lstrip("/")
        else:
            raw = raw.lstrip("/")
    if not raw or raw in {".", "/"}:
        return ""
    posix = raw.replace("\\", "/")
    if "/_builtin_skills/" in f"/{posix}/" or posix.startswith("_builtin_skills"):
        return ""
    base = posix.split("/")[-1] or posix
    if re.fullmatch(r"[\d.]+", base):
        return ""
    if not _PATH_EXT_RE.search(base):
        return ""
    return posix


def extract_artifact_paths(
    *,
    tool_name: str = "",
    args: str | Mapping[str, Any] | None = None,
    result: Any = None,
) -> list[str]:
    """Return workspace paths from a write/edit/send/screenshot tool.

    Prefer structured path keys on tool *args*. Scan the tool result text only
    when args did not yield a path (screenshots, send_file without a path key).
    """
    if not is_artifact_tool_name(tool_name):
        return []
    from_args = _dedupe_paths(_paths_from_args(args))
    if from_args:
        return from_args
    return _dedupe_paths(_paths_from_content(result))


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
    """Append successful file-producing tool paths onto the current thread row."""

    def __init__(self, *, thread_repo: ArtifactThreadStore) -> None:
        super().__init__()
        self._threads = thread_repo

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
        )
        if not paths:
            return
        try:
            self._threads.append_artifacts(thread_id, paths)
        except Exception:
            logger.warning(
                "Failed to append thread artifacts for %s",
                thread_id,
                exc_info=True,
            )


def _dedupe_paths(paths: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        key = normalize_artifact_path(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _pick_path_from_object(parsed: Mapping[str, Any]) -> str:
    for key in _PATH_KEYS:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _paths_from_args(raw: str | Mapping[str, Any] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        picked = _pick_path_from_object(raw)
        return [picked] if picked else []
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        picked = _pick_path_from_object(parsed)
        return [picked] if picked else _paths_from_text(text)
    return _paths_from_text(text)


def _paths_from_content(content: Any) -> list[str]:
    if content is None:
        return []
    if isinstance(content, str):
        stripped = content.strip()
        if stripped and stripped[0] in "{[":
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                return _paths_from_content(parsed)
            if isinstance(parsed, list):
                found: list[str] = []
                for item in parsed:
                    found.extend(_paths_from_content(item))
                return found
        return _paths_from_text(stripped)
    if isinstance(content, Mapping):
        found = []
        picked = _pick_path_from_object(content)
        if picked:
            found.append(picked)
        nested = content.get("source")
        if isinstance(nested, Mapping):
            url = nested.get("url")
            if isinstance(url, str) and url.strip():
                found.append(url.strip())
        return found
    if isinstance(content, list):
        found = []
        for item in content:
            found.extend(_paths_from_content(item))
        return found
    return []


def _paths_from_text(text: str) -> list[str]:
    if not text:
        return []
    abs_match = _ABS_OCTOP_RE.search(text)
    if abs_match:
        return [abs_match.group(0)]
    rel_match = _REL_DIR_RE.search(text)
    if rel_match:
        return [rel_match.group(1)]
    return []


__all__ = [
    "ARTIFACT_TOOL_BASES",
    "ThreadArtifactsMiddleware",
    "current_thread_id",
    "extract_artifact_paths",
    "is_artifact_tool_name",
    "normalize_artifact_path",
    "tool_name_base",
]
