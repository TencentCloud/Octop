"""Per-agent ``Memory`` instance management for the dashboard router.

Owns a tiny LRU cache of ``octop_memory.core.Memory`` instances
keyed by ``agent_id``. Backend may be sqlite (default workspace file) or
postgres when ``config_json.memory.backend`` says so.

Each cached instance owns real connections — on PostgreSQL one backend
connection plus a checkpointer pool (``min_size=1``). Entries are therefore
closed once nothing has touched them for ``_IDLE_TTL_SECONDS``; without that,
every agent ever opened from the dashboard pinned its connections for the
life of the process until PostgreSQL refused new ones.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.api.common.agent import require_agent_owner_row
from octop.infra.agents.memory.backend import open_memory_kwargs
from octop.infra.agents.workspace.dir import host_system_dir
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_MEMORY_NS_PREFIX = "agent_"


def memory_namespace(agent_id: str) -> str:
    """Return the memory namespace octop-memory uses for ``agent_id``."""
    return f"{_MEMORY_NS_PREFIX}{agent_id}"


def memory_db_path(workspace_dir: Path) -> Path:
    """Return the default SQLite file path within an agent workspace.

    Prefer an explicit on-disk file. When neither exists, treat a populated
    ``.octop/_builtin_skills`` tree as the new-layout signal (empty ``.octop/``
    alone is not enough for legacy agents).
    """
    nested = workspace_dir / ".octop" / "memory.sqlite"
    root = workspace_dir / "memory.sqlite"
    if nested.exists():
        return nested
    if root.exists():
        return root
    if (workspace_dir / ".octop" / "_builtin_skills").is_dir():
        return nested
    return root


def memory_db_path_for_cfg(workspace_dir: Path, cfg: dict[str, Any] | None) -> Path:
    """Return the default SQLite file path for a specific agent config."""
    return host_system_dir(workspace_dir, cfg) / "memory.sqlite"


_MAX_CACHED = 16
# Dashboard reads are bursty: an agent is opened, a few RPCs run, then it can
# go quiet for hours. Releasing its connections after this much silence keeps
# the pool bounded without reconnecting on every page load.
_IDLE_TTL_SECONDS = 900.0
# Idle entries are released by a background sweep rather than lazily on the
# next ``get_or_open``: an install can stop touching the dashboard entirely,
# which is exactly the state the leak was reported in.
_IDLE_SWEEP_SECONDS = 60.0


@dataclass
class _CacheEntry:
    memory: Any
    bridge: Any
    fingerprint: str
    last_used: float


class _MemoryCache:
    """Thread-safe LRU of ``agent_id -> _CacheEntry`` with idle release.

    Every drop path (idle timeout, LRU eviction, config change, explicit
    invalidation) closes the entry's backend connection and checkpointer
    pool; a dropped entry that kept them open would leak exactly like never
    dropping it at all.

    Closing is not synchronized with in-flight RPCs — a request that has
    already taken an entry may lose it to the sweeper. The TTL is orders of
    magnitude longer than a dashboard RPC, so this stays theoretical.
    """

    def __init__(
        self,
        max_size: int = _MAX_CACHED,
        idle_ttl: float = _IDLE_TTL_SECONDS,
    ) -> None:
        self._max_size = max_size
        self._idle_ttl = idle_ttl
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._reaper: threading.Thread | None = None

    def get_or_open(
        self,
        agent_id: str,
        *,
        backend: str,
        backend_config: dict[str, Any] | None,
        fingerprint: str,
    ) -> tuple[Any, Any]:
        from octop_memory.adapters.bridge.handlers import Bridge  # noqa: PLC0415
        from octop_memory.core import Memory  # noqa: PLC0415

        now = time.monotonic()
        dropped: list[tuple[str, _CacheEntry, str]] = []
        with self._lock:
            self._start_reaper_locked()
            cached = self._entries.get(agent_id)
            if cached is not None and cached.fingerprint == fingerprint:
                cached.last_used = now
                self._entries.move_to_end(agent_id)
                return cached.memory, cached.bridge
            # Config changed under the same agent id: the old backend is now
            # unreachable through the cache, so its connections must go.
            replaced = self._entries.pop(agent_id, None)
            if replaced is not None:
                dropped.append((agent_id, replaced, "replaced"))

            ns = memory_namespace(agent_id)
            memory = Memory(
                namespace=ns,
                backend=backend,
                backend_config=backend_config,
            )
            bridge = Bridge(memory)
            self._entries[agent_id] = _CacheEntry(memory, bridge, fingerprint, now)
            while len(self._entries) > self._max_size:
                evicted_id, evicted = self._entries.popitem(last=False)
                dropped.append((evicted_id, evicted, "evicted"))
        for dropped_id, entry, reason in dropped:
            self._release(dropped_id, entry, reason=reason)
        return memory, bridge

    def invalidate(self, agent_id: str | None = None) -> None:
        with self._lock:
            if agent_id is None:
                dropped = [(aid, entry, "invalidated") for aid, entry in self._entries.items()]
                self._entries.clear()
            else:
                entry = self._entries.pop(agent_id, None)
                dropped = [(agent_id, entry, "invalidated")] if entry is not None else []
        for dropped_id, entry, reason in dropped:
            self._release(dropped_id, entry, reason=reason)

    def _start_reaper_locked(self) -> None:
        if self._reaper is not None:
            return
        self._reaper = threading.Thread(
            target=self._reap_idle,
            name="octop-memory-cache-reaper",
            daemon=True,
        )
        self._reaper.start()

    def _reap_idle(self) -> None:
        while True:
            time.sleep(_IDLE_SWEEP_SECONDS)
            self.sweep_idle()

    def sweep_idle(self) -> None:
        """Release entries untouched for ``idle_ttl``. One pass, then return."""
        cutoff = time.monotonic() - self._idle_ttl
        with self._lock:
            stale = [
                (aid, entry) for aid, entry in self._entries.items() if entry.last_used <= cutoff
            ]
            for stale_id, _ in stale:
                del self._entries[stale_id]
        for stale_id, entry in stale:
            self._release(stale_id, entry, reason="idle")

    @staticmethod
    def _release(agent_id: str, entry: _CacheEntry, *, reason: str) -> None:
        """Close one entry's connections. Never raises into the RPC path."""
        from octop_harness.memory.store import close_memory_resources  # noqa: PLC0415

        logger.debug("memory dashboard cache %s agent_id=%s", reason, agent_id)
        try:
            close_memory_resources(entry.memory)
        except Exception:  # noqa: BLE001 - shutdown must not break the caller
            logger.warning("failed closing cached memory agent_id=%s", agent_id, exc_info=True)


_CACHE = _MemoryCache()


def _open_memory_for_agent(server: Any, agent_id: str) -> tuple[Any, Any]:
    from octop.api.common.agent_workspace import resolve_agent_workspace_dir  # noqa: PLC0415

    workspace = resolve_agent_workspace_dir(server, agent_id)
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
        db_path = Path(
            (backend_config or {}).get("db_path") or memory_db_path_for_cfg(workspace, cfg)
        )
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
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    runtime = server.app_runtime
    coordinator = runtime.agent_registry.memory_slim if runtime is not None else None
    if coordinator is not None:
        status = coordinator.status(agent_id)
        if isinstance(status, dict) and status.get("phase") in {
            "backing_up",
            "deduplicating",
            "compacting",
        }:
            # Avoid synchronous dashboard writes holding the event loop in a
            # SQLite busy wait while maintenance status needs to remain visible.
            raise OctopError.localized(ErrorCode.AGENT_BUSY)
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
    "memory_db_path_for_cfg",
    "memory_namespace",
]
