"""SlashCtx and helpers for gateway slash handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from octop.infra.utils.locale import Locale, normalize_locale, resolve_locale

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.cron.manager import CronManager
    from octop.infra.db.repos.agents import AgentRepo, AgentRow
    from octop.infra.db.repos.connectors import ConnectorRepo
    from octop.infra.db.repos.usage import UsageRepo
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.db.services import RepoBundle
    from octop.infra.gateway.gateway import Gateway
    from octop.infra.gateway.threads import ThreadRegistry
    from octop.infra.utils.paths import PathLayout


@dataclass
class SlashCtx:
    agent_id: str
    user_id: int
    channel_type: str
    session_key: str
    thread_registry: ThreadRegistry
    agent_repo: AgentRepo | None = None
    connector_repo: ConnectorRepo | None = None
    usage_repo: UsageRepo | None = None
    user_repo: UserRepo | None = None
    agent_manager: AgentManager | None = None
    cron_manager: CronManager | None = None
    paths: PathLayout | None = None
    gateway_channels: list[dict[str, str]] = field(default_factory=list)
    octop_version: str | None = None
    server_started_at: int | None = None
    locale: str = "zh"
    """Dashboard composer / turn ``metadata.model`` (``provider/model``), if any."""
    model_ref: str | None = None


def lang_of(ctx: SlashCtx) -> Locale:
    return normalize_locale(ctx.locale)


def subject_id(ctx: SlashCtx) -> str:
    parts = ctx.session_key.split(":", 3)
    return parts[2] if len(parts) >= 3 else str(ctx.user_id)


def chat_type(ctx: SlashCtx) -> str:
    parts = ctx.session_key.split(":", 3)
    return parts[3] if len(parts) >= 4 else "dm"


def find_thread_by_short(
    registry: ThreadRegistry, agent_id: str, user_id: int, short: str
) -> Any | None:
    rows = registry.list_threads(agent_id=agent_id, user_id=user_id, limit=200)
    matches = [r for r in rows if r.thread_id.endswith(short)]
    return matches[0] if matches else None


def resolve_user_agent(ctx: SlashCtx, query: str) -> AgentRow | None:
    if ctx.agent_manager is None:
        return None
    return ctx.agent_manager.resolve_user_agent(ctx.user_id, query)


async def ensure_thread_id(ctx: SlashCtx) -> str:
    tid = ctx.thread_registry.get_bound_thread_id(ctx.session_key)
    if tid is not None:
        return tid
    return await ctx.thread_registry.get_or_create_by_key(
        session_key=ctx.session_key,
        agent_id=ctx.agent_id,
        user_id=ctx.user_id,
        channel_type=ctx.channel_type,
    )


def build_slash_ctx(
    *,
    gateway: Gateway | None = None,
    thread_registry: ThreadRegistry | None = None,
    agent_repo: AgentRepo | None = None,
    connector_repo: ConnectorRepo | None = None,
    user_repo: Any | None = None,
    agent_manager: AgentManager | None = None,
    usage_repo: Any | None = None,
    cron_manager: CronManager | None = None,
    paths: Any | None = None,
    agent_id: str,
    user_id: int,
    channel_type: str,
    session_key: str,
    metadata: dict[str, Any] | None = None,
    repos: RepoBundle | None = None,
    octop_version: str | None = None,
    server_started_at: int | None = None,
    user_locale: str | None = None,
    channel_metadata: dict[str, object] | None = None,
) -> SlashCtx:
    """Build SlashCtx for GlobalProcessor or other gateway entry points."""
    meta = getattr(gateway, "slash_meta", None) if gateway is not None else None
    gw_channels: list[dict[str, str]] = []
    if gateway is not None:
        gw_channels = [
            {"id": c.channel_id, "kind": c.kind, "name": c.name}
            for c in gateway.list_channels(agent_id)
        ]
        thread_registry = thread_registry or gateway.thread_registry

    if repos is not None:
        agent_repo = agent_repo or repos.agent_repo
        connector_repo = connector_repo or repos.connector_repo
        usage_repo = usage_repo or repos.usage_repo

    user_loc = user_locale
    if user_loc is None and user_repo is not None and user_id > 0:
        user_row = user_repo.get(user_id)
        user_loc = user_row.locale if user_row is not None else None

    from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY  # noqa: PLC0415

    resolved_meta = channel_metadata if channel_metadata is not None else metadata
    model_ref: str | None = None
    if resolved_meta:
        raw_model = resolved_meta.get("model")
        if not (isinstance(raw_model, str) and raw_model.strip()):
            composer = resolved_meta.get(COMPOSER_CTX_KEY)
            if isinstance(composer, dict):
                raw_model = composer.get("model")
        if isinstance(raw_model, str) and raw_model.strip():
            model_ref = raw_model.strip()
    return SlashCtx(
        agent_id=agent_id,
        user_id=user_id,
        channel_type=channel_type,
        session_key=session_key,
        locale=resolve_locale(
            user_locale=user_loc,
            channel_type=channel_type,
            metadata=resolved_meta,
        ),
        thread_registry=thread_registry,  # type: ignore[arg-type]
        agent_repo=agent_repo,
        connector_repo=connector_repo,
        usage_repo=usage_repo,
        user_repo=user_repo,
        agent_manager=agent_manager,
        cron_manager=cron_manager,
        paths=paths,
        gateway_channels=gw_channels,
        octop_version=octop_version or (meta.version if meta else None),
        server_started_at=server_started_at or (meta.started_at if meta else None),
        model_ref=model_ref,
    )
