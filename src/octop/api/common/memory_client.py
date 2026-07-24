"""Per-agent ``Memory`` instance management for the dashboard router.

Owns a tiny LRU cache of ``harness_memory.core.Memory`` instances
keyed by ``agent_id``. Backend may be sqlite (default workspace file) or
postgres when ``config_json.memory.backend`` says so.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from octop.api.common.agent import require_agent_row
from octop.infra.agents.memory_backend import open_memory_kwargs
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_MEMORY_NS_PREFIX = "agent_"


def memory_namespace(agent_id: str) -> str:
    """Return the memory namespace harness-memory uses for ``agent_id``."""
    return f"{_MEMORY_NS_PREFIX}{agent_id}"


def memory_db_path(workspace_dir: Path) -> Path:
    """Return the default SQLite file path within an agent workspace."""
    return workspace_dir / "memory.sqlite"


_MAX_CACHED = 16


class _MemoryCache:
    """Thread-safe LRU of ``(agent_id) -> (memory, bridge, fingerprint)``."""

    def __init__(self, max_size: int = _MAX_CACHED) -> None:
        self._max_size = max_size
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[Any, Any, str]] = OrderedDict()

    def get_or_open(
        self,
        agent_id: str,
        *,
        backend: str,
        backend_config: dict[str, Any] | None,
        fingerprint: str,
    ) -> tuple[Any, Any]:
        from harness_memory.adapters.bridge.handlers import Bridge  # noqa: PLC0415
        from harness_memory.core import Memory  # noqa: PLC0415

        with self._lock:
            cached = self._entries.get(agent_id)
            if cached is not None and cached[2] == fingerprint:
                self._entries.move_to_end(agent_id)
                return cached[0], cached[1]

            ns = memory_namespace(agent_id)
            memory = Memory(
                namespace=ns,
                backend=backend,
                backend_config=backend_config,
            )
            bridge = Bridge(memory)
            self._entries[agent_id] = (memory, bridge, fingerprint)
            while len(self._entries) > self._max_size:
                _, evicted = self._entries.popitem(last=False)
                logger.debug("memory dashboard cache evicted agent_id=%s", evicted)
            return memory, bridge

    def invalidate(self, agent_id: str | None = None) -> None:
        with self._lock:
            if agent_id is None:
                self._entries.clear()
            else:
                self._entries.pop(agent_id, None)


_CACHE = _MemoryCache()


def _open_memory_for_agent(server: Any, agent_id: str) -> tuple[Any, Any]:
    workspace = server.services.paths.ensure_agent_workspace(agent_id)
    row = server.services.agent_repo.get(agent_id)
    cfg: dict[str, Any] = {}
    if row is not None and row.config_json:
        import json  # noqa: PLC0415

        try:
            parsed = json.loads(row.config_json)
            if isinstance(parsed, dict):
                cfg = parsed
        except json.JSONDecodeError:
            cfg = {}

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=server.services.config,
        workspace_dir=workspace,
    )
    fingerprint = f"{ns}:{backend}:{backend_config}"
    if backend == "sqlite":
        db_path = Path((backend_config or {}).get("db_path") or memory_db_path(workspace))
        if not db_path.exists():
            logger.debug(
                "memory db not yet created for agent %s; opening will create empty schema",
                agent_id,
            )
    return _CACHE.get_or_open(
        agent_id,
        backend=backend,
        backend_config=backend_config,
        fingerprint=fingerprint,
    )


def call_memory_rpc(
    *,
    agent_id: str,
    method: str,
    params: dict[str, Any] | None,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Any:
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    _memory, bridge = _open_memory_for_agent(server, agent_id)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    response = bridge.handle(payload)
    if "error" in response:
        err = response["error"]
        code = err.get("code")
        message = err.get("message", "memory bridge error")
        if code == -32010:  # ERR_PATH_NOT_FOUND
            raise OctopError(ErrorCode.NOT_FOUND, message)
        if code == -32602:  # ERR_INVALID_PARAMS
            raise OctopError(ErrorCode.INTERNAL_ERROR, message, status=400)
        if code == -32601:  # ERR_METHOD_NOT_FOUND
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"unknown memory dashboard method: {method!r}",
            )
        raise OctopError(ErrorCode.INTERNAL_ERROR, message)
    return response["result"]


def invalidate_cached_memory(agent_id: str | None = None) -> None:
    _CACHE.invalidate(agent_id)


__all__ = [
    "call_memory_rpc",
    "invalidate_cached_memory",
    "memory_db_path",
    "memory_namespace",
]
