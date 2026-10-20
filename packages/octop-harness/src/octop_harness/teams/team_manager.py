"""Peer discovery and collaboration via :class:`~octop_harness.registry.AgentRegistry`."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from octop_harness.messages import extract_call_response
from octop_harness.registry import AgentEntry, AgentRegistry
from octop_harness.request import ChatRequest
from octop_harness.teams.inbox import (
    DEFAULT_INBOX_MAX_CONCURRENCY,
    HarnessAgentInboxManager,
    InboxMessage,
    PeerResult,
)
from octop_harness.teams.processor import TeamProcessor
from octop_harness.teams.profile import Language
from octop_harness.teams.tools import build_team_tools
from octop_harness.teams.util import (
    PEER_IDENTITY_CONFIG_KEYS,
    PeerCall,
    PeerInvokeMode,
    PeerSession,
    build_one_shot_request,
    derive_peer_thread_id,
    parse_team_peers,
)

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


def _request_team_peers() -> tuple[str, ...] | None:
    """Read a request-scoped ``team_peers`` allowlist from LangGraph config."""
    try:
        from langgraph.config import get_config

        cfg = get_config().get("configurable") or {}
    except Exception:  # no request config outside a graph run; pylint: disable=broad-except
        return None
    return parse_team_peers(cfg.get("team_peers"))


EnrichRequest = Callable[[str, ChatRequest], Awaitable[ChatRequest]]
AfterCall = Callable[[], Awaitable[None]]
PeerEnrich = Callable[[AgentEntry], None]
PreparePeerSession = Callable[[PeerCall], Awaitable[PeerSession | None]]
AfterPeerCall = Callable[[PeerCall, str, dict[str, Any]], Awaitable[None]]


class TeamManager:
    """Peer listing, sync/async collaboration, and inbox wiring."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._inbox: HarnessAgentInboxManager | None = None
        self._enrich_request: EnrichRequest | None = None
        self._after_call: AfterCall | None = None
        self._peer_enrich: PeerEnrich | None = None
        self._prepare_peer: PreparePeerSession | None = None
        self._after_peer: AfterPeerCall | None = None

    def bind_invocation_hooks(
        self,
        *,
        enrich_request: EnrichRequest | None = None,
        after_call: AfterCall | None = None,
    ) -> None:
        """Optional hooks from :class:`~octop_harness.manager.HarnessAgentManager` (langfuse, etc.)."""
        self._enrich_request = enrich_request
        self._after_call = after_call

    def bind_peer_enrich(self, enrich: PeerEnrich | None) -> None:
        """Host hook to refresh ``AgentEntry.metadata`` before roster / ``agent_list``.

        Called once per returned peer on :meth:`list_peers`. Hosts that snapshot
        description or guidance cards at agent start should re-read them here so
        edits apply without a restart.
        """
        self._peer_enrich = enrich

    def bind_peer_session(
        self,
        *,
        prepare: PreparePeerSession | None = None,
        after: AfterPeerCall | None = None,
    ) -> None:
        """Host hooks to map a peer call onto a durable callee session.

        *prepare* may rewrite ``thread_id`` / ``session_key`` / ``message``
        / ``configurable`` (for example Octop's ``threads`` table and a
        group-chat transcript). Identity keys in ``configurable``
        (``agent_id``, ``user``, ``thread_id``, ``source``) are ignored.
        *after* sees the message actually delivered to the callee. Harness
        still derives a stable ``thread_id`` from the caller's thread when
        the host leaves it unset.
        """
        self._prepare_peer = prepare
        self._after_peer = after

    # ------------------------------------------------------------------
    # Inbox / processor lifecycle
    # ------------------------------------------------------------------

    def set_processor(
        self,
        processor: TeamProcessor | None,
        *,
        max_concurrency: int = DEFAULT_INBOX_MAX_CONCURRENCY,
    ) -> None:
        """Enable (or disable) inbox-driven async collaboration."""
        if processor is None:
            if self._inbox is not None:
                self._inbox.cancel_worker()
            self._inbox = None
            return
        self._inbox = HarnessAgentInboxManager(
            call_agent=self._call_agent,
            processor=processor,
            invoke_target=self._invoke_inbox_target,
            max_concurrency=max_concurrency,
        )

    @property
    def enabled(self) -> bool:
        """``True`` when an inbox/TeamProcessor is configured (async available)."""
        return self._inbox is not None

    @property
    def inbox(self) -> HarnessAgentInboxManager | None:
        return self._inbox

    def close(self) -> None:
        if self._inbox is not None:
            self._inbox.cancel_worker()

    async def aclose(self) -> None:
        if self._inbox is not None:
            await self._inbox.shutdown()

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def team_tools(
        self,
        *,
        agent_id: str | None = None,
        peer_invoke_mode: PeerInvokeMode | None = None,
    ) -> list[StructuredTool]:
        """Return ``agent_list`` / ``ask_agent`` bound to this manager.

        Kept for hosts that still append these to ``config.tools``. Agents
        created through ``HarnessAgentManager`` with ``team_enabled`` already
        get the same tools from ``PeerAgentMiddleware`` — do not add both, or the
        model will see duplicates.

        Pass *agent_id* (or an explicit *peer_invoke_mode*) so the schema
        matches that agent's ``peer_invoke_mode`` instead of defaulting to
        ``both``.
        """
        mode = peer_invoke_mode
        if mode is None and agent_id is not None:
            mode = self.peer_invoke_mode_for(agent_id)
        return build_team_tools(self, peer_invoke_mode=mode or "both")

    # ------------------------------------------------------------------
    # Peer discovery
    # ------------------------------------------------------------------

    def list_peers(
        self,
        user_id: str | int,
        *,
        exclude_agent_id: str | None = None,
        team_peers: Sequence[str] | None = None,
    ) -> list[AgentEntry]:
        wanted = str(user_id)
        by_id: dict[str, AgentEntry] = {}
        for entry in self._registry.list():
            meta_uid = entry.metadata.get("user_id")
            if meta_uid is None or str(meta_uid) == wanted:
                by_id[entry.agent_id] = entry
        peers = list(by_id.values())
        if exclude_agent_id is not None:
            peers = [e for e in peers if e.agent_id != exclude_agent_id]
        allowlist = self._peer_allowlist(exclude_agent_id)
        if allowlist is not None:
            peers = self._filter_peers(peers, allowlist)
        override: Sequence[str] | None = team_peers
        if override is None:
            override = _request_team_peers()
        if override is not None:
            names = tuple(str(n).strip().lstrip("@") for n in override if str(n).strip())
            peers = self._filter_peers(peers, names)
        self._apply_peer_enrich(peers)
        return peers

    def peer_invoke_mode_for(self, agent_id: str) -> PeerInvokeMode | None:
        """Return the calling agent's configured ``peer_invoke_mode``, if any."""
        try:
            return self._registry.get(agent_id).config.peer_invoke_mode
        except KeyError:
            return None

    def caller_language(self, from_agent_id: str) -> Language:
        """UI language of the calling agent (``agent_list`` localization)."""
        try:
            lang = self._registry.get(from_agent_id).config.language
        except KeyError:
            return "zh"
        return "en" if lang == "en" else "zh"

    def _apply_peer_enrich(self, peers: list[AgentEntry]) -> None:
        enrich = self._peer_enrich
        if enrich is None:
            return
        for entry in peers:
            try:
                enrich(entry)
            except Exception:  # peer metadata is best-effort; pylint: disable=broad-except
                logger.warning(
                    "peer metadata enrich failed for %s",
                    entry.agent_id,
                    exc_info=True,
                )

    def _peer_allowlist(self, from_agent_id: str | None) -> tuple[str, ...] | None:
        """Return the calling agent's ``team_peers`` allowlist, or ``None`` for all."""
        if not from_agent_id:
            return None
        try:
            entry = self._registry.get(from_agent_id)
        except KeyError:
            return None
        names = entry.config.team_peers
        if names is None:
            return None
        cleaned = tuple(n.strip().lstrip("@") for n in names if str(n).strip())
        return cleaned

    def _filter_peers(self, peers: list[AgentEntry], names: Sequence[str]) -> list[AgentEntry]:
        if not names:
            return []
        out: list[AgentEntry] = []
        seen: set[str] = set()
        for raw in names:
            matched = self._match_peer(peers, raw)
            if matched is not None and matched.agent_id not in seen:
                seen.add(matched.agent_id)
                out.append(matched)
        return out

    def resolve_peer(
        self,
        user_id: str | int,
        query: str,
        *,
        exclude_agent_id: str | None = None,
    ) -> AgentEntry | None:
        rows = self.list_peers(user_id, exclude_agent_id=exclude_agent_id)
        return self._match_peer(rows, query)

    @staticmethod
    def _peer_alias_names(entry: AgentEntry) -> list[str]:
        """Human names plus harness ``config.name`` (memory namespace)."""
        names: list[str] = []
        meta = entry.metadata or {}
        for key in ("display_name", "name"):
            raw = meta.get(key)
            if isinstance(raw, str) and raw.strip():
                names.append(raw.strip())
        cfg_name = entry.config.name if entry.config else ""
        if cfg_name:
            names.append(cfg_name)
        seen: set[str] = set()
        out: list[str] = []
        for name in names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        return out

    @classmethod
    def _match_peer(cls, rows: list[AgentEntry], query: str) -> AgentEntry | None:
        q = query.strip().lstrip("@")
        if not q:
            return None
        ql = q.lower()
        for row in rows:
            if row.agent_id == q or row.agent_id.endswith(q):
                return row
        for row in rows:
            if any(name.lower() == ql for name in cls._peer_alias_names(row)):
                return row
        partial = [row for row in rows if any(ql in name.lower() for name in cls._peer_alias_names(row))]
        return partial[0] if len(partial) == 1 else None

    @classmethod
    def peer_display_name(cls, entry: AgentEntry) -> str:
        aliases = cls._peer_alias_names(entry)
        return aliases[0] if aliases else entry.agent_id[-6:]

    def _resolve_peer_entry(
        self,
        from_agent_id: str,
        to_agent_id: str,
        user_id: str | int,
    ) -> AgentEntry:
        if to_agent_id == from_agent_id:
            raise ValueError("cannot collaborate with self")
        entry = self._registry.get(to_agent_id)
        meta_uid = entry.metadata.get("user_id")
        if meta_uid is not None and str(meta_uid) != str(user_id):
            raise ValueError(f"agent {to_agent_id!r} not owned by user")
        return entry

    # ------------------------------------------------------------------
    # Collaboration
    # ------------------------------------------------------------------

    async def _call_agent(
        self,
        agent_id: str,
        request: ChatRequest | str | dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve *agent_id* from the registry and invoke ``entry.agent.call``."""
        entry = self._registry.get(agent_id)
        req = ChatRequest.coerce(request)
        if self._enrich_request is not None:
            req = await self._enrich_request(agent_id, req)
        elif not req.agent_id:
            req.agent_id = agent_id
        try:
            return await entry.agent.call(req)
        finally:
            if self._after_call is not None:
                await self._after_call()

    async def _invoke_inbox_target(self, msg: InboxMessage) -> dict[str, Any]:
        sk_raw = msg.metadata.get("session_key") if msg.metadata else None
        sk = sk_raw if isinstance(sk_raw, str) and sk_raw.strip() else None
        _req, result = await self._invoke_peer(
            from_agent_id=msg.source_agent_id,
            to_agent_id=msg.target_agent_id,
            message=msg.message,
            user_id=msg.user_id,
            source="inbox",
            source_thread_id=msg.source_thread_id,
            source_session_key=sk,
            job_id=msg.id,
        )
        return result

    async def _invoke_peer(
        self,
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        user_id: str | int,
        source: str,
        source_thread_id: str | None,
        source_session_key: str | None,
        job_id: str | None = None,
    ) -> tuple[ChatRequest, dict[str, Any]]:
        request = await self._build_peer_request(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message=message,
            user_id=user_id,
            source=source,
            source_thread_id=source_thread_id,
            source_session_key=source_session_key,
            job_id=job_id,
        )
        result = await self._call_agent(to_agent_id, request)
        payload = result if isinstance(result, dict) else {}
        if self._after_peer is not None:
            delivered = request.messages if isinstance(request.messages, str) else message
            call = PeerCall(
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                user_id=user_id,
                message=delivered,
                source_thread_id=source_thread_id,
                source_session_key=source_session_key,
                job_id=job_id,
            )
            try:
                await self._after_peer(call, str(request.thread_id or ""), payload)
            except Exception:  # after-call hook failures are non-fatal; pylint: disable=broad-except
                logger.warning(
                    "peer after-call hook failed for %s -> %s",
                    from_agent_id,
                    to_agent_id,
                    exc_info=True,
                )
        return request, payload

    async def _build_peer_request(
        self,
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        user_id: str | int,
        source: str,
        source_thread_id: str | None,
        source_session_key: str | None,
        job_id: str | None = None,
    ) -> ChatRequest:
        thread_id = derive_peer_thread_id(source_thread_id, to_agent_id) if source_thread_id else None
        session_key = source_session_key
        extra: dict[str, Any] = {}
        if self._prepare_peer is not None:
            call = PeerCall(
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
                user_id=user_id,
                message=message,
                source_thread_id=source_thread_id,
                source_session_key=source_session_key,
                job_id=job_id,
            )
            try:
                prepared = await self._prepare_peer(call)
            except Exception:  # peer session prepare failures are non-fatal; pylint: disable=broad-except
                logger.warning(
                    "peer session prepare failed for %s -> %s",
                    from_agent_id,
                    to_agent_id,
                    exc_info=True,
                )
                prepared = None
            if prepared is not None:
                if prepared.thread_id:
                    thread_id = prepared.thread_id
                if prepared.session_key:
                    session_key = prepared.session_key
                if prepared.configurable:
                    extra.update(
                        (key, value)
                        for key, value in prepared.configurable.items()
                        if key not in PEER_IDENTITY_CONFIG_KEYS
                    )
                if prepared.message:
                    message = prepared.message
        return build_one_shot_request(
            user_id=user_id,
            agent_id=to_agent_id,
            text=message,
            source=source,
            thread_id=thread_id,
            session_key=session_key,
            configurable=extra or None,
        )

    async def ask_peer_sync(
        self,
        *,
        from_agent_id: str,
        agent_query: str,
        message: str,
        user_id: str | int,
        source: str = "ask_agent",
    ) -> PeerResult:
        """Sync peer call after resolving *agent_query* — used by ``ask_agent``."""
        entry = self.resolve_peer(user_id, agent_query, exclude_agent_id=from_agent_id)
        if entry is None:
            raise ValueError(f"expert not found: {agent_query}")
        return await self.call_peer(
            from_agent_id=from_agent_id,
            to_agent_id=entry.agent_id,
            message=message,
            user_id=user_id,
            source=source,
        )

    async def call_peer(
        self,
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        user_id: str | int,
        source: str = "ask_agent",
        source_thread_id: str | None = None,
        session_key: str | None = None,
    ) -> PeerResult:
        """Synchronous one-shot call to a peer agent; blocks for the answer."""
        entry = self._resolve_peer_entry(
            from_agent_id,
            to_agent_id,
            user_id,
        )
        request, result = await self._invoke_peer(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message=message,
            user_id=user_id,
            source=source,
            source_thread_id=source_thread_id,
            source_session_key=session_key,
        )
        response = extract_call_response(result) if isinstance(result, dict) else ""
        return PeerResult(
            mode="sync",
            agent_id=to_agent_id,
            name=self.peer_display_name(entry),
            thread_id=request.thread_id,
            response=response,
        )

    def submit_peer(
        self,
        *,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
        user_id: str | int,
        source_thread_id: str | None,
        original_user_prompt: str | None = None,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PeerResult:
        """Enqueue async collaboration; returns inbox id immediately."""
        if self._inbox is None:
            raise RuntimeError("inbox not enabled: construct the manager with a team_processor")
        entry = self._resolve_peer_entry(from_agent_id, to_agent_id, user_id)
        jid = self._inbox.enqueue(
            target_agent_id=to_agent_id,
            source_agent_id=from_agent_id,
            source_thread_id=source_thread_id,
            message=message,
            user_id=user_id,
            original_user_prompt=original_user_prompt,
            job_id=job_id,
            metadata=metadata,
        )
        return PeerResult(
            mode="background",
            agent_id=to_agent_id,
            name=self.peer_display_name(entry),
            job_id=jid,
            status="queued",
            message=(
                "Background task started. Tell the user work is in progress; "
                "they will receive a follow-up reply when it completes."
            ),
        )


__all__ = ["TeamManager"]
