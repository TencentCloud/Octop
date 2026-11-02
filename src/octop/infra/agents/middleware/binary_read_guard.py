"""Block ``read_file`` on binary files and unlabeled inbound attachments."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

_READ_FILE_TOOL = "read_file"
# Known binaries only. ``read_file`` would otherwise paste the raw bytes
# into the model context.
_BLOCKED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".bin",
        ".gif",
        ".webp",
        ".jpg",
        ".jpeg",
        ".png",
    }
)
_BINARY_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "application/zip",
        "application/x-zip-compressed",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
    }
)
# Inbound attachments outside this set need an explicit text MIME. ``.log``
# and ``.conf`` stay readable even when a browser labels them octet-stream.
_TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".json",
        ".csv",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
        ".sql",
        ".sh",
        ".log",
        ".conf",
    }
)
_UNLABELED_MEDIA_TYPES = frozenset({"", "application/octet-stream"})


def _read_file_path_from_args(params: dict[str, Any]) -> str:
    for key in ("file_path", "path"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _extension(path: str) -> str:
    cleaned = path.split("?", 1)[0].split("#", 1)[0]
    return Path(cleaned).suffix.lower()


def _is_inbound_attachment(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    return normalized.startswith("inbound/") or "/inbound/" in normalized


def read_file_block_reason(path: str, *, media_type: str = "") -> str | None:
    """Return a rejection message when *path* must not be read via ``read_file``."""
    if not path:
        return None
    normalized_media_type = media_type.split(";", 1)[0].strip().lower()
    if normalized_media_type in _BINARY_MEDIA_TYPES or normalized_media_type.startswith(
        ("image/", "audio/", "video/")
    ):
        return (
            f"read_file blocked for binary attachment `{path}`. "
            "Use execute_shell_command or the matching skill instead."
        )
    ext = _extension(path)
    if ext == ".pdf":
        return (
            f"read_file blocked for binary PDF `{path}`. "
            "Use execute_shell_command with the pdf skill (pdftotext, pdfplumber, etc.) instead."
        )
    if ext in _BLOCKED_EXTENSIONS:
        return (
            f"read_file blocked for binary file `{path}`. "
            "Use execute_shell_command or the matching skill instead."
        )
    if (
        _is_inbound_attachment(path)
        and ext not in _TEXT_EXTENSIONS
        and normalized_media_type in _UNLABELED_MEDIA_TYPES
    ):
        return (
            f"read_file blocked for inbound attachment `{path}`. "
            "Use execute_shell_command or the matching skill instead."
        )
    return None


def _workspace_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    marker = "/inbound/"
    if marker in f"/{normalized}":
        return "inbound/" + normalized.rsplit(marker, 1)[1]
    return normalized


def _attachment_media_type(request: ToolCallRequest, path: str) -> str:
    target = _workspace_path(path)
    state = getattr(request, "state", {}) or {}
    messages = state.get("messages") if isinstance(state, dict) else None
    for message in reversed(messages or []):
        if not isinstance(message, HumanMessage):
            continue
        extra = message.additional_kwargs or {}
        attachments = extra.get("octop_inbound_attachments")
        if not isinstance(attachments, list):
            continue
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            raw_path = attachment.get("workspace_path")
            if isinstance(raw_path, str) and _workspace_path(raw_path) == target:
                media_type = attachment.get("media_type")
                return media_type if isinstance(media_type, str) else ""
    return ""


class BinaryReadGuardMiddleware(AgentMiddleware[Any, Any]):
    """Reject read_file on PDF/Office inbound attachments before bytes hit context."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        tool_name = str(tool_call.get("name") or "")
        if tool_name != _READ_FILE_TOOL:
            return await handler(request)

        params = tool_call.get("args") or {}
        if not isinstance(params, dict):
            params = {}
        path = _read_file_path_from_args(params)
        reason = read_file_block_reason(path, media_type=_attachment_media_type(request, path))
        if reason is None:
            return await handler(request)

        logger.info("BinaryReadGuard blocked read_file on %s", path)
        return ToolMessage(
            content=reason,
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )


__all__ = ["BinaryReadGuardMiddleware", "read_file_block_reason"]
