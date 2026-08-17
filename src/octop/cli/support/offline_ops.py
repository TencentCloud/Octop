"""Direct infra/DB helpers for local CLI (no HTTP, no login)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from octop.cli.support.db import (
    open_cli_services,
    resolve_username,
)
from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.providers.model_flags import is_local_runtime_provider
from octop.infra.cron.task_type import normalize_cron_task_type, require_cron_prompt
from octop.infra.cron.trigger import build_trigger
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.users.password import hash_password
from octop.infra.utils.ulid import new_cron_id, new_ulid

logger = logging.getLogger(__name__)


def _user_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "username": row.username,
        "role": row.role,
        "display_name": row.display_name,
        "disabled": bool(row.disabled),
    }


def _provider_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "api_key": row.api_key,
        "models": row.get_models(),
        "note": row.note,
        "enabled": bool(row.enabled),
    }


def _channel_row_to_dict(row: Any) -> dict[str, Any]:
    try:
        config = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    return {
        "id": row.channel_id,
        "channel_id": row.channel_id,
        "name": row.name,
        "kind": row.kind,
        "enabled": bool(row.enabled),
        "config": config,
    }


def _require_username(services: Any, username: str) -> int:
    try:
        return resolve_username(username, services)
    except ValueError as exc:
        raise OctopError(ErrorCode.NOT_FOUND, str(exc)) from exc


# ── Users ────────────────────────────────────────────────────────────────────


def list_users_offline(*, home: Path | None = None) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        return [_user_row_to_dict(r) for r in svc.user_repo.list(include_disabled=True)]


def create_user_offline(
    *,
    username: str,
    password: str,
    role: str,
    display_name: str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    with open_cli_services(home) as svc:
        if svc.user_repo.get_by_username(username) is not None:
            raise OctopError(ErrorCode.USERNAME_TAKEN, f"username {username!r} already exists")
        uid = svc.user_repo.create(
            username=username,
            password_hash=hash_password(password),
            role=role,
            display_name=display_name,
        )
        row = svc.user_repo.get(uid)
        assert row is not None
        return _user_row_to_dict(row)


def set_user_password_offline(username: str, password: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        uid = _require_username(svc, username)
        svc.user_repo.set_password_hash(uid, hash_password(password))


def set_user_role_offline(username: str, role: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        uid = _require_username(svc, username)
        svc.user_repo.set_role(uid, role)


def disable_user_offline(username: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        uid = _require_username(svc, username)
        svc.user_repo.set_disabled(uid, True)


def delete_user_offline(username: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        uid = _require_username(svc, username)
        svc.user_repo.delete(uid)


# ── Cron ─────────────────────────────────────────────────────────────────────


async def _ensure_dashboard_session(
    services: Any, *, agent_id: str, user_id: int, session_key: str
) -> None:
    registry = ThreadRegistry(
        session_repo=services.session_repo,
        thread_repo=services.thread_repo,
    )
    await registry.get_or_create_by_key(
        session_key=session_key,
        agent_id=agent_id,
        user_id=user_id,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
    )


def list_cron_offline(agent_id: str, *, home: Path | None = None) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        rows = svc.cron_repo.list_by_agent(agent_id, include_disabled=True)
        return [r.to_public_dict(include_agent=True) for r in rows]


def create_cron_offline(
    *,
    agent_id: str,
    user_id: int,
    trigger: str,
    prompt: str,
    fresh_thread: bool = False,
    task_type: str = "agent",
    home: Path | None = None,
) -> dict[str, Any]:
    build_trigger(trigger)
    cleaned_prompt = require_cron_prompt(prompt)
    session_key = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id)
    with open_cli_services(home) as svc:
        if svc.agent_repo.get(agent_id) is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        asyncio.run(
            _ensure_dashboard_session(
                svc, agent_id=agent_id, user_id=user_id, session_key=session_key
            )
        )
        cron_id = new_cron_id()
        svc.cron_repo.create(
            cron_id=cron_id,
            agent_id=agent_id,
            user_id=user_id,
            trigger=trigger,
            prompt=cleaned_prompt,
            session_key=session_key,
            fresh_thread=fresh_thread,
            model=None,
            task_type=normalize_cron_task_type(task_type),
        )
        row = svc.cron_repo.get(cron_id)
        assert row is not None
        user_row = svc.user_repo.get(user_id)
        actor = user_row.username if user_row else str(user_id)
        svc.audit_repo.write(
            actor=actor,
            action="cron.create",
            target=cron_id,
            payload=cleaned_prompt[:80],
        )
        return row.to_public_dict(include_agent=True)


def delete_cron_offline(agent_id: str, cron_id: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        row = svc.cron_repo.get(cron_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, "cron job not found")
        svc.cron_repo.delete(cron_id)


def resolve_cron_user_id(agent_id: str, as_user: str | None, *, home: Path | None = None) -> int:
    from octop.cli.support.acting import resolve_cli_acting_user_id

    return resolve_cli_acting_user_id(agent_id, as_user, home=home)


# Backward-compatible alias
resolve_acting_user_id_offline = resolve_cron_user_id


# ── Agents / experts ─────────────────────────────────────────────────────────


def delete_agent_offline(agent_id: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        if svc.agent_repo.get(agent_id) is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        workspace_dir = svc.paths.agent_workspace(agent_id)
        try:
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir)
        except OSError:
            logger.exception("rmtree failed for %s; agent removed from DB anyway", workspace_dir)
        svc.agent_repo.delete(agent_id)


def list_experts_offline() -> list[dict[str, Any]]:
    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    out: list[dict[str, Any]] = []
    for summary in catalog.list_summaries():
        out.append(
            {
                "id": summary.id,
                "label": {"zh": summary.label_zh, "en": summary.label_en},
                "description": {"zh": summary.description_zh, "en": summary.description_en},
            }
        )
    return out


# ── Admin ────────────────────────────────────────────────────────────────────


def admin_overview_offline(*, home: Path | None = None) -> dict[str, Any]:
    with open_cli_services(home) as svc:
        users = [
            {"username": r.username, "role": r.role, "agents": []}
            for r in svc.user_repo.list(include_disabled=True)
        ]
        agents = [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "name": r.name,
                "state": r.last_state or "unknown",
            }
            for r in svc.agent_repo.list_all()
        ]
        return {
            "users": users,
            "agents": agents,
            "totals": {"users": len(users), "agents": len(agents)},
        }


def admin_audit_offline(
    *,
    actor: str | None = None,
    action: str | None = None,
    limit: int = 50,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        rows = svc.audit_repo.query(actor=actor, action=action, limit=limit)
        return [
            {
                "id": r.id,
                "ts": r.ts,
                "actor": r.actor,
                "action": r.action,
                "target": r.target,
                "payload": r.payload,
            }
            for r in rows
        ]


# ── Providers / models ─────────────────────────────────────────────────────────


def list_providers_offline(*, home: Path | None = None) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        return [_provider_row_to_dict(r) for r in svc.provider_repo.list_all()]


def create_provider_offline(
    *,
    name: str,
    kind: str,
    base_url: str | None = None,
    api_key: str | None = None,
    models: list[dict[str, Any]] | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    models_json = json.dumps(models) if models is not None else None
    with open_cli_services(home) as svc:
        if svc.provider_repo.get_by_name(name) is not None:
            raise OctopError(ErrorCode.PROVIDER_NAME_TAKEN, f"provider {name!r} already exists")
        pid = svc.provider_repo.create(
            name=name,
            kind=kind,
            base_url=base_url,
            api_key=api_key,
            models_json=models_json,
        )
        row = svc.provider_repo.get(pid)
        assert row is not None
        return _provider_row_to_dict(row)


def delete_provider_offline(provider_id: int, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        row = svc.provider_repo.get(provider_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
        if is_local_runtime_provider(
            row.name,
            provider_api_key=row.api_key,
            provider_base_url=row.base_url,
        ):
            raise OctopError(
                ErrorCode.PROVIDER_LOCAL_PROTECTED,
                "local runtime providers cannot be deleted",
            )
        refs = svc.provider_repo.find_referencing_agent_ids(svc.agent_repo, row.name)
        if refs:
            raise OctopError(
                ErrorCode.PROVIDER_REFERENCED,
                f"provider {row.name!r} is referenced by {len(refs)} agent(s)",
            )
        svc.provider_repo.delete(provider_id)


def load_provider_presets_offline() -> list[dict[str, Any]]:
    from octop.infra.agents.providers.presets import load_provider_presets

    return load_provider_presets()


def list_resolved_models_offline(*, home: Path | None = None) -> list[dict[str, Any]]:
    from octop.infra.agents.providers.resolved import list_resolved_models

    with open_cli_services(home) as svc:
        return list_resolved_models(svc.provider_repo.list_all())


def get_active_model_offline(*, home: Path | None = None) -> dict[str, str]:
    with open_cli_services(home) as svc:
        name, model = svc.settings_repo.get_active_model()
        return {"provider_name": name, "model": model}


def set_active_model_offline(
    provider_name: str, model: str, *, home: Path | None = None
) -> dict[str, str]:
    with open_cli_services(home) as svc:
        svc.settings_repo.set_active_model(provider_name, model)
        return {"provider_name": provider_name, "model": model}


# ── Channels ─────────────────────────────────────────────────────────────────


def list_channels_offline(agent_id: str, *, home: Path | None = None) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        return [_channel_row_to_dict(r) for r in svc.channel_repo.list_by_agent(agent_id)]


def get_channel_offline(
    agent_id: str, channel_id: str, *, home: Path | None = None
) -> dict[str, Any]:
    with open_cli_services(home) as svc:
        row = svc.channel_repo.get(channel_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, f"channel {channel_id!r} not found")
        return _channel_row_to_dict(row)


def create_channel_offline(
    *,
    agent_id: str,
    user_id: int,
    kind: str,
    name: str,
    config: dict[str, Any],
    home: Path | None = None,
) -> dict[str, Any]:
    channel_id = new_ulid()
    with open_cli_services(home) as svc:
        if svc.agent_repo.get(agent_id) is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        svc.channel_repo.create(
            channel_id=channel_id,
            agent_id=agent_id,
            user_id=user_id,
            kind=kind,
            name=name,
            config_json=json.dumps(config),
        )
        row = svc.channel_repo.get(channel_id)
        assert row is not None
        return _channel_row_to_dict(row)


def patch_channel_offline(
    agent_id: str,
    channel_id: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    with open_cli_services(home) as svc:
        row = svc.channel_repo.get(channel_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, f"channel {channel_id!r} not found")
        svc.channel_repo.update(
            channel_id,
            name=name,
            config_json=json.dumps(config) if config is not None else None,
            enabled=enabled,
        )
        updated = svc.channel_repo.get(channel_id)
        assert updated is not None
        return _channel_row_to_dict(updated)


def delete_channel_offline(agent_id: str, channel_id: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        row = svc.channel_repo.get(channel_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.NOT_FOUND, f"channel {channel_id!r} not found")
        svc.channel_repo.delete(channel_id)


# ── Threads ──────────────────────────────────────────────────────────────────


def create_thread_offline(
    *,
    agent_id: str,
    user_id: int,
    home: Path | None = None,
) -> dict[str, Any]:
    session_key = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id)
    with open_cli_services(home) as svc:
        registry = ThreadRegistry(
            session_repo=svc.session_repo,
            thread_repo=svc.thread_repo,
        )
        tid = asyncio.run(
            registry.get_or_create_by_key(
                session_key=session_key,
                agent_id=agent_id,
                user_id=user_id,
                channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            )
        )
        row = registry.get_thread(tid)
        assert row is not None
        return {
            "thread_id": row.thread_id,
            "title": row.title,
            "session_key": session_key,
            "is_active": True,
        }


def update_thread_offline(
    agent_id: str,
    thread_id: str,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    with open_cli_services(home) as svc:
        row = svc.thread_repo.get(thread_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
        if title is not None:
            svc.thread_repo.update_title(thread_id, title)
        if pinned is not None:
            svc.thread_repo.set_pinned(thread_id, pinned)
        updated = svc.thread_repo.get(thread_id)
        assert updated is not None
        return {
            "thread_id": updated.thread_id,
            "title": updated.title,
            "pinned": updated.pinned,
        }


def delete_thread_offline(agent_id: str, thread_id: str, *, home: Path | None = None) -> None:
    with open_cli_services(home) as svc:
        row = svc.thread_repo.get(thread_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
        svc.thread_repo.delete(thread_id)
