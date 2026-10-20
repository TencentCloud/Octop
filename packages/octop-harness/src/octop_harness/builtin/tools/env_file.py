"""Built-in tool: read/write ``.env``-style files in the workspace.

These tools operate through :class:`BackendWorkspace`, so ``.env`` always
lands under the agent workspace (``config.workspace_dir``) instead of an
arbitrary host path. This gives the model a safe, explicit way to persist
credentials and configuration as ``KEY=VALUE`` pairs without falling back to
writing dotfiles to host-absolute locations such as ``/workspace/.env``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.tools import StructuredTool
from pydantic import Field

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace


def _sanitize_env_file(file: str) -> str:
    """Force *file* to be a workspace-relative fragment.

    ``BackendWorkspace.resolve_path`` leaves leading-slash and ``~`` paths as
    host-absolute, which would let a model escape the workspace (e.g. write to
    ``/workspace/.env``). Reject those explicitly so ``.env`` always stays in
    the agent workspace.
    """
    s = file.strip()
    if not s or s.startswith("/") or s.startswith("~"):
        msg = f"file must be a workspace-relative path, got {file!r}"
        raise ValueError(msg)
    return s


def _ok(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(exc: Exception) -> str:
    return json.dumps({"error": str(exc)}, ensure_ascii=False)


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse one `KEY=VALUE` line, ignoring blanks and ``#`` comments."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    key, _, raw_value = stripped.partition("=")
    key = key.strip()
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def _serialize_env(values: dict[str, str]) -> str:
    """Render ``KEY=VALUE`` lines (order-preserving)."""
    return "".join(f"{key}={value}\n" for key, value in values.items())


def build_env_file_tools(workspace: BackendWorkspace) -> list[StructuredTool]:
    """Return ``.env`` read/write tools scoped to *workspace*."""

    async def read_env_file(
        file: Annotated[
            str,
            Field(description="Workspace-relative .env path, e.g. '.env'. Defaults to '.env'."),
        ] = ".env",
    ) -> str:
        try:
            file = _sanitize_env_file(file)
            if not workspace.exists(file):
                return _ok({"file": file, "exists": False, "values": {}})
            raw = workspace.read_text(file)
            if raw is None:
                return _ok({"file": file, "exists": True, "values": {}})
            values = {}
            for line in raw.splitlines():
                parsed = _parse_env_line(line)
                if parsed is not None:
                    values[parsed[0]] = parsed[1]
            return _ok({"file": file, "exists": True, "values": values})
        except Exception as exc:  # surface tool errors as JSON; pylint: disable=broad-except
            return _err(exc)

    async def write_env_file(
        updates: Annotated[
            dict[str, str],
            Field(description="Key-value pairs to set in the .env file."),
        ],
        file: Annotated[
            str,
            Field(description="Workspace-relative .env path, e.g. '.env'. Defaults to '.env'."),
        ] = ".env",
        merge: Annotated[
            bool,
            Field(description="If true, keep existing keys not in `updates`; if false, overwrite with only `updates`."),
        ] = True,
        remove: Annotated[
            list[str] | None,
            Field(description="Keys to delete from the file. Applied after `updates`."),
        ] = None,
    ) -> str:
        try:
            file = _sanitize_env_file(file)
            existing: dict[str, str] = {}
            if merge and workspace.exists(file):
                raw = workspace.read_text(file)
                if raw:
                    for line in raw.splitlines():
                        parsed = _parse_env_line(line)
                        if parsed is not None:
                            existing[parsed[0]] = parsed[1]
            merged = dict(existing) if merge else {}
            merged.update(updates)
            for key in remove or []:
                merged.pop(key, None)
            workspace.write_text(file, _serialize_env(merged), force=True)
            return _ok({"file": file, "keys": sorted(merged.keys()), "removed": remove or []})
        except Exception as exc:  # surface tool errors as JSON; pylint: disable=broad-except
            return _err(exc)

    return [
        StructuredTool.from_function(
            coroutine=read_env_file,
            name="read_env_file",
            description=(
                "Read a .env-style file from the agent workspace and return its "
                "KEY=VALUE pairs as JSON. Use this instead of writing .env to an "
                "arbitrary host path."
            ),
        ),
        StructuredTool.from_function(
            coroutine=write_env_file,
            name="write_env_file",
            description=(
                "Write KEY=VALUE pairs to a .env-style file in the agent workspace. "
                "With merge=true, existing keys are preserved; removed keys are dropped. "
                "Use this to persist credentials/config safely inside the workspace. "
                "Written keys are injected into subsequent shell/sandbox execute "
                "(and ACP spawns); they do not replace Octop process-wide env."
            ),
        ),
    ]
