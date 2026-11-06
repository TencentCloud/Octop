"""Path rules for the secret-file card.

The model passes a *relative* name that must land inside the agent's
platform-managed auth directory:

* new layout: ``{workspace}/.octop/auth/`` (``system_files_path`` prefix)
* legacy layout: ``{workspace}/.octop-auth/`` (when it already holds files)

Absolute host paths, ``~``, Windows drive paths, ``..`` segments and other
workspaces are all rejected — the model can never pick an arbitrary host
location, a shared HOME, or another agent's directory.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

REQUEST_SECRET_FILE_TOOL = "request_secret_file"

# Drive-letter / UNC / double-slash absolute paths (Windows).
_WINDOWS_ABS_RE = re.compile(r"^(?:[A-Za-z]:[/\\]|\\\\|//)")
# Prefixes a skill may use when pointing inside the auth dir; all strip to a
# bare name relative to that directory.
_AUTH_PREFIXES = (".octop/auth/", ".octop-auth/", "auth/")

LEGACY_AUTH_FRAGMENT = ".octop-auth"

_MAX_NAME_CHARS = 200
_MAX_SEGMENTS = 8


def _invalid(detail: str) -> OctopError:
    return OctopError(
        ErrorCode.SECRET_PATH_INVALID,
        f"secret path must be a relative file name inside the agent auth directory ({detail})",
    )


def normalize_secret_name(raw: object) -> str:
    """Validate a model-provided path; return it relative to the auth dir.

    Accepts bare names (``hr.token``), nested relative paths
    (``feishu/app.token``) and the skill-facing prefixes ``auth/…``,
    ``.octop/auth/…`` or ``.octop-auth/…``. Anything absolute or escaping the
    auth directory raises :class:`OctopError` with ``SECRET_PATH_INVALID``.
    """
    if not isinstance(raw, str):
        raise _invalid("not a string")
    text = raw.strip().replace("\\", "/")
    if not text:
        raise _invalid("empty")
    if "\x00" in text:
        raise _invalid("NUL byte")
    if text.startswith(("/", "~")) or _WINDOWS_ABS_RE.match(text):
        raise _invalid("absolute paths are not allowed")
    while text.startswith("./"):
        text = text[2:]
    lowered = text.lower()
    for prefix in _AUTH_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    while text.startswith("./"):
        text = text[2:]
    segments = text.split("/")
    if len(text) > _MAX_NAME_CHARS or len(segments) > _MAX_SEGMENTS:
        raise _invalid("path too long")
    if any(seg in ("", ".", "..") for seg in segments):
        raise _invalid("empty, '.' or '..' segments are not allowed")
    return "/".join(segments)


async def resolve_auth_fragment(workspace: BackendWorkspace) -> str:
    """Workspace-relative auth directory fragment, mirroring ``agent_auth_dir``.

    New agents use ``{system_files_path}/auth``; legacy agents keep
    ``.octop-auth`` when it already holds files and the canonical directory is
    still empty.
    """
    prefix = workspace.system_files_path
    if not prefix:
        return LEGACY_AUTH_FRAGMENT
    canonical = f"{prefix}/auth"
    legacy_result = await workspace.als(LEGACY_AUTH_FRAGMENT)
    legacy_entries = getattr(legacy_result, "entries", None) or []
    if legacy_entries:
        canonical_result = await workspace.als(canonical)
        canonical_entries = getattr(canonical_result, "entries", None) or []
        if not canonical_entries:
            return LEGACY_AUTH_FRAGMENT
    return canonical


def secret_fragment(auth_fragment: str, name: str) -> str:
    """Workspace-relative fragment of the secret file."""
    return f"{auth_fragment.rstrip('/')}/{name}"


def is_secret_action_requests(action_requests: list[dict[str, Any]]) -> bool:
    """True when this HITL pause is a ``request_secret_file`` interrupt."""
    return any(
        isinstance(a, dict) and a.get("name") == REQUEST_SECRET_FILE_TOOL for a in action_requests
    )


def secret_request_args(action_requests: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Args of the first ``request_secret_file`` action, if any."""
    for action in action_requests:
        if not isinstance(action, dict) or action.get("name") != REQUEST_SECRET_FILE_TOOL:
            continue
        args = action.get("args")
        return args if isinstance(args, dict) else {}
    return None


__all__ = [
    "LEGACY_AUTH_FRAGMENT",
    "REQUEST_SECRET_FILE_TOOL",
    "is_secret_action_requests",
    "normalize_secret_name",
    "resolve_auth_fragment",
    "secret_fragment",
    "secret_request_args",
]
