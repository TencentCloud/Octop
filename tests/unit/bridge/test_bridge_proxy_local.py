"""Unit tests for hub-local Bridge shadow history-migration responses."""

from __future__ import annotations

import json

import pytest

from octop.api.middleware.bridge_proxy import (
    _local_bridge_shadow_response,
    resolve_tunnel_target,
)
from octop.infra.errors import ErrorCode, OctopError


def test_history_migration_status_is_idle() -> None:
    resp = _local_bridge_shadow_response(
        method="GET",
        rest="/history-migration/status",
    )
    assert resp is not None
    body = json.loads(resp.body)
    assert body["remaining"] == 0
    assert body["can_start"] is False


def test_history_migration_start_rejected() -> None:
    with pytest.raises(OctopError) as ei:
        _local_bridge_shadow_response(
            method="POST",
            rest="/history-migration/start",
        )
    assert ei.value.code == ErrorCode.BRIDGE_REMOTE_UNSUPPORTED


def test_status_is_not_short_circuited() -> None:
    """Runtime status must tunnel to the peer (allowlisted), not be faked here."""
    assert (
        _local_bridge_shadow_response(
            method="GET",
            rest="/status",
        )
        is None
    )


def test_other_paths_pass_through() -> None:
    assert (
        _local_bridge_shadow_response(
            method="GET",
            rest="/threads",
        )
        is None
    )


def test_resolve_agents_and_plugins_path() -> None:
    agents = resolve_tunnel_target("/api/agents/bridge:cid1:aid1/tool-settings")
    assert agents is not None
    assert agents.remote_path == "/api/agents/aid1/tool-settings"
    assert agents.ref.connection_id == "cid1"

    plugins = resolve_tunnel_target("/api/plugins/agents/bridge:cid1:aid1/tools")
    assert plugins is not None
    assert plugins.remote_path == "/api/plugins/agents/aid1/tools"


def test_resolve_unwraps_stale_shadow_thread_id() -> None:
    target = resolve_tunnel_target(
        "/api/agents/bridge:cid1:doctor/threads/01ROOM~bridge:cid1:doctor/history"
    )
    assert target is not None
    assert target.remote_path == "/api/agents/doctor/threads/01ROOM~doctor/history"

    encoded = resolve_tunnel_target(
        "/api/agents/bridge%3Acid1%3Adoctor/threads/01ROOM~bridge%3Acid1%3Adoctor/history"
    )
    assert encoded is not None
    assert encoded.remote_path == "/api/agents/doctor/threads/01ROOM~doctor/history"


def test_resolve_header_tunneled_paths() -> None:
    mbti = resolve_tunnel_target("/api/mbti/current", "bridge:cid1:aid1")
    assert mbti is not None
    assert mbti.remote_path == "/api/mbti/current"
    assert mbti.ref.remote_agent_id == "aid1"

    catalog = resolve_tunnel_target("/api/subagent-catalog/divisions", "bridge:cid1:aid1")
    assert catalog is not None
    acp = resolve_tunnel_target("/api/acp", "bridge:cid1:aid1")
    assert acp is not None
    cron = resolve_tunnel_target("/api/cron/settings", "bridge:cid1:aid1")
    assert cron is not None
    assert cron.remote_path == "/api/cron/settings"
    connectors = resolve_tunnel_target("/api/connector-instances", "bridge:cid1:aid1")
    assert connectors is not None
    models = resolve_tunnel_target("/api/providers/resolved", "bridge:cid1:aid1")
    assert models is not None
    assert models.remote_path == "/api/providers/resolved"
    kb = resolve_tunnel_target("/api/knowledge-bases", "bridge:cid1:aid1")
    assert kb is not None
    env = resolve_tunnel_target("/api/browser/env-status", "bridge:cid1:aid1")
    assert env is not None


def test_resolve_ignores_local_header_and_unscoped_paths() -> None:
    assert resolve_tunnel_target("/api/mbti/current", "01LOCAL") is None
    assert resolve_tunnel_target("/api/users", "bridge:cid1:aid1") is None
    assert resolve_tunnel_target("/api/plugins/install", "bridge:cid1:aid1") is None
