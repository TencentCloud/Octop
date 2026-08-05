"""Shared workspace helpers (not route handlers)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from harness_agent.backends.workspace import BackendWorkspace

from octop.api.common.agent import require_agent_row

if TYPE_CHECKING:
    from harness_agent import HarnessAgent

# deepagents.backends.utils.EMPTY_CONTENT_WARNING — shown to LLM tools, not humans.
_DEEPAGENTS_EMPTY_WARNING = "System reminder: File exists but has empty contents"


def coerce_read_content(content: Any) -> str:
    """Normalize backend read payloads for the dashboard file viewer."""
    if content is None:
        return ""
    if isinstance(content, list):
        content = "\n".join(str(line) for line in content)
    text = str(content)
    if text == _DEEPAGENTS_EMPTY_WARNING:
        return ""
    return text


def require_running_agent(server: Any, agent_id: str) -> HarnessAgent:
    """Return the live harness agent or raise not-running / not-found errors."""
    assert server.app_runtime is not None
    return cast("HarnessAgent", server.app_runtime.agent_registry.get_agent(agent_id))


async def require_running_workspace(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> BackendWorkspace:
    """Auth-checked :class:`BackendWorkspace` for a running agent."""
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    return require_running_agent(server, agent_id).workspace


def workspace_api_path(raw: str) -> str:
    """Map dashboard ``/`` / ``/foo`` paths to workspace-relative fragments for I/O."""
    text = raw.strip().replace("\\", "/")
    if not text or text == "/":
        return "."
    return text.lstrip("/")


def reanchor_entry_path(entry_path: str, *, parent: str) -> str:
    """Anchor a single-level listing entry under *parent* (the requested dir).

    A directory listing only carries entry names, so the dashboard must get
    ``{requested}/{name}`` back — otherwise a backend that presents longer
    paths yields keys the workspace API cannot resolve on the next request.
    """
    name = entry_path.strip().replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    base = parent.strip().replace("\\", "/").rstrip("/")
    if base in ("", "."):
        return name
    return f"{base}/{name}" if name else base


def file_info_to_dict(info: Any) -> dict[str, Any]:
    """Coerce a ``FileInfo`` TypedDict into a JSON-friendly dict."""
    if isinstance(info, dict):
        path = info.get("path")
        is_dir = info.get("is_dir")
        size = info.get("size")
        modified_at = info.get("modified_at")
    else:
        path = getattr(info, "path", None)
        is_dir = getattr(info, "is_dir", None)
        size = getattr(info, "size", None)
        modified_at = getattr(info, "modified_at", None)
    out: dict[str, Any] = {"path": path}
    if is_dir is not None:
        out["is_dir"] = bool(is_dir)
    if size is not None:
        out["size"] = int(size)
    if modified_at is not None:
        out["modified_at"] = modified_at
    return out
