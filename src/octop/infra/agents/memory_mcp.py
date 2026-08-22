"""Expose Octop expert memory as an MCP server for external agents.

External agents (coding agents, bots) can read/write Octop expert memory over
MCP (Streamable HTTP), aligned with the in-process ``MemoryService``
capabilities. Every write stamps a ``source`` marker that can be traced back
on recall.

Expert binding: the endpoint is a single ``/mcp/memory`` mount; the expert is
selected at connect time via the ``X-Octop-Agent-Id`` header (one connection
binds one expert — the caller never passes an agent id per tool call).

raw vs atom (aligned with ``MemoryService``):

* ``memory_capture`` -> ``add_raw``: writes an **L0 raw event**, which goes
  through the extraction pipeline (extract -> candidate -> promote -> atom).
  Use it to record raw conversations / events. The record is visible
  immediately via ``memory_search_raw``; ``memory_recall`` returns it only
  after extraction promotes it to an atom.
* ``memory_save`` -> ``store``: persists a structured fact directly into the
  canonical atom/tree (durable, no extraction). Use it when you already know
  the exact fact to remember.

Auth: independent token via ``OCTOP_MEMORY_MCP_TOKEN`` (fail-closed when
unset), enforced by the ASGI middleware in ``mount_memory_mcp``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from octop.infra.agents.memory_backend import open_memory_kwargs
from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)


def _open_memory(server: OctopServer, agent_id: str) -> Any:
    """Open the agent's ``Memory`` instance (sqlite by default, postgres opt-in).

    Mirrors ``api.common.memory_client._open_memory_for_agent`` but stays in
    ``infra/`` (no api dependency). Workspace is resolved from the agent
    registry, falling back to the Octop default layout.
    """
    from harness_memory.core import Memory  # noqa: PLC0415

    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is not None and hasattr(registry, "resolve_workspace_dir"):
        workspace = registry.resolve_workspace_dir(agent_id)
    else:
        paths = getattr(server, "paths", None) or server.services.paths
        workspace = paths.ensure_agent_workspace(agent_id)

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
    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def build_memory_mcp(server: OctopServer, agent_id: str) -> FastMCP:
    """Build an MCP server bound to one expert (``agent_id`` captured in closure)."""
    mcp = FastMCP(
        f"octop-memory-{agent_id}",
        # Octop runs behind a reverse proxy (Host is the public domain, forwarded
        # by nginx), not a localhost dev scenario — the mcp SDK's localhost
        # DNS-rebinding protection does not apply and would reject the Host
        # with 421 unless the domain is allow-listed.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    # Collapse the streamable-HTTP path to "/" so the endpoint is exactly
    # /mcp/memory (the default "/mcp" would make it /mcp/memory/mcp).
    mcp.settings.streamable_http_path = "/"

    def _memory():
        return _open_memory(server, agent_id)

    @mcp.tool()
    def memory_recall(query: str, limit: int = 5) -> dict[str, Any]:
        """Recall memories from this expert (aligned with the in-process recall_inject).

        Runs the full recall pipeline (tokenization -> FTS -> rerank -> dedupe)
        and returns structured snippets plus a rendered markdown block ready to
        inject into a system prompt.

        Args:
            query: free-form question / keywords (pass the whole sentence; the
                pipeline tokenizes CJK into n-grams internally).
            limit: max number of snippets to return.
        """
        from harness_memory.pipeline.recall import recall_for_prompt  # noqa: PLC0415

        memory = _memory()
        result = recall_for_prompt(memory, query, limit=limit)
        return {
            "memories": [
                {
                    "source_id": s.source_id,
                    "timestamp": s.timestamp_iso,
                    "layer": s.layer,
                    "text": s.text,
                }
                for s in result.snippets
            ],
            "count": len(result.snippets),
            "rendered": result.rendered,
        }

    @mcp.tool()
    def memory_save(
        content: str,
        source: str,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """Persist a structured fact directly (atom/tree, durable, no extraction).

        Use this when you already know the exact fact to remember — it is
        immediately recallable via ``memory_recall``. The source marker is
        stored in ``metadata.source``.

        Args:
            content: the fact to remember.
            source: who/what recorded it (e.g. "coding-agent"), for traceability.
            topic: optional topic label.
        """
        memory = _memory()
        node = memory.store(content, topic=topic, metadata={"source": source})
        return {"node_id": node.id, "content": node.content, "source": source}

    @mcp.tool()
    def memory_capture(content: str, source: str, session_id: str | None = None) -> dict[str, Any]:
        """Record a raw event to L0 (goes through extraction: extract -> candidate -> atom).

        Use this to record raw conversations / events that the extraction
        pipeline will later distill into atoms. The record is NOT immediately
        recallable via ``memory_recall`` (that reads atoms); query it right
        away with ``memory_search_raw``. The source marker is stored in
        ``payload.source``.

        Example::

            memory_capture(
                content="user reported: the report panel banner is not rendering",
                source="review-bot",
                session_id="review-2026-08-20",
            )
            # -> {"event_id": "...", "recorded": true, ...}
            # later: memory_recall(query="report panel banner not rendering")

        Args:
            content: the raw conversation / event text.
            source: who/what recorded it, for traceability.
            session_id: optional stable session id (e.g. caller name) so the
                extraction pipeline can group events by session.
        """
        memory = _memory()
        raw = memory.add_raw(
            content,
            event_type="manual",
            host="mcp-external",
            session_id=session_id,
            payload={"source": source},
        )
        return {
            "event_id": raw.id,
            "source": source,
            "recorded": True,
            "note": (
                "raw (L0) event recorded; visible now via memory_search_raw, "
                "recallable via memory_recall after the extraction pipeline "
                "promotes it to an atom"
            ),
        }

    @mcp.tool()
    def memory_search_raw(query: str, limit: int = 10) -> dict[str, Any]:
        """FTS-search L0 raw events of this expert (capture visible immediately).

        Unlike ``memory_recall`` (which reads atoms), this searches the raw
        event layer, so records written by ``memory_capture`` are visible right
        away, before extraction promotes them.

        Args:
            query: keywords to match against raw event content.
            limit: max number of events to return.
        """
        memory = _memory()
        events = memory.search_raw(query, limit=limit)
        return {
            "events": [
                {
                    "event_id": e.id,
                    "timestamp": e.timestamp.isoformat(),
                    "session_id": e.session_id,
                    "user": e.user,
                    "source": (e.payload or {}).get("source") if e.payload else None,
                    "content": e.content,
                }
                for e in events
            ],
            "count": len(events),
        }

    @mcp.tool()
    def memory_update(
        atom_id: str,
        new_content: str,
        source: str,
        note: str = "mcp update",
    ) -> dict[str, Any]:
        """Update a memory: deprecate the old atom and persist the new fact.

        Args:
            atom_id: id of the atom to supersede.
            new_content: the replacement fact.
            source: who/what updated it, for traceability.
            note: deprecation note.
        """
        memory = _memory()
        deprecated = memory.deprecate_atom(atom_id, actor="user", note=note)
        node = memory.store(new_content, metadata={"source": source, "supersedes": atom_id})
        return {
            "deprecated": deprecated,
            "deprecated_atom_id": atom_id,
            "new_node_id": node.id,
            "source": source,
        }

    return mcp


def _memory_mcp_token() -> str | None:
    """Read the MCP auth token (empty string treated as unconfigured)."""
    return (os.environ.get("OCTOP_MEMORY_MCP_TOKEN") or "").strip() or None


class _TokenAuthMiddleware:
    """ASGI middleware enforcing ``Authorization: Bearer`` or ``X-Octop-Memory-Token``."""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        provided = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not provided:
            provided = headers.get("x-octop-memory-token", "").strip()

        if provided != self._token:
            body = b'{"error":"unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self._app(scope, receive, send)


class _AgentRouter:
    """ASGI dispatcher routing to the per-expert MCP app by ``X-Octop-Agent-Id`` header."""

    def __init__(self, mcp_apps: dict[str, Any]) -> None:
        self._mcp_apps = mcp_apps

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            return  # lifespan is wired into the host FastAPI manually; http only here

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        agent_id = headers.get("x-octop-agent-id", "").strip()
        target = self._mcp_apps.get(agent_id)
        if target is None:
            body = b'{"error":"missing or unknown agent_id (X-Octop-Agent-Id)"}'
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await target(scope, receive, send)


def mount_memory_mcp(app: Any, server: OctopServer) -> list[Any]:
    """Mount the memory MCP endpoint at ``/mcp/memory``; the expert is selected
    per connection via the ``X-Octop-Agent-Id`` header (one connection binds one
    expert; the URL stays uniform and does not leak expert ids).

    Does not mount when ``OCTOP_MEMORY_MCP_TOKEN`` is unset (fail-closed).
    Returns the session managers that must be initialized in the host FastAPI
    lifespan (``streamable_http_app`` task groups depend on it).
    """
    token = _memory_mcp_token()
    if token is None:
        return []

    managers: list[Any] = []
    mcp_apps: dict[str, Any] = {}
    rows = server.services.agent_repo.list_all(include_disabled=False)
    for row in rows:
        agent_id = row.agent_id
        mcp = build_memory_mcp(server, agent_id)
        mcp_apps[agent_id] = mcp.streamable_http_app()
        managers.append(mcp._session_manager)

    app.mount("/mcp/memory", _TokenAuthMiddleware(_AgentRouter(mcp_apps), token))
    return managers


__all__ = ["build_memory_mcp", "mount_memory_mcp"]
