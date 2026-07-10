"""Per-agent ``Memory`` instance management for the dashboard router.

Owns a tiny LRU cache of ``harness_memory.core.Memory`` instances
keyed by ``agent_id``. Each instance opens (and reuses) its own
SQLite connection to ``~/.octop/agents/<agent_id>/memory.sqlite`` so
that successive list / stats calls don't pay re-open cost on every
HTTP hit.

Why a separate module:

* The dashboard router is the *only* place inside octop that talks
  directly to a Memory; isolating the wiring here keeps the router
  small and lets unit tests inject a stub easily.
* ``AgentManager`` already manages a separate ``HarnessAgent``
  pipeline per agent — that path goes through harness-agent's
  middleware. The dashboard surface deliberately bypasses it: the
  middleware adds capture / extract logic that is irrelevant for
  read-only inspection RPCs and would make rejecting a candidate
  much harder to reason about.
* harness-memory namespace logic is mirrored from
  ``octop.infra.agents.manager._memory_namespace`` so we never get
  a different table prefix than the agent runtime uses.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from octop.api.common.agent import require_agent_row
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)


# Mirror harness_memory's namespace shape used by AgentManager. Kept in
# sync manually rather than imported because that module owns it as a
# private symbol — the duplication is one tiny constant and the runtime
# would silently mismatch if we imported it then later AgentManager
# changed shape.
_MEMORY_NS_PREFIX = "agent_"


def memory_namespace(agent_id: str) -> str:
    """Return the SQLite table prefix harness-memory uses for ``agent_id``."""
    return f"{_MEMORY_NS_PREFIX}{agent_id}"


def memory_db_path(workspace_dir: Path) -> Path:
    """Return the SQLite file path within an agent workspace."""
    return workspace_dir / "memory.sqlite"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


_MAX_CACHED = 16
"""Max in-process Memory instances. SQLite connections are cheap, but
we cap to keep file descriptors bounded under heavy multi-agent
dashboard browsing."""


class _MemoryCache:
    """Thread-safe LRU of ``(agent_id) -> (memory, bridge)``."""

    def __init__(self, max_size: int = _MAX_CACHED) -> None:
        self._max_size = max_size
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[Any, Any, str]] = OrderedDict()

    def get_or_open(self, agent_id: str, db_path: Path) -> tuple[Any, Any]:
        # Late-imported so the octop process can still start when
        # harness-memory's optional dependencies aren't fully installed
        # in some dev sandboxes — the dashboard endpoints just 503 in
        # that case rather than the whole server failing to boot.
        from harness_memory.adapters.bridge.handlers import Bridge  # noqa: PLC0415
        from harness_memory.core import Memory  # noqa: PLC0415

        path_str = str(db_path)
        with self._lock:
            cached = self._entries.get(agent_id)
            if cached is not None and cached[2] == path_str:
                self._entries.move_to_end(agent_id)
                return cached[0], cached[1]

            ns = memory_namespace(agent_id)
            memory = Memory(
                namespace=ns,
                backend="sqlite",
                backend_config={"db_path": path_str},
            )
            bridge = Bridge(memory)
            self._entries[agent_id] = (memory, bridge, path_str)
            while len(self._entries) > self._max_size:
                _, evicted = self._entries.popitem(last=False)
                logger.debug("memory dashboard cache evicted agent_id=%s", evicted)
            return memory, bridge

    def invalidate(self, agent_id: str | None = None) -> None:
        """Drop one or all cached instances. Called when agents are deleted."""
        with self._lock:
            if agent_id is None:
                self._entries.clear()
            else:
                self._entries.pop(agent_id, None)


_CACHE = _MemoryCache()


def _open_memory_for_agent(server: Any, agent_id: str) -> tuple[Any, Any]:
    """Resolve agent workspace, open Memory + Bridge (cached).

    Returns ``(memory, bridge)``. The bridge already has the dashboard
    RPC table merged into its dispatch by ``Bridge.__init__`` — so the
    router can call ``bridge.handle({...})`` without further wiring.
    """
    workspace = server.services.paths.ensure_agent_workspace(agent_id)
    db_path = memory_db_path(workspace)
    if not db_path.exists():
        # The DB file is created lazily by the harness-agent runtime on
        # the first ``add_raw`` call. Until that happens, the agent has
        # nothing to inspect.
        # We still open the connection (Memory will create the file +
        # schema), so the dashboard returns empty lists rather than 404.
        # Caller controls the create behavior via the ``mode`` SQLite
        # uri flag — for now we just let Memory create-on-open since
        # that's the default.
        logger.debug(
            "memory db not yet created for agent %s; opening will create empty schema", agent_id
        )
    return _CACHE.get_or_open(agent_id, db_path)


# ---------------------------------------------------------------------------
# Public API used by the FastAPI router
# ---------------------------------------------------------------------------


def call_memory_rpc(
    *,
    agent_id: str,
    method: str,
    params: dict[str, Any] | None,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Any:
    """Authenticate the caller, open the Memory backend, dispatch via Bridge.

    Translates the bridge JSON-RPC envelope into either:
    * the ``result`` payload (success → router returns it as JSON), or
    * an :class:`OctopError` with the canonical error code.

    Specifically:
    * ``ERR_PATH_NOT_FOUND`` → ``OctopError(NOT_FOUND, ...)`` (HTTP 404)
    * ``ERR_INVALID_PARAMS``  → ``OctopError(INVALID_PARAM, ...)`` (HTTP 400)
    * any other code           → ``OctopError(INTERNAL_ERROR, ...)`` (HTTP 500)

    The router itself does not need to know about JSON-RPC — it just
    builds the params dict and trusts this helper.
    """
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
            # ErrorCode has no INVALID_PARAM enum — fall back to
            # INTERNAL_ERROR semantics with an explicit HTTP 400 so the
            # frontend shows the user-fixable validation message.
            raise OctopError(ErrorCode.INTERNAL_ERROR, message, status=400)
        if code == -32601:  # ERR_METHOD_NOT_FOUND
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"unknown memory dashboard method: {method!r}",
            )
        raise OctopError(ErrorCode.INTERNAL_ERROR, message)
    return response["result"]


def invalidate_cached_memory(agent_id: str | None = None) -> None:
    """Drop cached Memory(s); call when an agent is deleted or moved.

    Currently exported but not yet wired from the agent lifecycle —
    until it is, the LRU cap keeps the cache bounded.
    """
    _CACHE.invalidate(agent_id)


__all__ = [
    "call_memory_rpc",
    "invalidate_cached_memory",
    "memory_db_path",
    "memory_namespace",
]
