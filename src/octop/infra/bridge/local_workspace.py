"""Run one cloud-expert turn against a directory on the chat initiator.

The expert keeps its own skills, memory, and connectors. File tools keep
their names and call back over the Bridge WebSocket. The initiator executes
them on a backend rooted at the directory the user picked.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SEND_CAP = 8 * 1024 * 1024
_EXECUTE_CAP = 20_000

_GRANTS: dict[str, LocalWorkspaceGrant] = {}
_BY_DIR: dict[tuple[str, str], str] = {}
_TARGETS: dict[str, Any] = {}
_THREADS: dict[str, str] = {}


class LocalDirectoryError(ValueError):
    """The user-picked directory cannot be used. ``code`` is an i18n suffix."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class LocalWorkspaceGrant:
    token: str
    connection_id: str
    directory: str
    execute: bool
    workspace: Any
    backend: Any


@dataclass
class PeerFileTarget:
    """Expert-side stand-in for the initiator's directory."""

    token: str
    directory: str
    execute: bool
    session: Any
    bridge_file_target: bool = True

    async def call(self, op: str, args: dict[str, Any]) -> dict[str, Any]:
        req_id = uuid.uuid4().hex
        fut = self.session.expect_workspace_result(req_id)
        timeout = 120.0
        if op == "execute":
            raw = args.get("timeout")
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
                timeout = min(float(raw) + 15.0, 600.0)
        try:
            await self.session.send_json(
                {
                    "type": "workspace.call",
                    "id": req_id,
                    "token": self.token,
                    "op": op,
                    "args": args,
                }
            )
            result = await asyncio.wait_for(fut, timeout)
        except TimeoutError as exc:
            raise RuntimeError("local workspace call timed out") from exc
        finally:
            self.session.drop_workspace_waiter(req_id)
        if not isinstance(result, dict) or not result.get("ok"):
            message = ""
            if isinstance(result, dict):
                message = str(result.get("error") or "")
            raise RuntimeError(message or "local workspace call failed")
        return result

    async def call_text(self, op: str, args: dict[str, Any]) -> str:
        result = await self.call(op, args)
        text = str(result.get("text") or "")
        if op == "execute" and len(text) > _EXECUTE_CAP:
            text = text[-_EXECUTE_CAP:]
        return text or "(no output)"

    async def materialize(self, file_path: str) -> Path:
        result = await self.call("materialize", {"file_path": file_path})
        raw = base64.b64decode(str(result.get("b64") or ""))
        name = Path(str(result.get("name") or "file")).name or "file"
        folder = Path(tempfile.gettempdir()) / "octop-bridge-send"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{uuid.uuid4().hex}-{name}"
        dest.write_bytes(raw)
        return dest


def clear_local_workspace_state() -> None:
    """Drop in-memory grants. Tests use this."""
    _GRANTS.clear()
    _BY_DIR.clear()
    _TARGETS.clear()
    _THREADS.clear()


def _ensure_default_agent_workspace(path: Path) -> None:
    """Create the agent's default workspace when the chosen path is that default.

    Reuses :func:`default_agent_workspace_dir` so the bridge follows the same
    layout (and scoped-root handling) as agent creation. Other missing paths
    stay missing — a typo'd directory is not silently created.
    """
    from octop.infra.agents.workspace.dir import default_agent_workspace_dir
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout.from_env()
    try:
        default_path = default_agent_workspace_dir(paths, path.name, ensure=False)
        if default_path.resolve() != path.resolve():
            return
        default_agent_workspace_dir(paths, path.name, ensure=True)
    except OSError:
        return


def open_local_workspace(directory: str, connection_id: str) -> LocalWorkspaceGrant:
    """Root a local backend at ``directory`` and reuse its token for this link."""
    path = Path(directory).expanduser()
    if not path.is_absolute():
        raise LocalDirectoryError("relative")
    _ensure_default_agent_workspace(path)
    if not path.is_dir():
        raise LocalDirectoryError("missing")
    resolved = path.resolve()
    key = (connection_id, str(resolved))
    existing = _BY_DIR.get(key)
    if existing is not None:
        grant = _GRANTS.get(existing)
        if grant is not None:
            return grant
    from octop_harness.backends.workspace import BackendWorkspace

    from octop.infra.agents.teams.file_target import host_can_execute
    from octop.infra.backend.compat import adapt_backend_protocol
    from octop.infra.backend.resolve_backend import resolve_octop_backend

    spec = {"type": "local_shell", "root_dir": str(resolved), "virtual_mode": True}
    backend = adapt_backend_protocol(resolve_octop_backend(spec, workspace_dir=resolved))
    workspace = BackendWorkspace(backend, resolved)
    grant = LocalWorkspaceGrant(
        token=secrets.token_urlsafe(32),
        connection_id=connection_id,
        directory=str(resolved),
        execute=host_can_execute(backend),
        workspace=workspace,
        backend=backend,
    )
    _GRANTS[grant.token] = grant
    _BY_DIR[key] = grant.token
    return grant


