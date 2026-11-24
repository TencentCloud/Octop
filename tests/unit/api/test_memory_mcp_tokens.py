from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from octop.api.routers import memory_mcp
from octop.infra.agents import memory_sharing
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

_USER = cast(User, SimpleNamespace(id=7))
_SERVER = cast(OctopServer, SimpleNamespace())
_BASE_URL = "https://octop.example"


@pytest.fixture(autouse=True)
def connected_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        memory_sharing,
        "get_session",
        lambda _uid: memory_sharing.SharingSession(
            "management", "*", ("admin",), "2099-01-01T00:00:00+00:00", 0
        ),
    )


@pytest.mark.parametrize("scopes", [[], ["write"], ["read", "read"], ["read", "review"]])
def test_rejects_client_scopes_outside_read_only_or_read_write(scopes: list[str]) -> None:
    with pytest.raises(ValidationError):
        memory_mcp.TokenCreateBody.model_validate(
            {"name": "Cursor", "space_id": "project", "scopes": scopes}
        )


def test_uses_the_selected_space_without_requiring_a_local_expert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued: list[tuple[int, str, str, list[str]]] = []

    def create(uid: int, space_id: str, client: str, scopes: list[str]) -> dict[str, Any]:
        issued.append((uid, space_id, client, scopes))
        # The #59 response has no creation timestamp or space field.
        return {"token_id": "mt_one", "client_name": client, "token": "fresh", "token_hint": "hint"}

    monkeypatch.setattr(memory_sharing, "create_token_in", create)
    result = memory_mcp.create_token(
        memory_mcp.TokenCreateBody(name=" Cursor ", space_id="project", scopes=["read"]),
        _USER,
        _SERVER,
        _BASE_URL,
    )

    assert issued == [(7, "project", "Cursor", ["read"])]
    assert result.token == "fresh"
    assert result.space_id == "project"
    assert result.scopes == ["read"]
    assert result.mcp_url == f"{_BASE_URL}/mcp/"
    assert result.created_at


def test_existing_client_payload_still_uses_expert_default_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experts = [{"agent_id": "alpha", "space_id": "agent_alpha"}]
    monkeypatch.setattr(memory_mcp, "_experts", lambda _server, _user: experts)
    monkeypatch.setattr(memory_mcp, "_space_for_expert", lambda *_: experts[0])

    def create(_uid: int, space_id: str, client: str, scopes: list[str]) -> dict[str, Any]:
        assert space_id == "agent_alpha"
        assert scopes == ["read", "write", "review"]
        return {"token_id": "mt_legacy", "client_name": client, "token": "fresh"}

    monkeypatch.setattr(memory_sharing, "create_token_in", create)
    result = memory_mcp.create_token(
        memory_mcp.TokenCreateBody(name="existing", expert_ids=["alpha"]),
        _USER,
        _SERVER,
        _BASE_URL,
    )
    assert result.expert_ids == ["alpha"]


def test_rotate_finds_credential_in_the_selected_space_before_rotating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = {
        "token_id": "mt_one",
        "client_name": "Cursor",
        "space_id": "project",
        "scopes": ["read"],
        "token_hint": "old",
    }
    monkeypatch.setattr(
        memory_sharing,
        "list_tokens_in",
        lambda _uid, space: {"tokens": [record] if space == "project" else []},
    )
    rotated: list[str] = []

    def rotate(_uid: int, token_id: str) -> dict[str, Any]:
        rotated.append(token_id)
        return {"token_hint": "new", "token": "fresh"}

    monkeypatch.setattr(memory_sharing, "rotate_token", rotate)
    with pytest.raises(OctopError) as exc:
        memory_mcp.rotate_token("mt_one", _USER, _SERVER, _BASE_URL, space_id="other")
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert not rotated

    result = memory_mcp.rotate_token("mt_one", _USER, _SERVER, _BASE_URL, space_id="project")
    assert rotated == ["mt_one"]
    assert result.token_hint == "new"
    assert result.token == "fresh"
    assert result.scopes == ["read"]
