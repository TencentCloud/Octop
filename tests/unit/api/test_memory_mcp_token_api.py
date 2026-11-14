"""Unit tests for the memory MCP token HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from octop.api.deps import current_user, get_server
from octop.api.routers import memory_mcp
from octop.infra.agents.memory_tokens import TOKEN_PREFIX, hash_token
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import RepoBundle
from octop.infra.errors import OctopError
from octop.infra.users.identity import Role, User
from octop.infra.utils.ulid import new_ulid


@dataclass
class Seeded:
    db: SqlitePool
    repos: RepoBundle
    owner: User
    other: User
    owner_agent: str
    other_agent: str


def _seed(tmp_path: Path) -> Seeded:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repos = RepoBundle.from_pool(db)
    users = UserRepo(db)
    owner_id = users.create(
        username="owner", password_hash="h", role="user", permissions=["memory"]
    )
    other_id = users.create(
        username="other", password_hash="h", role="user", permissions=["memory"]
    )
    owner_agent = new_ulid()
    other_agent = new_ulid()
    repos.agent_repo.create(agent_id=owner_agent, user_id=owner_id, name="owner-bot")
    repos.agent_repo.create(agent_id=other_agent, user_id=other_id, name="other-bot")
    return Seeded(
        db=db,
        repos=repos,
        owner=User(
            id=owner_id,
            username="owner",
            role=Role.USER,
            display_name=None,
            permissions=["memory"],
        ),
        other=User(
            id=other_id,
            username="other",
            role=Role.USER,
            display_name=None,
            permissions=["memory"],
        ),
        owner_agent=owner_agent,
        other_agent=other_agent,
    )


@pytest.fixture
def seeded(tmp_path: Path) -> Seeded:
    return _seed(tmp_path)


def _client(seeded: Seeded, user: User) -> TestClient:
    server = SimpleNamespace(services=SimpleNamespace(repos=seeded.repos))
    app = FastAPI()
    app.include_router(memory_mcp.router)

    @app.exception_handler(OctopError)
    async def _octop_error(request: Request, exc: OctopError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_envelope())

    app.dependency_overrides[get_server] = lambda: server
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def _create_token(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/memory-mcp/tokens", json={"name": "codex@macbook", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_plaintext_once(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    data = _create_token(client, expert_ids=[seeded.owner_agent])

    token = data["token"]
    assert token.startswith(TOKEN_PREFIX)
    assert data["token_hint"] == f"{token[:9]}…{token[-4:]}"
    assert data["name"] == "codex@macbook"
    assert data["expert_ids"] == [seeded.owner_agent]
    assert data["revoked_at"] is None
    assert data["last_used_at"] is None

    row = seeded.repos.memory_mcp_token_repo.get_for_user(data["token_id"], user_id=seeded.owner.id)
    assert row is not None
    assert row.token_hash == hash_token(token)
    assert row.token_hint == data["token_hint"]


def test_list_never_returns_plaintext(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token = _create_token(client)["token"]

    response = client.get("/memory-mcp/tokens")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert "token" not in items[0]
    assert token not in response.text


def test_revoke_only_own_token(seeded: Seeded) -> None:
    owner_client = _client(seeded, seeded.owner)
    token_id = _create_token(owner_client)["token_id"]

    other_client = _client(seeded, seeded.other)
    foreign = other_client.delete(f"/memory-mcp/tokens/{token_id}")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "NOT_FOUND"
    row = seeded.repos.memory_mcp_token_repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None
    assert row.revoked_at is None

    first = owner_client.delete(f"/memory-mcp/tokens/{token_id}")
    assert first.status_code == 200
    assert first.json() == {"revoked": True}
    second = owner_client.delete(f"/memory-mcp/tokens/{token_id}")
    assert second.status_code == 200
    assert second.json() == {"revoked": False}


def test_create_rejects_inaccessible_expert(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)

    forbidden = client.post(
        "/memory-mcp/tokens",
        json={"name": "codex@macbook", "expert_ids": [seeded.other_agent]},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    missing = client.post(
        "/memory-mcp/tokens",
        json={"name": "codex@macbook", "expert_ids": [new_ulid()]},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "AGENT_NOT_FOUND"

    assert seeded.repos.memory_mcp_token_repo.list_for_user(seeded.owner.id) == []


def test_empty_expert_ids_means_unrestricted(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    data = _create_token(client, expert_ids=[])
    assert data["expert_ids"] is None


def test_patch_renames_and_keeps_the_experts(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    created = _create_token(client, expert_ids=[seeded.owner_agent])

    response = client.patch(
        f"/memory-mcp/tokens/{created['token_id']}", json={"name": "claude@laptop"}
    )

    assert response.status_code == 200, response.text
    patched = response.json()
    assert patched["name"] == "claude@laptop"
    assert patched["expert_ids"] == [seeded.owner_agent]
    assert patched["token_hint"] == created["token_hint"]
    assert patched["revoked_at"] is None
    assert "token" not in patched
    assert created["token"] not in response.text


def test_patch_rebinds_experts_and_clears_the_restriction(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client, expert_ids=[seeded.owner_agent])["token_id"]

    rebound = client.patch(f"/memory-mcp/tokens/{token_id}", json={"expert_ids": []})
    assert rebound.status_code == 200, rebound.text
    assert rebound.json()["expert_ids"] is None

    rebound = client.patch(
        f"/memory-mcp/tokens/{token_id}", json={"expert_ids": [seeded.owner_agent]}
    )
    assert rebound.json()["expert_ids"] == [seeded.owner_agent]

    cleared = client.patch(f"/memory-mcp/tokens/{token_id}", json={"expert_ids": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["expert_ids"] is None

    row = seeded.repos.memory_mcp_token_repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None
    assert row.expert_ids is None


def test_patch_other_users_token_is_not_found(seeded: Seeded) -> None:
    token_id = _create_token(_client(seeded, seeded.owner))["token_id"]

    response = _client(seeded, seeded.other).patch(
        f"/memory-mcp/tokens/{token_id}", json={"name": "hijack"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    row = seeded.repos.memory_mcp_token_repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None and row.name == "codex@macbook"


def test_patch_revoked_token_is_a_conflict(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client)["token_id"]
    assert client.delete(f"/memory-mcp/tokens/{token_id}").status_code == 200

    response = client.patch(f"/memory-mcp/tokens/{token_id}", json={"name": "late"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert "revoked" in response.json()["error"]["message"]


def test_patch_rejects_inaccessible_expert_and_keeps_the_row(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client, expert_ids=[seeded.owner_agent])["token_id"]

    forbidden = client.patch(
        f"/memory-mcp/tokens/{token_id}", json={"expert_ids": [seeded.other_agent]}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    missing = client.patch(f"/memory-mcp/tokens/{token_id}", json={"expert_ids": [new_ulid()]})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "AGENT_NOT_FOUND"

    row = seeded.repos.memory_mcp_token_repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None and row.expert_ids == [seeded.owner_agent]


def test_patch_requires_a_field(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client)["token_id"]

    assert client.patch(f"/memory-mcp/tokens/{token_id}", json={}).status_code == 422
    assert client.patch(f"/memory-mcp/tokens/{token_id}", json={"name": None}).status_code == 422


def test_create_requires_memory_permission(seeded: Seeded) -> None:
    denied = User(
        id=seeded.owner.id,
        username="owner",
        role=Role.USER,
        display_name=None,
        permissions=[],
    )
    response = _client(seeded, denied).post("/memory-mcp/tokens", json={"name": "codex@macbook"})
    assert response.status_code == 403
    assert response.json()["error"]["details"]["permission"] == "memory"


def test_create_reports_empty_client_state(seeded: Seeded) -> None:
    data = _create_token(_client(seeded, seeded.owner))
    assert data["disabled_clients"] is None
    assert data["client_stats"] is None


def test_list_reports_client_stats_and_disabled_clients(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    created = _create_token(client)
    repo = seeded.repos.memory_mcp_token_repo
    repo.record_client(created["token_id"], "codex", now="2026-01-01T00:00:00Z")
    repo.record_client(created["token_id"], "codex", now="2026-01-02T00:00:00Z")

    patched = client.patch(
        f"/memory-mcp/tokens/{created['token_id']}", json={"disabled_clients": ["cursor"]}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["disabled_clients"] == ["cursor"]
    assert patched.json()["client_stats"]["codex"]["count"] == 2

    items = client.get("/memory-mcp/tokens").json()
    assert items[0]["disabled_clients"] == ["cursor"]
    assert items[0]["client_stats"] == {
        "codex": {
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-02T00:00:00Z",
            "count": 2,
        }
    }


def test_patch_sets_and_clears_disabled_clients(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client)["token_id"]
    repo = seeded.repos.memory_mcp_token_repo

    # Only disabled_clients: the expert list and name stay untouched.
    set_response = client.patch(
        f"/memory-mcp/tokens/{token_id}", json={"disabled_clients": ["codex", "cursor"]}
    )
    assert set_response.status_code == 200, set_response.text
    assert set_response.json()["disabled_clients"] == ["codex", "cursor"]
    assert set_response.json()["name"] == "codex@macbook"
    row = repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None and row.disabled_clients == ["codex", "cursor"]

    cleared = client.patch(f"/memory-mcp/tokens/{token_id}", json={"disabled_clients": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["disabled_clients"] is None
    row = repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None and row.disabled_clients is None

    client.patch(f"/memory-mcp/tokens/{token_id}", json={"disabled_clients": ["kiro"]})
    nulled = client.patch(f"/memory-mcp/tokens/{token_id}", json={"disabled_clients": None})
    assert nulled.status_code == 200, nulled.text
    assert nulled.json()["disabled_clients"] is None
    row = repo.get_for_user(token_id, user_id=seeded.owner.id)
    assert row is not None and row.disabled_clients is None


def test_rotate_issues_a_new_secret_and_invalidates_the_old_one(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    created = _create_token(client, expert_ids=[seeded.owner_agent])
    repo = seeded.repos.memory_mcp_token_repo

    response = client.post(f"/memory-mcp/tokens/{created['token_id']}/rotate")
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["token_id"] == created["token_id"]
    assert rotated["token"] != created["token"]
    assert rotated["expert_ids"] == [seeded.owner_agent]
    assert rotated["token_hint"] != created["token_hint"]

    row = repo.get_by_token_hash(hash_token(created["token"]))
    assert row is None  # the old plaintext no longer resolves
    row = repo.get_by_token_hash(hash_token(rotated["token"]))
    assert row is not None and row.token_id == created["token_id"]


def test_rotate_other_users_token_is_not_found(seeded: Seeded) -> None:
    created = _create_token(_client(seeded, seeded.owner))
    other = _client(seeded, seeded.other)
    response = other.post(f"/memory-mcp/tokens/{created['token_id']}/rotate")
    assert response.status_code == 404


def test_rotate_revoked_token_is_a_conflict(seeded: Seeded) -> None:
    client = _client(seeded, seeded.owner)
    token_id = _create_token(client)["token_id"]
    assert client.delete(f"/memory-mcp/tokens/{token_id}").status_code == 200
    response = client.post(f"/memory-mcp/tokens/{token_id}/rotate")
    assert response.status_code == 409
