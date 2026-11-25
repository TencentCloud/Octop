"""Unit tests for connector authorization status and re-authorization."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from octop.config import OctopConfig
from octop.infra.connectors.auth_status import (
    custom_auth_status,
)
from octop.infra.connectors.builder import mcp_server_name
from octop.infra.connectors.custom_mcp import shared_mcp_server_name
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.utils.ulid import new_ulid

NOW = 1_800_000_000


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def svc(db: SqlitePool) -> ConnectorService:
    return ConnectorService(
        repo=ConnectorRepo(db),
        secret_repo=SecretRepo(db),
        settings_repo=SettingsRepo(db),
        config=OctopConfig(),
    )


def _user(db: SqlitePool, name: str) -> int:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, 'x', 'user', 1)",
            (name,),
        )
        row = conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()
    assert row is not None
    return int(row["id"])


def _notion(svc: ConnectorService, user_id: int, creds: dict[str, Any]) -> str:
    instance_id = new_ulid()
    svc._repo.create(
        instance_id=instance_id,
        user_id=user_id,
        kind="notion",
        display_name="Notion",
        mcp_server_name=mcp_server_name("notion", instance_id),
    )
    svc.encrypt_and_store(instance_id=instance_id, payload=creds)
    return instance_id


def _custom(svc: ConnectorService, user_id: int, servers: dict[str, dict[str, Any]]) -> None:
    """Save custom servers, then write their stored OAuth state directly."""
    svc.put_custom_servers(
        user_id,
        {name: {k: v for k, v in spec.items() if k != "oauth"} for name, spec in servers.items()},
    )
    stored = dict(svc.get_custom_servers(user_id))
    for name, spec in servers.items():
        if "oauth" in spec:
            stored[name] = {**stored[name], "oauth": spec["oauth"]}
    svc._save_custom_servers(user_id, stored)


# -- status --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("oauth", "expected"),
    [
        (None, None),
        ({"required": True}, "required"),
        ({"required": True, "expired": True}, "expired"),
        ({"access_token": "t", "expires_at": NOW + 60}, "ok"),
        ({"access_token": "t", "expires_at": NOW - 60, "refresh_token": "r"}, "ok"),
        ({"access_token": "t", "expires_at": NOW - 60}, "expired"),
    ],
)
def test_custom_auth_status(oauth: dict[str, Any] | None, expected: str | None) -> None:
    spec: dict[str, Any] = {"transport": "streamable_http", "url": "https://x.example/mcp"}
    if oauth is not None:
        spec["oauth"] = oauth
    assert custom_auth_status(spec, now=NOW) == expected


# -- listing -------------------------------------------------------------------


def test_list_reports_custom_server_status_for_owner_and_viewers(
    svc: ConnectorService, db: SqlitePool
) -> None:
    owner, viewer = _user(db, "u1"), _user(db, "u2")
    _custom(
        svc,
        owner,
        {
            "needs": {
                "transport": "streamable_http",
                "url": "https://a.example/mcp",
                "shared": True,
                "oauth": {"required": True},
            },
            "plain": {"transport": "streamable_http", "url": "https://b.example/mcp"},
        },
    )

    mine = {item["mcp_server_name"]: item for item in svc.list_instances_for_api(owner)}
    assert mine["needs"]["auth_status"] == "required"
    assert "auth_status" not in mine["plain"]
    parent = svc._repo.get_by_user_kind(owner, "custom-mcp")
    assert parent is not None
    shared = {item["mcp_server_name"]: item for item in svc.list_instances_for_api(viewer)}
    assert shared[shared_mcp_server_name(parent.instance_id, "needs")]["auth_status"] == "required"


def test_list_leaves_catalog_connectors_without_status(
    svc: ConnectorService, db: SqlitePool
) -> None:
    uid = _user(db, "u1")
    _notion(svc, uid, {"access_token": "t", "expires_at": 1})

    assert "auth_status" not in svc.list_instances_for_api(uid)[0]


# -- blocked servers -----------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_servers_lists_custom_servers_that_need_authorization(
    svc: ConnectorService, db: SqlitePool
) -> None:
    owner, viewer = _user(db, "u1"), _user(db, "u2")
    expired = _notion(svc, owner, {"access_token": "t", "expires_at": 1})
    _custom(
        svc,
        owner,
        {
            "needs": {
                "transport": "streamable_http",
                "url": "https://a.example/mcp",
                "shared": True,
                "oauth": {"required": True},
            },
            "plain": {"transport": "streamable_http", "url": "https://b.example/mcp"},
        },
    )
    parent = svc._repo.get_by_user_kind(owner, "custom-mcp")
    assert parent is not None
    notion_name = mcp_server_name("notion", expired)

    with patch("octop.infra.connectors.service._token_rejected", new=AsyncMock(return_value=False)):
        blocked = await svc.auth_blocked_servers(owner, [notion_name, "needs", "plain", "gone"])
        for_viewer = await svc.auth_blocked_servers(
            viewer, [shared_mcp_server_name(parent.instance_id, "needs")]
        )

    # Catalog connectors keep their own token handling and are not reported.
    assert [(b["server"], b["auth_status"], b["can_authorize"]) for b in blocked] == [
        ("needs", "required", True),
    ]
    assert blocked[0]["target"] == {"type": "custom_mcp", "server_name": "needs"}
    # Someone else's shared server can only be fixed by its owner.
    assert [(b["auth_status"], b["can_authorize"]) for b in for_viewer] == [("required", False)]


@pytest.mark.asyncio
async def test_a_revoked_token_is_detected_by_probe_and_flagged(
    svc: ConnectorService, db: SqlitePool
) -> None:
    uid = _user(db, "u1")
    _custom(
        svc,
        uid,
        {
            "srv": {
                "transport": "streamable_http",
                "url": "https://a.example/mcp",
                "oauth": {"access_token": "revoked", "expires_at": int(time.time()) + 3600},
            }
        },
    )
    probe = AsyncMock(return_value=True)

    with patch("octop.infra.connectors.service._token_rejected", new=probe):
        blocked = await svc.auth_blocked_servers(uid, ["srv"])

    assert [b["auth_status"] for b in blocked] == ["expired"]
    assert probe.await_args_list[0].args[1]["Authorization"] == "Bearer revoked"
    assert svc.get_custom_servers(uid)["srv"]["oauth"] == {"required": True, "expired": True}
    assert svc.list_instances_for_api(uid)[0]["auth_status"] == "expired"


@pytest.mark.asyncio
async def test_a_working_token_or_unreachable_server_is_not_an_auth_problem(
    svc: ConnectorService, db: SqlitePool
) -> None:
    uid = _user(db, "u1")
    _custom(
        svc,
        uid,
        {
            "srv": {
                "transport": "streamable_http",
                "url": "https://a.example/mcp",
                "oauth": {"access_token": "fine", "expires_at": int(time.time()) + 3600},
            }
        },
    )

    with patch(
        "octop.infra.connectors.probe.probe_streamable_http_mcp",
        new=AsyncMock(return_value={"ok": False, "error_type": "connection", "status_code": 502}),
    ):
        blocked = await svc.auth_blocked_servers(uid, ["srv"])

    assert blocked == []
    assert svc.get_custom_servers(uid)["srv"]["oauth"]["access_token"] == "fine"


@pytest.mark.asyncio
async def test_token_rejected_reads_only_auth_errors() -> None:
    from octop.infra.connectors import service

    with patch(
        "octop.infra.connectors.probe.probe_streamable_http_mcp",
        new=AsyncMock(return_value={"ok": False, "error_type": "auth", "status_code": 401}),
    ):
        assert await service._token_rejected("https://a.example/mcp", {}, kind="x") is True
    with patch(
        "octop.infra.connectors.probe.probe_streamable_http_mcp",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        assert await service._token_rejected("https://a.example/mcp", {}, kind="x") is False
    assert await service._token_rejected("", {}, kind="x") is False
