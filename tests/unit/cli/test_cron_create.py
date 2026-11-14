"""Offline cron create: latest channel vs a pinned historical thread."""

from __future__ import annotations

from pathlib import Path

from octop.cli.support.db import open_cli_services
from octop.cli.support.offline_ops import create_cron_offline
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_ulid


def test_create_cron_offline_pins_history_thread(tmp_path: Path) -> None:
    aid = new_ulid()
    with open_cli_services(tmp_path) as svc:
        uid = svc.user_repo.create(username="u", password_hash="h", role="user")
        svc.agent_repo.create(agent_id=aid, user_id=uid, name="bot")
        session_key = ThreadRegistry.dashboard_key(agent_id=aid, user_id=uid)
        svc.thread_repo.insert(
            thread_id="thr_hist",
            agent_id=aid,
            user_id=uid,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            session_key=session_key,
            title="old chat",
            last_active=10,
        )
        svc.session_repo.upsert(
            session_key=session_key,
            agent_id=aid,
            user_id=uid,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            chat_type=ThreadRegistry.CHAT_TYPE_DM,
            thread_id="thr_hist",
        )

    row = create_cron_offline(
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="ping",
        thread_id="thr_hist",
        home=tmp_path,
    )
    assert row["session_key"] == "thread:thr_hist"


def test_create_cron_offline_defaults_to_dashboard_channel(tmp_path: Path) -> None:
    aid = new_ulid()
    with open_cli_services(tmp_path) as svc:
        uid = svc.user_repo.create(username="u", password_hash="h", role="user")
        svc.agent_repo.create(agent_id=aid, user_id=uid, name="bot")

    row = create_cron_offline(
        agent_id=aid,
        user_id=uid,
        trigger="interval:60",
        prompt="ping",
        home=tmp_path,
    )
    assert row["session_key"] == ThreadRegistry.dashboard_key(agent_id=aid, user_id=uid)
