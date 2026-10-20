"""Merge process env, admin/global keys, and workspace ``.env`` for agent spawn.

Precedence (later wins): base → extra → workspace ``.env``.
Workspace keys listed in :data:`PROTECTED_ENV_KEYS` / ``OCTOP_*`` are ignored
so an agent file cannot clobber platform identity or Octop process config.

Spawn surfaces are intentionally not identical:

- Host ``execute`` (bwrap / local shell) inherits live ``os.environ``, then extra
  keys, then workspace ``.env``.
- Docker sandbox starts from a minimal ``PATH``/``HOME`` and never copies the
  full host environment.
- ACP child processes inherit full ``os.environ`` (runners need PATH/display),
  then cwd ``.env`` (protected keys skipped), then runner-config env.
- MCP stdio uses the SDK default subset, then spec ``env`` — not full
  ``os.environ``.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PROTECTED_ENV_KEYS = frozenset(
    {
        "HOME",
        "USER",
        "USERNAME",
        "LOGNAME",
        "SHELL",
        "PWD",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "COMSPEC",
        "WINDIR",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
    }
)
PROTECTED_ENV_PREFIXES = ("OCTOP_",)

DOCKER_MINIMAL_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def is_protected_env_key(key: str) -> bool:
    if key in PROTECTED_ENV_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in PROTECTED_ENV_PREFIXES)


def parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or not _KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        out[key] = value
    return out


def load_dotenv_path(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    file = Path(path)
    if not file.is_file():
        return {}
    try:
        return parse_env_text(file.read_text(encoding="utf-8"))
    except OSError:
        return {}


def backend_workspace_dotenv_reader(
    workspace: BackendWorkspace,
) -> Callable[[], dict[str, str]]:
    """Read workspace ``.env`` through ``BackendWorkspace`` (same as env_file tools)."""

    def _read() -> dict[str, str]:
        try:
            if not workspace.exists(".env"):
                return {}
            raw = workspace.read_text(".env")
            return parse_env_text(raw) if raw else {}
        except Exception:  # workspace .env is optional; pylint: disable=broad-except
            logger.debug("failed to read workspace .env via backend", exc_info=True)
            return {}

    return _read


def _workspace_dotenv(
    *,
    reader: Callable[[], Mapping[str, str]] | None,
    host_dir: str | Path | None,
) -> dict[str, str]:
    if reader is not None:
        try:
            return {str(k): str(v) for k, v in reader().items()}
        except Exception:  # workspace dotenv reader is best-effort; pylint: disable=broad-except
            logger.debug("workspace dotenv reader failed", exc_info=True)
            return {}
    return load_dotenv_path(None if host_dir is None else Path(host_dir) / ".env")


def overlay_env(
    base: Mapping[str, str],
    overlay: Mapping[str, str],
    *,
    protect: bool = True,
    extra_locked: frozenset[str] | None = None,
) -> dict[str, str]:
    out = {str(k): str(v) for k, v in base.items()}
    locked = extra_locked or frozenset()
    for raw_key, raw_value in overlay.items():
        key = str(raw_key)
        if key in locked or (protect and is_protected_env_key(key)):
            continue
        out[key] = str(raw_value)
    return out


def docker_base_env() -> dict[str, str]:
    return {
        "PATH": DOCKER_MINIMAL_PATH,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": "/root",
    }


def resolve_local_execute_env(
    *,
    inherit: bool = True,
    extra: Mapping[str, str] | None = None,
    workspace_dir: str | Path | None = None,
    workspace_reader: Callable[[], Mapping[str, str]] | None = None,
) -> dict[str, str]:
    """Host shell: live ``os.environ`` + extra + workspace ``.env`` (reader, else host file)."""
    base: Mapping[str, str] = os.environ if inherit else {}
    env = overlay_env(base, extra or {}, protect=False)
    return overlay_env(
        env,
        _workspace_dotenv(reader=workspace_reader, host_dir=workspace_dir),
        protect=True,
    )


def resolve_docker_execute_env(
    *,
    global_env: Mapping[str, str] | None = None,
    workspace_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Sandbox env: minimal PATH + admin/global keys + workspace ``.env`` (not full host).

    Admin/global keys cannot override ``PATH`` (container toolchain) or protected
    identity keys. Workspace ``.env`` may set ``PATH``. Callers that read an
    admin ``environment_file`` should merge it into ``global_env`` first so file
    mtime caching stays at the sandbox layer.
    """
    merged_global = overlay_env(
        {},
        global_env or {},
        protect=True,
        extra_locked=frozenset({"PATH"}),
    )
    env = overlay_env(docker_base_env(), merged_global, protect=True, extra_locked=frozenset({"PATH"}))
    return overlay_env(env, workspace_env or {}, protect=True)


def stdio_base_env() -> dict[str, str]:
    """Safe subset the MCP SDK would inherit when ``env`` is omitted."""
    try:
        from mcp.client.stdio import get_default_environment

        return dict(get_default_environment())
    except Exception:  # mcp SDK is optional; pylint: disable=broad-except
        keys = ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
        return {k: os.environ[k] for k in keys if os.environ.get(k)}


def merge_host_stdio_env(spec_env: Mapping[str, str] | None) -> dict[str, str]:
    """MCP stdio: SDK default subset, then spec-provided keys (not full ``os.environ``)."""
    return overlay_env(stdio_base_env(), spec_env or {}, protect=False)
