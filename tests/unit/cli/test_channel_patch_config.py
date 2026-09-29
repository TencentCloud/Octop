"""Tests for `octop channel patch --config`, which must merge, not replace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.main import cli
from octop.cli.support.offline_ops import (
    _merge_channel_config,
    create_channel_offline,
    get_channel_offline,
    patch_channel_offline,
)

_AGENT_ID = "01CHANNELPATCHAGENT"


def _bootstrap_agent(home: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["init", "--admin-username", "alice", "--admin-password", "TestPass12", "--yes"],
    )
    assert result.exit_code == 0, result.output

    from octop.cli.support.db import open_cli_services
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.users import UserRepo

    with open_cli_services(home=home) as svc:
        user = UserRepo(svc.db).get_by_username("alice")
        assert user is not None
        AgentRepo(svc.db).create(
            agent_id=_AGENT_ID,
            user_id=int(user.id),
            name="main",
            config_json=json.dumps({}),
        )


def _seed_feishu_channel(home: Path, config: dict[str, Any]) -> str:
    return create_channel_offline(
        agent_id=_AGENT_ID,
        user_id=1,
        kind="feishu",
        name="feishu",
        config=config,
        home=home,
    )["channel_id"]


# ── merge helper ─────────────────────────────────────────────────────────────


def test_merge_keeps_top_level_siblings() -> None:
    stored = {"app_id": "cli_x", "app_secret": "s3cret"}
    merged = _merge_channel_config(stored, {"group_context": {"enabled": True}})
    assert merged == {
        "app_id": "cli_x",
        "app_secret": "s3cret",
        "group_context": {"enabled": True},
    }


def test_merge_recurses_into_nested_objects() -> None:
    stored = {"group_context": {"enabled": True, "visibility": "admins", "limits": {"max": 3}}}
    merged = _merge_channel_config(
        stored, {"group_context": {"visibility": "all", "limits": {"max": 9}}}
    )
    assert merged["group_context"] == {
        "enabled": True,
        "visibility": "all",
        "limits": {"max": 9},
    }
    # The stored mapping is not mutated in place.
    assert stored["group_context"]["visibility"] == "admins"


def test_merge_patch_value_wins_for_scalars_and_retypes() -> None:
    stored = {"a": 1, "b": {"x": 1}, "c": "text"}
    merged = _merge_channel_config(stored, {"a": 2, "b": None, "c": {"nested": True}})
    assert merged == {"a": 2, "b": None, "c": {"nested": True}}


# ── patch_channel_offline ─────────────────────────────────────────────────────


def test_patch_config_preserves_credentials(tmp_octop_home: Path) -> None:
    """Regression for #1190: a partial --config used to wipe every other key."""
    _bootstrap_agent(tmp_octop_home)
    channel_id = _seed_feishu_channel(
        tmp_octop_home,
        {"app_id": "cli_xxx", "app_secret": "s3cret"},
    )

    patch_channel_offline(
        _AGENT_ID,
        channel_id,
        config={"group_context": {"enabled": True, "visibility": "all"}},
        home=tmp_octop_home,
    )

    stored = get_channel_offline(_AGENT_ID, channel_id, home=tmp_octop_home)["config"]
    assert stored == {
        "app_id": "cli_xxx",
        "app_secret": "s3cret",
        "group_context": {"enabled": True, "visibility": "all"},
    }


def test_patch_config_deep_merges_nested_object(tmp_octop_home: Path) -> None:
    _bootstrap_agent(tmp_octop_home)
    channel_id = _seed_feishu_channel(
        tmp_octop_home,
        {
            "app_id": "cli_xxx",
            "group_context": {
                "enabled": True,
                "visibility": "admins",
                "activation": "always",
            },
        },
    )

    patch_channel_offline(
        _AGENT_ID,
        channel_id,
        config={"group_context": {"visibility": "all"}},
        home=tmp_octop_home,
    )

    stored = get_channel_offline(_AGENT_ID, channel_id, home=tmp_octop_home)["config"]
    assert stored["group_context"] == {
        "enabled": True,
        "visibility": "all",
        "activation": "always",
    }
    assert stored["app_id"] == "cli_xxx"


def test_patch_without_config_leaves_config_untouched(tmp_octop_home: Path) -> None:
    _bootstrap_agent(tmp_octop_home)
    channel_id = _seed_feishu_channel(tmp_octop_home, {"app_id": "cli_xxx"})

    patch_channel_offline(_AGENT_ID, channel_id, name="renamed", enabled=False, home=tmp_octop_home)

    row = get_channel_offline(_AGENT_ID, channel_id, home=tmp_octop_home)
    assert row["name"] == "renamed"
    assert row["enabled"] is False
    assert row["config"] == {"app_id": "cli_xxx"}


def test_patch_config_merges_into_an_undecodable_stored_value(
    tmp_octop_home: Path,
) -> None:
    """A corrupt config_json must not make --config fail; it merges onto {}."""
    _bootstrap_agent(tmp_octop_home)
    channel_id = _seed_feishu_channel(tmp_octop_home, {"app_id": "cli_xxx"})

    from octop.cli.support.db import open_cli_services

    with open_cli_services(home=tmp_octop_home) as svc, svc.db.transaction() as conn:
        conn.execute(
            "UPDATE channels SET config_json = ? WHERE channel_id = ?",
            ("{not json", channel_id),
        )

    patch_channel_offline(_AGENT_ID, channel_id, config={"enabled": True}, home=tmp_octop_home)

    stored = get_channel_offline(_AGENT_ID, channel_id, home=tmp_octop_home)["config"]
    assert stored == {"enabled": True}


def test_channel_patch_help_documents_the_merge() -> None:
    result = CliRunner().invoke(cli, ["channel", "patch", "--help"])
    assert result.exit_code == 0, result.output
    assert "deep-merged" in result.output


def test_patch_rejects_a_channel_from_another_agent(tmp_octop_home: Path) -> None:
    from octop.infra.errors import OctopError

    _bootstrap_agent(tmp_octop_home)
    channel_id = _seed_feishu_channel(tmp_octop_home, {"app_id": "cli_xxx"})

    with pytest.raises(OctopError):
        patch_channel_offline("01SOMEOTHERAGENT", channel_id, config={"x": 1}, home=tmp_octop_home)
