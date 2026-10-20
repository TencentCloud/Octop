"""Built-in tool: ``send_file_to_user``.

Returns a media block with:

* ``path`` — the caller path unchanged (relative / virtual / host)
* ``source.url`` — an RFC 8089 ``file://`` URI of the **materialized** local
  file when available, so naive channel adapters can open bytes directly

Octop / octop-gateway should prefer ``path`` +
:class:`~octop_harness.backends.workspace.BackendWorkspace` (virtual/host
failback) when a workspace is available.

Expected path mistakes (missing file, directory) are returned as recoverable
``ToolException`` observations — they must not crash the agent turn.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.tools import ToolException, tool

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace


def _classify(media_type: str) -> str:
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    return "file"


def _send_file_block(file_path: str, *, local: Path) -> dict[str, Any]:
    """Emit caller *file_path* plus the materialized local file URI."""
    raw = str(file_path).strip()
    media_type, _ = mimetypes.guess_type(raw)
    if media_type is None:
        media_type, _ = mimetypes.guess_type(str(local))
    if media_type is None:
        media_type = "application/octet-stream"

    return {
        "type": _classify(media_type),
        "path": raw,
        "source": {
            "type": "url",
            "url": local.resolve().as_uri(),
            "media_type": media_type,
        },
        "filename": os.path.basename(raw.rstrip("/\\")) or "file",
    }


def _missing_file_error(file_path: str) -> ToolException:
    return ToolException(
        f"send_file_to_user: no such file: {file_path}. "
        "Use an existing workspace-relative path, verify it, then call again."
    )


def _not_a_file_error(file_path: str) -> ToolException:
    return ToolException(f"send_file_to_user: not a regular file: {file_path}. Pass a file path, not a directory.")


def build_send_file_to_user_tool(workspace: BackendWorkspace) -> Any:
    """Return ``send_file_to_user`` bound to *workspace*."""

    @tool
    def send_file_to_user(file_path: str) -> dict[str, Any]:
        """Send a file to the user through the chat channel.

        Args:
            file_path: Path as known to the agent (kept in ``path`` unchanged).

        Returns:
            A multimodal content block for the channel adapter.
        """
        local = workspace.materialize_local(file_path)
        if local is not None and local.exists() and not local.is_file():
            raise _not_a_file_error(file_path)
        if local is None or not local.is_file():
            raise _missing_file_error(file_path)
        return _send_file_block(file_path, local=local)

    send_file_to_user.handle_tool_error = str
    return send_file_to_user


@tool
def send_file_to_user(file_path: str) -> dict[str, Any]:
    """Send a file (unbound — local path / cwd only; prefer the bound builder)."""
    candidate = Path(file_path).expanduser()
    if not candidate.is_absolute():
        candidate = candidate.absolute()
    if not candidate.exists():
        raise _missing_file_error(str(candidate))
    if not candidate.is_file():
        raise _not_a_file_error(str(candidate))
    return _send_file_block(file_path, local=candidate)


send_file_to_user.handle_tool_error = str
