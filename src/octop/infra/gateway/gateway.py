"""Gateway — global AI interaction entry point."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from harness_gateway.channel import ChannelCredentialsError
from harness_gateway.channels import ChannelKind
from harness_gateway.manager import ChannelManager
from harness_gateway.models import ChannelSubject

from octop.i18n import channel_probe_incomplete, channel_runtime_reason, tr
from octop.infra.cron.task_type import CronTaskType, normalize_cron_task_type
from octop.infra.db.repos.channels import ChannelRow
from octop.infra.db.repos.sessions import SessionRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.cli import CLI_CHANNEL_ID, CliChannel, CliHub
from octop.infra.gateway.process import build_harness_request, media_backend_for_agent
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher, build_default_dispatcher
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.gateway.ws import WS_CHANNEL_ID, WebSocketChannel, WebSocketHub
from octop.infra.utils.locale import DEFAULT_LOCALE, Locale

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.services import RepoBundle

logger = logging.getLogger(__name__)

# Re-export for api/cli importers
__all__ = [
    "ChannelCreateSpec",
    "ChannelKind",
    "ChannelRuntimeStatus",
    "Gateway",
    "SlashRuntimeMeta",
]


@dataclass(frozen=True)
class SlashRuntimeMeta:
    version: str
    started_at: int


@dataclass(frozen=True)
class ChannelRuntimeStatus:
    """Live connection state for a channel.

    ``reason`` is a locale-neutral code (``disabled`` / ``unregistered`` /
    ``error``) localized at serialization time; ``detail`` carries free-form
    diagnostics (e.g. an exception message) shown alongside the reason.
    """

    connected: bool
    reason: str | None = None
    detail: str | None = None
    updated_at: int = 0


@dataclass
class ChannelCreateSpec:
    channel_id: str
    agent_id: str
    user_id: int
    kind: ChannelKind | str
    name: str
    config: dict[str, Any] = field(default_factory=dict)


async def _probe_processor(_msg: Any) -> Any:
    """Stub processor for ephemeral channel probe instances."""
    if False:  # pragma: no cover - makes this an async generator
        yield None


class Gateway:
    """Global AI interaction entry point.

    Owns the harness-gateway ChannelManager. Routes IM messages
    by ``InboundMessage.tenant_id`` (== agent ULID) via GlobalProcessor.
    """

    def __init__(
        self,
        *,
        agent_manager: AgentManager,
        repos: RepoBundle,
    ) -> None:
        self._agent_manager = agent_manager
        self._repos = repos
        self._thread_registry = ThreadRegistry(
            session_repo=repos.session_repo,
            thread_repo=repos.thread_repo,
        )
        self._channel_manager: ChannelManager | None = None
        self._processor: GlobalProcessor | None = None
        self._dispatcher = build_default_dispatcher()
        self._slash_meta: SlashRuntimeMeta | None = None
        self._ws_hub = WebSocketHub()
        self._cli_hub = CliHub()
        self._ws_channel: WebSocketChannel | None = None
        self._cli_channel: CliChannel | None = None
        self._runtime_status: dict[str, ChannelRuntimeStatus] = {}

    def replace_repos(self, repos: RepoBundle) -> None:
        """Point channel/thread persistence at a rebound control-plane pool."""
        self._repos = repos
        self._thread_registry.replace_repos(
            session_repo=repos.session_repo,
            thread_repo=repos.thread_repo,
        )

    @property
    def ws_hub(self) -> WebSocketHub:
        return self._ws_hub

    @property
    def cli_hub(self) -> CliHub:
        return self._cli_hub

    @property
    def cli_channel_id(self) -> str:
        return CLI_CHANNEL_ID

    @property
    def channel_manager(self) -> ChannelManager | None:
        return self._channel_manager

    @property
    def dashboard_channel_id(self) -> str:
        return WS_CHANNEL_ID

    @property
    def slash_dispatcher(self) -> SlashDispatcher:
        return self._dispatcher

    @property
    def processor(self) -> GlobalProcessor:
        if self._processor is None:
            raise RuntimeError("gateway not booted")
        return self._processor

    @property
    def slash_meta(self) -> SlashRuntimeMeta | None:
        return self._slash_meta

    def set_slash_meta(self, *, version: str, started_at: int) -> None:
        self._slash_meta = SlashRuntimeMeta(version=version, started_at=started_at)

    @property
    def thread_registry(self) -> ThreadRegistry:
        return self._thread_registry

    def get_runtime_status(self, channel_id: str) -> ChannelRuntimeStatus | None:
        return self._runtime_status.get(channel_id)

    def runtime_status_to_dict(
        self, channel_id: str, *, locale: Locale = DEFAULT_LOCALE
    ) -> dict[str, Any] | None:
        status = self.get_runtime_status(channel_id)
        if status is None:
            return None
        error: str | None = None
        if status.reason is not None:
            error = channel_runtime_reason(status.reason, locale)
            if status.detail:
                error = f"{error}: {status.detail}"
        return {
            "connected": status.connected,
            "error": error,
            "updated_at": status.updated_at,
        }

    async def boot(self) -> None:
        self._processor = GlobalProcessor(
            agent_manager=self._agent_manager,
            thread_registry=self._thread_registry,
            audit_repo=self._repos.audit_repo,
            agent_repo=self._repos.agent_repo,
            user_repo=self._repos.user_repo,
            connector_repo=self._repos.connector_repo,
            dispatcher=self._dispatcher,
            usage_repo=self._repos.usage_repo,
            gateway=self,
        )

        self._channel_manager = ChannelManager(channels={})
        await self._channel_manager.start()

        self._ws_channel = WebSocketChannel(
            self._processor,
            hub=self._ws_hub,
            channel_id=WS_CHANNEL_ID,
        )
        await self._channel_manager.add_channel(self._ws_channel)

        self._cli_channel = CliChannel(
            self._processor,
            hub=self._cli_hub,
            channel_id=CLI_CHANNEL_ID,
        )
        await self._channel_manager.add_channel(self._cli_channel)

        rows = self._repos.channel_repo.list_all(include_disabled=False)
        if rows:
            await asyncio.gather(*(self._safe_register_channel(row) for row in rows))

        logger.info("Gateway booted")

    async def refresh_media_backends(self) -> None:
        """Re-set media backends on all registered channels.

        Called after agents finish booting (gateway boots before agents) to
        resolve the startup ordering gap.
        """
        if not self._channel_manager:
            return
        rows = self._repos.channel_repo.list_all(include_disabled=False)
        for row in rows:
            channel = self._channel_manager.get_channel(row.channel_id)
            if channel is None:
                continue
            backend = media_backend_for_agent(self._agent_manager, row.agent_id)
            if backend is not None:
                channel.set_media_backend(backend)

    async def shutdown(self) -> None:
        if self._channel_manager:
            await self._channel_manager.stop()
        self._channel_manager = None
        self._processor = None
        self._ws_channel = None
        self._cli_channel = None
        self._runtime_status.clear()

    def list_channels(self, agent_id: str) -> list[ChannelRow]:
        return self._repos.channel_repo.list_by_agent(agent_id)

    def get_channel(self, channel_id: str) -> ChannelRow | None:
        return self._repos.channel_repo.get(channel_id)

    async def create_channel(self, spec: ChannelCreateSpec) -> ChannelRow:
        config_json = json.dumps(spec.config)
        existing = self._repos.channel_repo.get_by_agent_and_name(spec.agent_id, spec.name)
        if existing is not None:
            if existing.kind != str(spec.kind):
                raise OctopError(
                    ErrorCode.CHANNEL_NAME_TAKEN,
                    f"channel name {spec.name!r} already in use by kind {existing.kind!r}",
                )
            row = await self.update_channel(
                existing.channel_id,
                kind=str(spec.kind),
                name=spec.name,
                config_json=config_json,
                enabled=1,
            )
            assert row is not None
            return row

        self._repos.channel_repo.create(
            channel_id=spec.channel_id,
            agent_id=spec.agent_id,
            user_id=spec.user_id,
            kind=str(spec.kind),
            name=spec.name,
            config_json=config_json,
        )
        row = self._repos.channel_repo.get(spec.channel_id)
        assert row is not None
        if row.enabled:
            await self._safe_register_channel(row)
        else:
            self._set_runtime_status(row.channel_id, connected=False, reason="disabled")
        return row

    async def update_channel(
        self,
        channel_id: str,
        *,
        kind: str | None = None,
        name: str | None = None,
        config_json: str | None = None,
        enabled: int | None = None,
    ) -> ChannelRow | None:
        self._repos.channel_repo.update(
            channel_id,
            kind=kind,
            name=name,
            config_json=config_json,
            enabled=bool(enabled) if enabled is not None else None,
        )
        row = self._repos.channel_repo.get(channel_id)
        await self._unregister(channel_id)
        if row and row.enabled:
            await self._safe_register_channel(row)
        elif row is not None:
            self._set_runtime_status(channel_id, connected=False, reason="disabled")
        return row

    async def delete_channel(self, channel_id: str) -> None:
        self._repos.channel_repo.delete(channel_id)
        await self._unregister(channel_id)
        self._runtime_status.pop(channel_id, None)

    def _require_session(self, agent_id: str, session_key: str) -> SessionRow:
        session = self._thread_registry.get_session(session_key)
        if session is None:
            raise ValueError(f"session {session_key!r} not found")
        if session.agent_id != agent_id:
            raise ValueError(f"session {session_key!r} does not belong to agent {agent_id!r}")
        return session

    def _bump_dashboard_session(self, session: SessionRow, session_key: str, text: str) -> None:
        self._thread_registry.touch_last_active(session.thread_id)
        if text:
            self._thread_registry.set_title_if_null(session.thread_id, text[:40])
        self._thread_registry.increment_unread(session_key)

    async def push_text_from_session(
        self,
        agent_id: str,
        session_key: str,
        text: str,
        *,
        task_type: CronTaskType | str = "agent",
        model: str | None = None,
    ) -> None:
        """Cron delivery: run agent if needed, then push text (IM channel or dashboard WS)."""
        session = self._require_session(agent_id, session_key)
        virtual_stream = session.channel_type in (
            ThreadRegistry.CHANNEL_DASHBOARD,
            ThreadRegistry.CHANNEL_CLI,
        )

        if normalize_cron_task_type(str(task_type)) == "text":
            outbound = text
        else:
            request = build_harness_request(
                thread_id=session.thread_id,
                user_id=session.user_id,
                agent_id=agent_id,
                session_key=session_key,
                source=session.channel_type,
                text=text,
                model=model,
            )
            parts: list[str] = []
            async for chunk in self._agent_manager.stream(agent_id, request):
                if chunk.get("type") in ("token", "delta"):
                    parts.append(str(chunk.get("content") or chunk.get("text") or ""))
            outbound = "".join(parts).strip() or "(empty)"

        if virtual_stream:
            self._bump_dashboard_session(session, session_key, text)
            channel_id = (
                WS_CHANNEL_ID
                if session.channel_type == ThreadRegistry.CHANNEL_DASHBOARD
                else CLI_CHANNEL_ID
            )
            await self.push_text(
                session.channel_type,
                channel_id,
                self._resolve_push_subject(session),
                outbound,
            )
            return

        if not session.channel_id:
            raise ValueError(
                f"session is IM ({session.channel_type!r}) but has no channel_id bound"
            )
        await self.push_text(
            session.channel_type,
            session.channel_id,
            self._resolve_push_subject(session),
            outbound,
        )

    def _resolve_push_subject(self, session: SessionRow) -> ChannelSubject:
        """Build ChannelSubject from session; IM routing enrichment is in harness-gateway."""
        return session.to_channel_subject()

    def _require_channel_manager(self) -> ChannelManager:
        if self._channel_manager is None:
            raise RuntimeError("gateway not booted")
        return self._channel_manager

    async def push_text(
        self,
        channel_type: str,
        channel_id: str,
        subject: ChannelSubject,
        text: str,
    ) -> None:
        """Proactively push text to an IM user via ChannelManager."""
        await self._require_channel_manager().push_text(channel_id, subject, text)

    async def probe_channel(
        self, channel_id: str, *, locale: Locale = DEFAULT_LOCALE
    ) -> dict[str, Any]:
        """Start/stop an ephemeral channel instance to verify credentials."""
        row = self.get_channel(channel_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
        return await self._probe_row(row, locale=locale)

    async def probe_config(
        self,
        *,
        agent_id: str,
        kind: str,
        config: dict[str, Any],
        locale: Locale = DEFAULT_LOCALE,
    ) -> dict[str, Any]:
        """Probe credentials without persisting a channel row."""
        ts = int(time.time())
        row = ChannelRow(
            id=0,
            channel_id="__probe__",
            agent_id=agent_id,
            user_id=0,
            kind=kind,
            name="probe",
            config_json=json.dumps(config),
            enabled=1,
            created_at=ts,
            updated_at=ts,
        )
        return await self._probe_row(row, locale=locale)

    async def _probe_row(
        self, row: ChannelRow, *, locale: Locale = DEFAULT_LOCALE
    ) -> dict[str, Any]:
        try:
            raw_cfg = json.loads(row.config_json or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": tr("errors.CHANNEL_INVALID_CREDENTIALS", locale)}
        if not isinstance(raw_cfg, dict):
            return {"ok": False, "error": tr("errors.CHANNEL_INVALID_CREDENTIALS", locale)}

        manager = self._channel_manager
        if manager is None:
            raise RuntimeError("gateway not booted")

        try:
            await manager.probe_channel(
                row.kind,
                raw_cfg,
                tenant_id=row.agent_id,
                channel_id=row.channel_id,
                processor=_probe_processor,
            )
            return {"ok": True}
        except ChannelCredentialsError as exc:
            return {"ok": False, "error": channel_probe_incomplete(exc.missing, locale)}
        except OctopError as exc:
            return {"ok": False, "error": exc.localized_message(locale)}
        except Exception as exc:
            logger.exception("Channel probe failed for %s", row.channel_id)
            return {"ok": False, "error": self._format_probe_error(exc, locale)}

    @staticmethod
    def _format_probe_error(exc: Exception, locale: Locale) -> str:
        msg = str(exc)
        lower = msg.lower()
        if "invalid appid or secret" in lower or "100016" in msg:
            return tr("channel.probe.invalid_credentials", locale)
        if "feishu token refresh failed" in lower:
            return tr(
                "channel.probe.feishu_token_failed", locale, detail=msg.split(":", 1)[-1].strip()
            )
        return msg

    def _set_runtime_status(
        self,
        channel_id: str,
        *,
        connected: bool,
        reason: str | None = None,
        detail: str | None = None,
    ) -> None:
        self._runtime_status[channel_id] = ChannelRuntimeStatus(
            connected=connected,
            reason=reason,
            detail=detail,
            updated_at=int(time.time()),
        )

    async def _safe_register_channel(self, row: ChannelRow) -> None:
        try:
            await self._register_channel(row)
        except Exception as exc:
            logger.exception("Failed to register channel %s (%s)", row.channel_id, row.kind)
            self._set_runtime_status(
                row.channel_id, connected=False, reason="error", detail=str(exc)
            )

    async def _register_channel(self, row: ChannelRow) -> None:
        if not self._channel_manager or not self._processor:
            return
        config = self._config_from_row(row)
        manager = self._require_channel_manager()
        await manager.add_channel(
            row.kind,
            config,
            tenant_id=row.agent_id,
            channel_id=row.channel_id,
            processor=self._processor,
        )
        registered = manager.get_channel(row.channel_id)
        if registered is not None:
            backend = media_backend_for_agent(self._agent_manager, row.agent_id)
            if backend is not None:
                registered.set_media_backend(backend)
        self._set_runtime_status(row.channel_id, connected=True)

    def _config_from_row(self, row: ChannelRow) -> dict[str, Any]:
        """Parse the stored JSON config; alias/normalize happens in ``Config.from_dict``."""
        try:
            raw = json.loads(row.config_json or "{}")
        except json.JSONDecodeError as exc:
            raise OctopError(
                ErrorCode.CHANNEL_INVALID_CREDENTIALS,
                f"channel {row.channel_id} config is not valid JSON",
            ) from exc
        if not isinstance(raw, dict):
            raise OctopError(
                ErrorCode.CHANNEL_INVALID_CREDENTIALS,
                f"channel {row.channel_id} config must be a JSON object",
            )
        return raw

    async def _unregister(self, channel_id: str) -> None:
        if not self._channel_manager:
            return
        try:
            await self._channel_manager.remove_channel(channel_id)
        except Exception:
            logger.exception("Failed to unregister channel %s", channel_id)
        self._set_runtime_status(channel_id, connected=False, reason="unregistered")
