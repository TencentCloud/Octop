"""Tests for offline channel CLI helpers."""

from __future__ import annotations

from pathlib import Path

from octop.cli.support.db import open_cli_services
from octop.cli.support.offline_ops import (
    create_channel_offline,
    patch_channel_offline,
)


def test_patch_channel_offline_merges_nested_config(tmp_path: Path) -> None:
    with open_cli_services(home=tmp_path) as services:
        user_id = services.user_repo.create(username="alice", password_hash="hash", role="admin")
        services.agent_repo.create(agent_id="agent-1", user_id=user_id, name="main")

    created = create_channel_offline(
        agent_id="agent-1",
        user_id=user_id,
        kind="feishu",
        name="feishu",
        config={"app_id": "cli_xxx", "app_secret": "secret"},
        home=tmp_path,
    )

    updated = patch_channel_offline(
        "agent-1",
        created["channel_id"],
        config={"group_context": {"enabled": True}},
        home=tmp_path,
    )

    assert updated["config"] == {
        "app_id": "cli_xxx",
        "app_secret": "secret",
        "group_context": {"enabled": True},
    }


def test_patch_channel_offline_replaces_nested_values(tmp_path: Path) -> None:
    with open_cli_services(home=tmp_path) as services:
        user_id = services.user_repo.create(username="alice", password_hash="hash", role="admin")
        services.agent_repo.create(agent_id="agent-1", user_id=user_id, name="main")

    created = create_channel_offline(
        agent_id="agent-1",
        user_id=user_id,
        kind="feishu",
        name="feishu",
        config={"group_context": {"enabled": False, "visibility": "all"}},
        home=tmp_path,
    )

    updated = patch_channel_offline(
        "agent-1",
        created["channel_id"],
        config={"group_context": {"enabled": True}},
        home=tmp_path,
    )

    assert updated["config"] == {"group_context": {"enabled": True, "visibility": "all"}}
