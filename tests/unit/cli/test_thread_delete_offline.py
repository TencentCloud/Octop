"""End-to-end (SQLite) tests for the offline `octop chats` thread operations."""

from __future__ import annotations

import asyncio
from pathlib import Path

from octop.cli.support.db import open_cli_services
from octop.cli.support.offline_ops import delete_thread_offline
from octop.infra.gateway.threads import ThreadRegistry


def _seed_dashboard_thread(home: Path) -> tuple[int, str, str]:
    """Create user + agent + a bound dashboard session.

    Returns ``(user_id, session_key, thread_id)``.
    """
    with open_cli_services(home) as svc:
        user_id = svc.user_repo.create(username="u", password_hash="h", role="user")
        svc.agent_repo.create(agent_id="a1", user_id=user_id, name="Agent 1")
        registry = ThreadRegistry(session_repo=svc.session_repo, thread_repo=svc.thread_repo)
        session_key = ThreadRegistry.dashboard_key(agent_id="a1", user_id=user_id)
        thread_id = asyncio.run(
            registry.get_or_create_by_key(
                session_key=session_key,
                agent_id="a1",
                user_id=user_id,
                channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            )
        )
    return user_id, session_key, thread_id


def test_delete_thread_offline_unbinds_session(tmp_path: Path) -> None:
    """`octop chats delete` must clear the session bound to the removed thread (#833).

    Otherwise the session survives, keeps resolving to a dead thread id, and
    every later turn silently stops persisting — the model still replies.
    """
    _user_id, session_key, thread_id = _seed_dashboard_thread(tmp_path)
    with open_cli_services(tmp_path) as svc:
        assert svc.session_repo.get(session_key) is not None

    delete_thread_offline("a1", thread_id, home=tmp_path)

    with open_cli_services(tmp_path) as svc:
        assert svc.thread_repo.get(thread_id) is None
        assert svc.session_repo.get(session_key) is None


def test_create_thread_offline_recovers_after_delete(tmp_path: Path) -> None:
    """`octop chats create` must work again once the dangling session is cleared.

    Pre-fix this crashed on `assert row is not None`, so the very command meant
    to create a fresh dashboard thread could not rescue a dangling agent.
    """
    user_id, session_key, thread_id = _seed_dashboard_thread(tmp_path)
    delete_thread_offline("a1", thread_id, home=tmp_path)

    from octop.cli.support.offline_ops import create_thread_offline

    created = create_thread_offline(agent_id="a1", user_id=user_id, home=tmp_path)
    assert created["thread_id"] != thread_id
    with open_cli_services(tmp_path) as svc:
        assert svc.thread_repo.get(created["thread_id"]) is not None
        row = svc.session_repo.get(session_key)
        assert row is not None
        assert row.thread_id == created["thread_id"]