def register_peer_target(
    token: str,
    *,
    session: Any,
    directory: str,
    execute: bool,
) -> PeerFileTarget:
    target = PeerFileTarget(
        token=token,
        directory=directory,
        execute=execute,
        session=session,
    )
    _TARGETS[token] = target
    return target


def lookup_peer_target(token: str) -> Any | None:
    return _TARGETS.get(token)


def replace_peer_target(token: str, target: Any) -> None:
    """Tests swap in a stub after ``register_peer_target``."""
    _TARGETS[token] = target


def remember_thread_target(thread_id: str, token: str) -> None:
    if thread_id and token:
        _THREADS[thread_id] = token


def peer_target_for_thread(thread_id: str) -> Any | None:
    token = _THREADS.get(thread_id)
    if not token:
        return None
    return _TARGETS.get(token)


def file_target_metadata(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Inbound metadata for a peer turn that should use the initiator's directory."""
    token = str(payload.get("file_target_token") or "").strip()
    directory = str(payload.get("local_directory") or "").strip()
    if not token or not directory:
        return None
    from octop.infra.agents.teams.file_target import turn_capabilities

    execute = bool(payload.get("local_execute"))
    extra = payload.get("local_capabilities")
    return {
        "bridge_file_target": {
            "token": token,
            "directory": directory,
            "execute": execute,
            "capabilities": turn_capabilities(
                execute=execute,
                extra=extra if isinstance(extra, dict) else None,
            ),
        }
    }


def stamp_bridge_file_target(
    request: dict[str, Any],
    meta: dict[str, Any] | None,
    *,
    locale: str,
    thread_id: str,
    agent: Any | None = None,
    member_agent_id: str = "",
) -> None:
    """Bind this expert turn to the initiator directory carried on the inbound."""
    raw = (meta or {}).get("bridge_file_target")
    if not isinstance(raw, dict):
        return
    token = str(raw.get("token") or "").strip()
    directory = str(raw.get("directory") or "").strip()
    if not token or not directory or lookup_peer_target(token) is None:
        return
    from octop.infra.agents.middleware.team_dispatch import CONFIG_KEY
    from octop.infra.agents.teams.file_target import (
        BRIDGE_TARGET_KEY,
        DIR_KEY,
        file_target_briefing,
        stamp_member_mounts,
        stamp_turn_capabilities,
    )

    remember_thread_target(thread_id, token)
    cfg = request.get("configurable")
    if not isinstance(cfg, dict):
        cfg = {}
        request["configurable"] = cfg
    execute = bool(raw.get("execute"))
    extra = raw.get("capabilities")
    cfg[BRIDGE_TARGET_KEY] = token
    cfg[DIR_KEY] = directory
    stamp_turn_capabilities(
        cfg,
        execute=execute,
        extra=extra if isinstance(extra, dict) else None,
    )
    mounts = stamp_member_mounts(cfg, agent, member_agent_id) if agent is not None else []
    note = file_target_briefing(
        locale,
        directory,
        execute=execute,
        managed=False,
        local=True,
        mounts=mounts,
    )
    existing = cfg.get(CONFIG_KEY)
    if isinstance(existing, str) and existing.strip():
        cfg[CONFIG_KEY] = f"{existing.rstrip()}\n\n{note}"
    else:
        cfg[CONFIG_KEY] = note


async def run_local_workspace_op(
    *,
    token: str,
    connection_id: str,
    op: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Execute one file op for a grant opened on this bridge connection."""
    grant = _GRANTS.get(token)
    if grant is None or grant.connection_id != connection_id:
        raise PermissionError("workspace is not available")
    if op == "materialize":
        return await _materialize(grant, str(args.get("file_path") or args.get("path") or ""))
    from octop.infra.agents.acp.team_workspace_mcp import (
        TeamWorkspaceScope,
        run_workspace_tool,
    )

    text = await run_workspace_tool(
        op,
        args,
        scope=TeamWorkspaceScope(
            host_agent_id="",
            directory=grant.directory,
            execute=grant.execute,
        ),
        workspace=grant.workspace,
        backend=grant.backend,
    )
    if op == "execute" and len(text) > _EXECUTE_CAP:
        text = text[-_EXECUTE_CAP:]
    return {"text": text}


async def _materialize(grant: LocalWorkspaceGrant, file_path: str) -> dict[str, Any]:
    path = file_path.strip()
    if not path:
        raise ValueError("file_path is required")
    local = await asyncio.to_thread(grant.workspace.materialize_local, path)
    if local is None or not local.is_file():
        raise FileNotFoundError(path)

    def _read() -> bytes:
        data = bytes(local.read_bytes())
        if len(data) > _SEND_CAP:
            raise ValueError("file is too large to send")
        return data

    data = await asyncio.to_thread(_read)
    return {"b64": base64.b64encode(data).decode("ascii"), "name": local.name}
