"""GlobalProcessor — harness-gateway MessageProcessor + TeamProcessor."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from harness_agent.slash import SlashSink, parse_slash
from harness_agent.teams.inbox import InboxMessage
from harness_agent.teams.processor import ReplyEvent, default_compose_followup
from harness_gateway.models import (
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
)

from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.providers.reasoning import reasoning_request_parameters
from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    HitlSlashOutcome,
    HitlStreamContext,
)
from octop.infra.gateway.media.attachment_hints import content_blocks_need_vision
from octop.infra.gateway.media.tool_media import (
    attachment_frames_from_tool_result,
    enrich_tool_result_for_dashboard,
    enrich_tool_result_with_backend,
)
from octop.infra.gateway.process.agent_resolve import (
    harness_workspace_for_agent,
    media_backend_for_agent,
)
from octop.infra.gateway.process.harness_request import (
    build_content_from_message,
    build_harness_request,
)
from octop.infra.gateway.process.message_keys import (
    resolve_user_id_for_message,
    sanitize_im_metadata,
    session_key_from_message,
)
from octop.infra.gateway.process.stream_project import (
    StreamProjectionState,
    enrich_tool_stream_chunk,
    project_stream,
)
from octop.infra.gateway.process.usage_record import UsageTracker, record_turn_usage
from octop.infra.gateway.slash.ctx import SlashCtx, build_slash_ctx
from octop.infra.gateway.slash.runner import try_handle_slash
from octop.infra.users.preferences import (
    get_model_reasoning_from_json,
    get_preferred_model_from_json,
)
from octop.infra.utils.locale import resolve_user_locale

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.audit import AuditRepo
    from octop.infra.db.repos.connectors import ConnectorRepo
    from octop.infra.db.repos.sessions import SessionRow
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher
    from octop.infra.gateway.threads import ThreadRegistry

logger = logging.getLogger(__name__)


class _MessageEventSink(SlashSink):
    def __init__(self) -> None:
        self.events: list[MessageEvent] = []

    async def text(self, line: str) -> None:
        self.events.append(
            MessageEvent(type=MessageEventType.MESSAGE, content=[TextContent(text=line)])
        )

    async def complete(self) -> None:
        pass


class GlobalProcessor:
    """Routes InboundMessages by ``tenant_id`` to the correct HarnessAgent."""

    def __init__(
        self,
        *,
        agent_manager: AgentManager,
        thread_registry: ThreadRegistry,
        audit_repo: AuditRepo,
        agent_repo: AgentRepo,
        user_repo: UserRepo,
        connector_repo: ConnectorRepo,
        dispatcher: SlashDispatcher,
        usage_repo: Any | None = None,
        gateway: Any | None = None,
        hitl: HitlChannelCoordinator | None = None,
    ) -> None:
        self._agent_manager = agent_manager
        self._thread_registry = thread_registry
        self._audit_repo = audit_repo
        self._agent_repo = agent_repo
        self._user_repo = user_repo
        self._connector_repo = connector_repo
        self._dispatcher = dispatcher
        self._usage_repo = usage_repo
        self._gateway = gateway
        self._hitl = hitl or HitlChannelCoordinator()

    @property
    def hitl_coordinator(self) -> HitlChannelCoordinator:
        return self._hitl

    # -- TeamProcessor (harness inbox async peer collaboration) ----------------

    def compose_followup(
        self,
        msg: InboxMessage,
        *,
        result_text: str | None,
        error_text: str | None,
    ) -> str:
        prompt = default_compose_followup(msg, result_text=result_text, error_text=error_text)
        child_name = self._peer_display_name(msg.target_agent_id)
        if child_name and child_name != msg.target_agent_id[-6:]:
            return prompt.replace(
                f"agent {msg.target_agent_id}",
                f"agent {child_name}",
                1,
            )
        return prompt

    async def on_reply(self, event: ReplyEvent) -> None:
        session_key = event.metadata.get("session_key")
        if not isinstance(session_key, str) or not session_key.strip():
            logger.warning("team reply %s: missing session_key", event.inbox_id)
            return
        sk = session_key.strip()
        session = self._thread_registry.get_session(sk)
        if session is None:
            logger.warning("team reply %s: session %r not found", event.inbox_id, sk)
            return

        if event.status != "done":
            text = event.error_text or "Background task did not complete."
            await self._deliver_team_text(session, sk, text)
            return

        await self._deliver_team_text(session, sk, event.reply_text or "(empty)")

    async def _deliver_team_text(self, session: SessionRow, session_key: str, text: str) -> None:
        if session.channel_id and self._gateway is not None:
            await self._gateway.push_text(
                session.channel_type,
                session.channel_id,
                session.to_channel_subject(),
                text,
            )
            return
        self._thread_registry.increment_unread(session_key)
        self._thread_registry.touch_last_active(session.thread_id)

    def _peer_display_name(self, agent_id: str) -> str:
        row = self._agent_manager.get_row(agent_id)
        return row.name if row is not None else agent_id[-6:]

    def _slash_ctx(
        self,
        *,
        agent_id: str,
        user_id: int,
        channel_type: str,
        session_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> SlashCtx:
        return build_slash_ctx(
            gateway=self._gateway,
            thread_registry=self._thread_registry,
            agent_repo=self._agent_repo,
            connector_repo=self._connector_repo,
            user_repo=self._user_repo,
            agent_manager=self._agent_manager,
            usage_repo=self._usage_repo,
            agent_id=agent_id,
            user_id=user_id,
            channel_type=channel_type,
            session_key=session_key,
            metadata=metadata,
            paths=self._agent_manager.paths,
        )

    @staticmethod
    def _model_ref_from_meta(
        thread_model: str | None,
        meta: dict[str, Any] | None,
        sticky_model: str | None = None,
    ) -> str | None:
        meta_model = (meta or {}).get("model")
        # Explicit composer choice wins, followed by its persisted conversation
        # value. The legacy /model override remains supported at lower priority.
        model_ref = meta_model or sticky_model or thread_model
        if isinstance(model_ref, str):
            stripped = model_ref.strip()
            return stripped or None
        return None

    def _resolve_harness_model(
        self,
        agent_id: str,
        thread_id: str,
        meta: dict[str, Any] | None,
        *,
        needs_multimodal: bool,
        user_id: int = 0,
    ) -> str | None:
        """Per-turn ``model`` for harness requests.

        - Expert AUTO (no ``default_model`` on row): omit ``model`` → harness routes.
        - Expert default set: pass default (or slash/thread / dashboard override).
        - Stale overrides (deleted / disabled catalog refs) are dropped so routing
          falls through to a usable expert default or harness AUTO.
        - When a model is passed and the turn needs vision, upgrade to a vision ref.
        """
        providers = self._agent_manager.providers
        thread_model = self._agent_manager.get_thread_model(agent_id, thread_id)
        thread_row = self._thread_registry.get_thread(thread_id)
        model_ref = self._model_ref_from_meta(
            thread_model,
            meta,
            thread_row.model_ref if thread_row is not None else None,
        )
        if model_ref and not providers.is_model_ref_usable(model_ref):
            model_ref = None
        if not model_ref:
            row = self._agent_repo.get(agent_id)
            if row is not None:
                model_ref = providers.resolve_explicit_default_model(
                    row,
                    self._agent_manager.get_config(agent_id),
                )
        if not model_ref:
            user_row = self._user_repo.get(user_id)
            preferred = get_preferred_model_from_json(
                user_row.preferences_json if user_row is not None else None
            )
            if preferred and self._agent_manager.providers.is_model_ref_usable(preferred):
                model_ref = preferred
        if not model_ref:
            fallback = self._agent_manager.resolve_fallback_model_ref()
            model_ref = fallback.strip() if isinstance(fallback, str) and fallback.strip() else None
        if not model_ref:
            return None
        return providers.resolve_model_for_multimodal_turn(
            model_ref,
            needs_multimodal=needs_multimodal,
        )

    def _resolve_reasoning_overrides(
        self,
        *,
        user_id: int,
        thread_id: str,
        model_ref: str | None,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not model_ref:
            return {}
        capability = self._agent_manager.providers.get_model_reasoning_capability(model_ref)
        if capability is None:
            return {}
        thread = self._thread_registry.get_thread(thread_id)
        user_row = self._user_repo.get(user_id)
        user_prefs = get_model_reasoning_from_json(
            user_row.preferences_json if user_row is not None else None
        )
        user_pref = user_prefs.get(model_ref)
        raw_mode = (meta or {}).get("reasoning_mode")
        raw_effort = (meta or {}).get("reasoning_effort")
        mode = (
            str(raw_mode)
            if raw_mode in ("auto", "enabled", "disabled")
            else thread.reasoning_mode
            if thread is not None and thread.reasoning_mode
            else user_pref.mode
            if user_pref is not None
            else None
        )
        effort = (
            str(raw_effort).strip().lower()
            if isinstance(raw_effort, str) and raw_effort.strip()
            else thread.reasoning_effort
            if thread is not None and thread.reasoning_effort
            else user_pref.effort
            if user_pref is not None
            else None
        )
        return reasoning_request_parameters(capability, mode=mode, effort=effort)

    # -- IM channel entry (MessageEvent stream) --------------------------------

    async def __call__(self, msg: InboundMessage) -> AsyncIterator[MessageEvent]:
        from octop.infra.metrics import METRICS  # noqa: PLC0415

        METRICS.inc("messages_total")

        agent_id = msg.tenant_id or ""
        if not agent_id:
            yield MessageEvent.error_event("No agent (tenant_id) specified")
            yield MessageEvent.completed()
            return

        agent_row = self._agent_repo.get(agent_id)
        user_id = resolve_user_id_for_message(
            msg,
            agent_owner_id=agent_row.user_id if agent_row is not None else None,
        )
        session_key = session_key_from_message(msg, agent_id=agent_id)
        channel_type = msg.channel_type or "unknown"
        im_meta = sanitize_im_metadata(msg)

        cmd = parse_slash(msg.text)
        locale = resolve_user_locale(
            user_repo=self._user_repo,
            user_id=user_id,
            channel_type=channel_type,
            metadata=msg.metadata,
        )
        if cmd is not None and cmd.name in ("approve", "reject", "pending"):
            usage_tracker = UsageTracker()
            slash_outcome = HitlSlashOutcome()
            async for ev in self._hitl.iter_slash_resolution(
                cmd,
                self._slash_ctx(
                    agent_id=agent_id,
                    user_id=user_id,
                    channel_type=channel_type,
                    session_key=session_key,
                    metadata=msg.metadata,
                ),
                agent_manager=self._agent_manager,
                locale=locale,
                usage_tracker=usage_tracker,
                outcome=slash_outcome,
            ):
                yield ev
            if slash_outcome.completed_turn:
                thread_id = self._thread_registry.get_bound_thread_id(session_key)
                if thread_id is None:
                    thread_id = await self._thread_registry.get_or_create_by_key(
                        session_key=session_key,
                        agent_id=agent_id,
                        user_id=user_id,
                        channel_type=channel_type,
                        channel_channel_id=msg.channel_id or None,
                        channel_metadata=im_meta,
                    )
                if thread_id:
                    self._touch_thread_after_turn(thread_id, msg.text)
                    if usage_tracker.usage:
                        self._record_turn_usage(
                            agent_id=agent_id,
                            user_id=user_id,
                            thread_id=thread_id,
                            usage=usage_tracker.usage,
                        )
            yield MessageEvent.completed()
            return

        if cmd is not None:
            sink = _MessageEventSink()
            handled = await self._dispatcher.handle(
                cmd,
                self._slash_ctx(
                    agent_id=agent_id,
                    user_id=user_id,
                    channel_type=channel_type,
                    session_key=session_key,
                    metadata=msg.metadata,
                ),
                sink,
            )
            for ev in sink.events:
                yield ev
            if handled:
                yield MessageEvent.completed()
                return

        thread_id = await self._thread_registry.get_or_create_by_key(
            session_key=session_key,
            agent_id=agent_id,
            user_id=user_id,
            channel_type=channel_type,
            channel_channel_id=msg.channel_id or None,
            channel_metadata=im_meta,
        )

        media_backend = media_backend_for_agent(self._agent_manager, agent_id)
        content = await build_content_from_message(
            msg,
            media_backend=media_backend,
            locale=locale,
        )
        model_ref = self._resolve_harness_model(
            agent_id,
            thread_id,
            None,
            user_id=user_id,
            needs_multimodal=content_blocks_need_vision(content),
        )
        mcp_servers = await self._resolve_turn_mcp_servers(
            agent_id=agent_id,
            user_id=user_id,
            explicit=None,
            apply_defaults=True,
            raise_on_failure=False,
        )
        message_kwargs: dict[str, Any] | None = None
        if mcp_servers:
            from octop.infra.gateway.process.message_keys import (  # noqa: PLC0415
                COMPOSER_CTX_KEY,
                build_composer_context,
            )

            row = self._agent_repo.get(agent_id)
            default_model = (row.default_model if row is not None else None) or None
            composer = build_composer_context(
                mcp_servers=mcp_servers,
                skills=None,
                target_agent_ids=None,
                model_ref=model_ref,
                default_model=default_model,
            )
            if composer:
                message_kwargs = {COMPOSER_CTX_KEY: composer}
        request = build_harness_request(
            thread_id=thread_id,
            user_id=user_id,
            agent_id=agent_id,
            session_key=session_key,
            source=f"{msg.channel_type}/{msg.channel_id}",
            content=content,
            model=model_ref,
            message_kwargs=message_kwargs,
        )
        if mcp_servers:
            request["mcp_servers"] = mcp_servers

        yield MessageEvent.typing()
        stream_ok = False
        hitl_paused = False
        usage_tracker = UsageTracker()
        projection_state = StreamProjectionState()
        try:
            async for ev in project_stream(
                self._agent_manager,
                agent_id,
                request,
                media_backend=media_backend,
                usage_tracker=usage_tracker,
                locale=locale,
                projection_state=projection_state,
                hitl_coordinator=self._hitl,
                hitl_ctx=HitlStreamContext(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    session_key=session_key,
                    channel_type=channel_type,
                ),
            ):
                yield ev
            stream_ok = True
            hitl_paused = projection_state.hitl_paused
        except Exception as exc:
            await self._record_stream_error(user_id=user_id, agent_id=agent_id, exc=exc)
            yield MessageEvent.error_event(format_stream_error(exc, locale))
        else:
            if stream_ok and not hitl_paused:
                self._touch_thread_after_turn(thread_id, msg.text)
                self._record_turn_usage(
                    agent_id=agent_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    usage=usage_tracker.usage,
                )
        yield MessageEvent.completed()

    # -- Raw harness-chunk stream (Dashboard WS, etc.) -------------------------
    # IM channels (DingTalk, Feishu, …) stream via __call__ → MessageEvent instead.

    async def iter_turn_chunks(self, msg: InboundMessage) -> AsyncIterator[dict[str, Any]]:
        """Run one agent turn and yield harness-native stream chunks.

        For transports that consume the dashboard chunk protocol (``token``,
        ``tool_result``, ``attachment``, ``done``, …) without going through
        harness-gateway :class:`MessageEvent` batching.

        IM channels use :meth:`__call__` → ``project_stream`` → ``MessageEvent``
        (e.g. DingTalk ``BaseChannel.handle_inbound``).
        """
        from octop.infra.metrics import METRICS  # noqa: PLC0415

        METRICS.inc("messages_total")

        agent_id = msg.tenant_id or ""
        if not agent_id:
            yield {"type": "error", "message": "No agent (tenant_id) specified"}
            yield {"type": "done"}
            return

        agent_row = self._agent_repo.get(agent_id)
        user_id = resolve_user_id_for_message(
            msg,
            agent_owner_id=agent_row.user_id if agent_row is not None else None,
        )
        session_key = session_key_from_message(msg, agent_id=agent_id)
        channel_type = msg.channel_type or "unknown"
        im_meta = sanitize_im_metadata(msg)
        meta = msg.metadata or {}

        handled, slash_lines, slash_actions = await try_handle_slash(
            msg.text,
            dispatcher=self._dispatcher,
            ctx=self._slash_ctx(
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                session_key=session_key,
                metadata=meta,
            ),
        )
        if handled:
            for line in slash_lines:
                yield {"type": "token", "content": f"{line}\n"}
            for action in slash_actions:
                yield {"type": "slash_action", **action}
            yield {"type": "done"}
            return

        thread_id = meta.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            thread_id = await self._thread_registry.get_or_create_by_key(
                session_key=session_key,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=channel_type,
                channel_channel_id=msg.channel_id or None,
                channel_metadata=im_meta,
            )

        request = await self._build_dashboard_request(
            msg,
            agent_id=agent_id,
            user_id=user_id,
            session_key=session_key,
            thread_id=thread_id,
            meta=meta,
        )

        stream_ok = False
        harness_workspace = harness_workspace_for_agent(self._agent_manager, agent_id)
        usage_tracker = UsageTracker()
        locale = resolve_user_locale(
            user_repo=self._user_repo,
            user_id=user_id,
            channel_type=channel_type,
            metadata=meta,
        )

        try:
            async for chunk in self._agent_manager.stream(agent_id, request):
                usage_tracker.observe(chunk)
                if chunk.get("type") == "hitl_required":
                    request_payload = chunk.get("request")
                    if isinstance(request_payload, dict):
                        from octop.infra.gateway.hitl.coordinator import HitlStreamContext

                        self._hitl.register_from_request(
                            request_payload,
                            ctx=HitlStreamContext(
                                thread_id=thread_id,
                                agent_id=agent_id,
                                user_id=user_id,
                                session_key=session_key,
                                channel_type=channel_type,
                            ),
                        )
                if chunk.get("type") == "tool_result":
                    if harness_workspace is not None:
                        chunk = await enrich_tool_result_with_backend(
                            chunk,
                            agent_id=agent_id,
                            workspace=harness_workspace,
                        )
                        async for att in attachment_frames_from_tool_result(
                            chunk,
                            agent_id=agent_id,
                            workspace=harness_workspace,
                        ):
                            yield att
                    else:
                        chunk = enrich_tool_result_for_dashboard(
                            chunk,
                            agent_id=agent_id,
                        )
                chunk = enrich_tool_stream_chunk(chunk, locale)
                yield chunk
            stream_ok = True
        except Exception as exc:
            await self._record_stream_error(user_id=user_id, agent_id=agent_id, exc=exc)
            yield {"type": "error", "message": format_stream_error(exc, locale)}
        if stream_ok:
            self._touch_thread_after_turn(thread_id, msg.text)
            self._record_turn_usage(
                agent_id=agent_id,
                user_id=user_id,
                thread_id=thread_id,
                usage=usage_tracker.usage,
            )
        yield {"type": "done"}

    async def _build_dashboard_request(
        self,
        msg: InboundMessage,
        *,
        agent_id: str,
        user_id: int,
        session_key: str,
        thread_id: str,
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        from octop.infra.gateway.process.message_keys import (  # noqa: PLC0415
            COMPOSER_CTX_KEY,
            INBOUND_ATTACHMENTS_KEY,
        )

        media_backend = media_backend_for_agent(self._agent_manager, agent_id)
        source = f"{msg.channel_type}/{msg.channel_id}"
        locale = resolve_user_locale(
            user_repo=self._user_repo,
            user_id=user_id,
            channel_type=msg.channel_type or "unknown",
            metadata=meta,
        )
        content = await build_content_from_message(
            msg,
            media_backend=media_backend,
            locale=locale,
        )
        model_ref = self._resolve_harness_model(
            agent_id,
            thread_id,
            meta,
            user_id=user_id,
            needs_multimodal=content_blocks_need_vision(content),
        )
        reasoning_overrides = self._resolve_reasoning_overrides(
            user_id=user_id,
            thread_id=thread_id,
            model_ref=model_ref,
            meta=meta,
        )

        message_kwargs: dict[str, Any] = {}
        composer = meta.get(COMPOSER_CTX_KEY)
        if isinstance(composer, dict) and composer:
            message_kwargs[COMPOSER_CTX_KEY] = composer
        attachments = meta.get(INBOUND_ATTACHMENTS_KEY)
        if isinstance(attachments, list) and attachments:
            message_kwargs[INBOUND_ATTACHMENTS_KEY] = attachments

        explicit_mcp = meta.get("mcp_servers")
        # Dashboard always sends mcp_servers (possibly []); trust that list so
        # users can opt out of default_open for a turn. Missing key → IM-style defaults.
        if isinstance(explicit_mcp, list):
            apply_defaults = False
        else:
            explicit_mcp = None
            apply_defaults = True
        mcp_servers = await self._resolve_turn_mcp_servers(
            agent_id=agent_id,
            user_id=user_id,
            explicit=explicit_mcp,
            apply_defaults=apply_defaults,
        )
        if mcp_servers:
            # Keep history chips aligned with the servers actually injected.
            if isinstance(composer, dict) and composer:
                stamped = dict(composer)
                stamped["connectors"] = list(mcp_servers)
                message_kwargs[COMPOSER_CTX_KEY] = stamped
            else:
                from octop.infra.gateway.process.message_keys import (  # noqa: PLC0415
                    build_composer_context,
                )

                row = self._agent_repo.get(agent_id)
                default_model = (row.default_model if row is not None else None) or None
                built = build_composer_context(
                    mcp_servers=mcp_servers,
                    skills=meta.get("skills") if isinstance(meta.get("skills"), list) else None,
                    target_agent_ids=None,
                    model_ref=model_ref,
                    default_model=default_model,
                )
                if built:
                    message_kwargs[COMPOSER_CTX_KEY] = built

        request = build_harness_request(
            thread_id=thread_id,
            user_id=user_id,
            agent_id=agent_id,
            session_key=session_key,
            source=source,
            content=content,
            model=model_ref,
            message_kwargs=message_kwargs or None,
            reasoning_overrides=reasoning_overrides,
        )

        if mcp_servers:
            request["mcp_servers"] = mcp_servers
        if "skills" in meta:
            request["skills"] = meta["skills"]
        target_raw = meta.get("target_agent_ids")
        if isinstance(target_raw, list) and target_raw:
            is_admin = bool(meta.get("user_is_admin"))
            filtered: list[str] = []
            for raw_id in target_raw:
                aid = str(raw_id).strip()
                if not aid or aid == agent_id:
                    continue
                row = self._agent_repo.get(aid)
                if row is None:
                    continue
                if not is_admin and row.user_id is not None and row.user_id != user_id:
                    continue
                filtered.append(aid)
            if filtered:
                configurable = dict(request.get("configurable") or {})
                configurable["target_agent_ids"] = filtered
                request["configurable"] = configurable
        return request

    async def _resolve_turn_mcp_servers(
        self,
        *,
        agent_id: str,
        user_id: int,
        explicit: list[str] | None,
        apply_defaults: bool | None = None,
        raise_on_failure: bool = True,
    ) -> list[str] | None:
        """Merge turn picks with default_open and ensure tools are loaded.

        Dashboard / HTTP paths should keep ``raise_on_failure=True`` so the
        client sees a clear MCP load error. IM ingress uses ``False`` so a
        flaky connector does not abort the whole message turn.
        """
        from octop.infra.errors import ErrorCode, OctopError  # noqa: PLC0415

        merged = self._agent_manager.merge_turn_mcp_servers(
            user_id, explicit, apply_defaults=apply_defaults
        )
        if not merged:
            return None
        failed = await self._agent_manager.prepare_chat_mcp(
            agent_id,
            merged,
            connector_user_id=user_id,
        )
        if failed:
            detail = f"mcp load failed: {', '.join(failed)}"
            if raise_on_failure:
                raise OctopError(ErrorCode.CONNECTOR_MCP_LOAD_FAILED, detail)
            logger.warning(
                "skipping turn MCP for agent=%s user=%s (%s)",
                agent_id,
                user_id,
                detail,
            )
            return None
        return merged

    async def _record_stream_error(self, *, user_id: int, agent_id: str, exc: Exception) -> None:
        from octop.infra.metrics import METRICS as _M  # noqa: PLC0415

        _M.inc("stream_errors_total")
        logger.exception("agent.stream failed for agent %s", agent_id)
        user_row = self._user_repo.get(user_id)
        actor = user_row.username if user_row else str(user_id)
        self._audit_repo.write(
            actor=actor,
            action="agent.stream.error",
            target=agent_id,
            payload=str(exc),
        )

    def _touch_thread_after_turn(self, thread_id: str, title_source: str | None) -> None:
        self._thread_registry.touch_last_active(thread_id)
        if title_source:
            self._thread_registry.set_title_if_null(thread_id, title_source)

    def _record_turn_usage(
        self,
        *,
        agent_id: str,
        user_id: int,
        thread_id: str,
        usage: dict[str, Any] | None,
    ) -> None:
        if self._usage_repo is None or not usage:
            return
        record_turn_usage(
            self._usage_repo,
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            usage=usage,
        )
