"""Offline DB access for CLI commands that only need local SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.config import load_config
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.env_file import apply_env_file, env_file_path
from octop.infra.utils.paths import PathLayout


@contextmanager
def open_cli_services(home: Path | None = None) -> Iterator[SharedServices]:
    """Open DB + repos for offline CLI reads (caller must not hold while server writes)."""
    paths = PathLayout(home) if home is not None else PathLayout.from_env()
    apply_env_file(env_file_path(paths.root))
    config = load_config(paths.config)
    db = open_database(config, paths)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=config)
    try:
        yield services
    finally:
        db.close()


def resolve_username(username: str, services: SharedServices) -> int:
    row = services.user_repo.get_by_username(username)
    if row is None:
        raise ValueError(f"user not found: {username}")
    return int(row.id)


def resolve_cli_user_id(
    as_user: str | None,
    *,
    services: SharedServices,
) -> int | None:
    """Map ``--user`` or CLI ``default_user`` to numeric user id (offline)."""
    from octop.cli.support.ctx import resolve_user
    from octop.cli.support.state import default_state_path, load

    name = resolve_user(as_user)
    if name:
        return resolve_username(name, services)
    pinned = load(default_state_path()).default_user
    if pinned:
        return resolve_username(pinned, services)
    return None


def resolve_cli_locale() -> str:
    """Best-effort locale for terminal rendering (zh/en)."""
    try:
        with open_cli_services() as svc:
            uid = resolve_cli_user_id(None, services=svc)
            if uid is not None:
                row = svc.user_repo.get(uid)
                if row is not None and row.locale in ("zh", "en", "ko"):
                    return "en" if row.locale == "ko" else row.locale
    except Exception:
        pass
    return "zh"


def agent_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "agent_id": row.agent_id,
        "id": row.agent_id,
        "name": row.name,
        "template_name": row.template_name,
        "default_model": row.default_model,
        "state": row.last_state or "",
        "user_id": row.user_id,
    }


def list_agents_offline(
    *, as_user: str | None = None, home: Path | None = None
) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        uid = resolve_cli_user_id(as_user, services=svc)
        rows = svc.agent_repo.list_by_user(uid) if uid is not None else svc.agent_repo.list_all()
        return [agent_row_to_dict(r) for r in rows]


@dataclass(frozen=True)
class OfflineThreadRow:
    thread_id: str
    title: str | None
    channel_type: str
    session_key: str
    last_active: int
    created_at: int
    is_active: bool
    pinned: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "channel_type": self.channel_type,
            "session_key": self.session_key,
            "last_active": self.last_active,
            "created_at": self.created_at,
            "is_active": self.is_active,
            "has_messages": None,
            "pinned": self.pinned,
        }


def list_threads_offline(
    *,
    agent_id: str,
    as_user: str | None = None,
    limit: int = 50,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    with open_cli_services(home) as svc:
        uid = resolve_cli_user_id(as_user, services=svc)
        bound: str | None = None
        if uid is not None:
            sk = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=uid)
            sess = svc.session_repo.get(sk)
            if sess is not None:
                bound = sess.thread_id
        rows = svc.thread_repo.list_by_agent(agent_id=agent_id, limit=limit)
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                OfflineThreadRow(
                    thread_id=r.thread_id,
                    title=r.title,
                    channel_type=r.channel_type,
                    session_key=r.session_key,
                    last_active=r.last_active,
                    created_at=r.created_at,
                    is_active=r.thread_id == bound if bound else False,
                    pinned=r.pinned,
                ).to_dict()
            )
        return out
