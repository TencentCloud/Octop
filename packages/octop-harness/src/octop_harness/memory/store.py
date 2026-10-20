"""Process-wide ``Memory`` reuse keyed by namespace + store location.

A ``HarnessAgent`` rebuild (MCP servers changed, security policy, …) used to
``close()`` the old runtime and construct a new ``Memory``. That opened a
fresh Postgres checkpointer pool and then tore down the old one — the
structural half of ``psycopg_pool.PoolClosed`` during hot-reload.

Declarative backends (sqlite path / postgres DSN) are acquired from this
store instead. Rebuild pins the entry so remove-then-create does not drop
the last ref; the new agent gets the same object. Graph, tools, middleware
and the aux LLM stay per-agent.

Pre-built ``MemoryBackend`` instances are not cached — the caller owns them.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

if TYPE_CHECKING:
    from octop_memory import Memory

    from octop_harness.config import HarnessAgentConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MemoryIdentity:
    """Cache key: one ``Memory`` per namespace + backend location."""

    namespace: str
    backend: str
    location: str


@dataclass
class _Entry:
    memory: Any
    refs: int


def resolve_backend_config(
    config: HarnessAgentConfig,
    workspace_path: Path,
    backend_type: str,
    backend_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Apply workspace-scoped defaults. Matches ``MemoryRuntime`` historically."""
    if backend_type != "sqlite":
        return dict(backend_config) if backend_config is not None else None
    resolved = dict(backend_config or {})
    prefix = str(config.system_files_path or "").strip()
    system = workspace_path / prefix if prefix else workspace_path
    resolved.setdefault("db_path", str(system / "memory.sqlite"))
    return resolved


def memory_identity(
    config: HarnessAgentConfig,
    workspace_path: Path,
) -> MemoryIdentity | None:
    """Return a shareable identity, or ``None`` when this Memory must stay private.

    ``None`` means memory is off, or the backend is a live instance we do not
    own (cannot key, cannot close on last-ref).
    """
    if not config.memory_enabled:
        return None
    spec = config.memory_backend
    namespace = str(config.memory_namespace or config.name or "").strip() or "octop-harness"
    if isinstance(spec, str):
        backend_type = spec
        backend_config = resolve_backend_config(config, workspace_path, backend_type, config.memory_backend_config)
    elif isinstance(spec, dict):
        backend_type = str(spec.get("type") or "sqlite")
        raw = {str(k): v for k, v in spec.items() if k != "type"}
        backend_config = resolve_backend_config(config, workspace_path, backend_type, raw)
    else:
        return None

    cfg = backend_config or {}
    if backend_type == "sqlite":
        raw_path = str(cfg.get("db_path") or "")
        try:
            location = str(Path(raw_path).expanduser().resolve())
        except OSError:
            location = raw_path
    elif backend_type == "postgres":
        location = str(cfg.get("dsn") or "").strip()
    else:
        return None
    return MemoryIdentity(namespace=namespace, backend=backend_type, location=location)


def close_memory_resources(memory: Any) -> None:
    """Release the backend connection and the checkpointer handle/pool."""
    pool = getattr(memory, "_checkpointer_pool", None)
    if pool is not None:
        with contextlib.suppress(Exception):
            close_fn = getattr(pool, "close", None)
            if callable(close_fn):
                close_fn()
        with contextlib.suppress(Exception):  # pragma: no cover - attribute may be missing
            memory._checkpointer_pool = None
    checkpointer = getattr(memory, "_checkpointer", None)
    if checkpointer is not None:
        cp_conn = getattr(checkpointer, "conn", None)
        if cp_conn is not None and cp_conn is not pool:
            with contextlib.suppress(Exception):
                cp_conn.close()
    backend = getattr(memory, "backend", None)
    close_fn = getattr(backend, "close", None)
    if callable(close_fn):
        try:
            close_fn()
        except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive shutdown
            logger.warning("Error closing memory backend", exc_info=True)


class SharedMemoryStore:
    """Refcounted ``Memory`` map. Last release closes connections."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[MemoryIdentity, _Entry] = {}

    def acquire(self, identity: MemoryIdentity, factory: Callable[[], Memory]) -> Memory:
        with self._lock:
            existing = self._entries.get(identity)
            if existing is not None:
                existing.refs += 1
                return existing.memory

        created = factory()
        with self._lock:
            existing = self._entries.get(identity)
            if existing is not None:
                existing.refs += 1
                extra = created
                kept = existing.memory
            else:
                self._entries[identity] = _Entry(memory=created, refs=1)
                extra = None
                kept = created
        if extra is not None:
            close_memory_resources(extra)
        return kept

    def release(self, identity: MemoryIdentity) -> None:
        with self._lock:
            existing = self._entries.get(identity)
            if existing is None:
                return
            existing.refs -= 1
            if existing.refs > 0:
                return
            del self._entries[identity]
            doomed = existing.memory
        close_memory_resources(doomed)

    @contextmanager
    def hold(self, identity: MemoryIdentity) -> Iterator[None]:
        """Pin an already-cached entry across a remove-then-create rebuild."""
        with self._lock:
            existing = self._entries.get(identity)
            if existing is None:
                held = False
            else:
                existing.refs += 1
                held = True
        try:
            yield
        finally:
            if held:
                self.release(identity)

    def refs(self, identity: MemoryIdentity) -> int:
        with self._lock:
            existing = self._entries.get(identity)
            return existing.refs if existing is not None else 0

    def peek(self, identity: MemoryIdentity) -> Any | None:
        with self._lock:
            existing = self._entries.get(identity)
            return existing.memory if existing is not None else None

    def reset(self) -> None:
        """Test helper: drop the map without closing (callers own teardown)."""
        with self._lock:
            self._entries.clear()


_STORE = SharedMemoryStore()


def shared_memory_store() -> SharedMemoryStore:
    return _STORE


@contextmanager
def hold_shared_memory(
    config: HarnessAgentConfig,
    workspace_path: Path | None,
) -> Iterator[None]:
    """Pin the shared ``Memory`` for ``config`` if one is already cached."""
    if workspace_path is None:
        workspace_path = Path(config.workspace_dir)
    identity = memory_identity(config, workspace_path)
    if identity is None:
        yield
        return
    with _STORE.hold(identity):
        yield


__all__ = [
    "MemoryIdentity",
    "SharedMemoryStore",
    "close_memory_resources",
    "hold_shared_memory",
    "memory_identity",
    "resolve_backend_config",
    "shared_memory_store",
]
