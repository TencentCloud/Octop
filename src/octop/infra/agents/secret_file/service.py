"""Service helpers for the secret-file card: card metadata and the write flow."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from octop.infra.agents.secret_file.paths import (
    REQUEST_SECRET_FILE_TOOL,
    is_secret_action_requests,
    normalize_secret_name,
    resolve_auth_fragment,
    secret_fragment,
    secret_request_args,
)
from octop.infra.agents.secret_file.private_write import (
    secret_backend_supported,
    write_secret_private,
)
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 64 * 1024


def display_path_for(workspace: BackendWorkspace, fragment: str) -> str:
    """Agent-facing path usable by the skill's CLI inside the agent environment.

    Local host backends get the absolute host path; sandbox backends get the
    workspace-relative fragment (their shell starts in the workspace root), so
    a host path is never pushed into a container.
    """
    if getattr(workspace.backend, "sandbox_fs", False):
        return fragment
    try:
        return workspace.resolve_path(fragment)
    except Exception:  # defensive: card still renders the fragment
        logger.debug("secret-file: resolve_path failed", exc_info=True)
        return fragment


async def describe_secret_request(
    workspace: BackendWorkspace,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Card metadata for the dashboard: normalized display path + existence.

    Pure metadata — never touches file contents. An invalid model-provided
    path yields ``{"invalid": True}`` so the card can refuse submission; a
    backend without private-write guarantees yields ``unsupported``.
    """
    if not secret_backend_supported(workspace.backend):
        return {"invalid": True, "unsupported": True}
    try:
        name = normalize_secret_name(args.get("path"))
    except OctopError:
        return {"invalid": True}
    try:
        fragment = secret_fragment(await resolve_auth_fragment(workspace), name)
        exists = await workspace.aexists(fragment)
        return {
            "path": display_path_for(workspace, fragment),
            "exists": bool(exists),
        }
    except Exception:  # best-effort annotation; card falls back to raw path
        logger.debug("secret-file: describe failed", exc_info=True)
        return {}


async def maybe_annotate_secret_payload(
    payload: dict[str, Any],
    workspace: BackendWorkspace | None,
) -> None:
    """Best-effort ``_secret_card`` metadata on a raw HITL interrupt payload.

    Runs before the pending record is registered so history reload re-shows
    the card with the same metadata. No-op for non-secret pauses.
    """
    if workspace is None:
        return
    requests = payload.get("action_requests")
    if not isinstance(requests, list):
        return
    for item in requests:
        if not isinstance(item, dict) or item.get("name") != REQUEST_SECRET_FILE_TOOL:
            continue
        args = item.get("args")
        if not isinstance(args, dict):
            return
        info = await describe_secret_request(workspace, args)
        if info:
            args["_secret_card"] = info
        return


async def submit_secret_content(
    workspace: BackendWorkspace,
    *,
    raw_path: object,
    content: str,
) -> str:
    """Validate and write the secret; return the agent-facing display path.

    Raises :class:`OctopError` on any failure; the previous file is preserved.
    """
    if not content.strip():
        raise OctopError(ErrorCode.SECRET_REQUEST_INVALID, "secret content is empty")
    if len(content) > _MAX_CONTENT_CHARS:
        raise OctopError(
            ErrorCode.SECRET_REQUEST_INVALID,
            f"secret content exceeds {_MAX_CONTENT_CHARS} characters",
        )
    name = normalize_secret_name(raw_path)
    fragment = secret_fragment(await resolve_auth_fragment(workspace), name)
    await write_secret_private(workspace, fragment=fragment, content=content)
    return display_path_for(workspace, fragment)


__all__ = [
    "describe_secret_request",
    "display_path_for",
    "is_secret_action_requests",
    "maybe_annotate_secret_payload",
    "secret_request_args",
    "submit_secret_content",
]
