"""A managed turn hands harness MCP specs for connectors and knowledge."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.agents.acp.turn import (
    KnowledgeScope,
    attach_managed_turn,
    knowledge_scope,
    retain_knowledge_scope,
)


def test_knowledge_token_is_stable_for_the_same_selection() -> None:
    scope = KnowledgeScope(
        user_id=3,
        is_admin=False,
        knowledge_base_ids=("kb1",),
        locale="zh",
        catalog=(("kb1", "手册", "产品说明"),),
    )
    first = retain_knowledge_scope(scope)
    second = retain_knowledge_scope(scope)
    assert first == second


@pytest.mark.asyncio
async def test_managed_turn_adds_connector_and_knowledge_specs() -> None:
    class Svc:
        async def mcp_configs_for_user(self, user_id: int) -> dict[str, object]:
            assert user_id == 7
            return {"notes": {"transport": "http", "url": "http://127.0.0.1:9/mcp"}}

    class Manager:
        _connector_svc = Svc()
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

    request: dict[str, object] = {
        "user": "7",
        "mcp_servers": ["notes"],
        "configurable": {
            "knowledge_base_ids": ["kb1"],
            "knowledge_base_catalog": [{"id": "kb1", "name": "手册", "description": ""}],
            "locale": "zh",
            "user_is_admin": False,
        },
    }
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert set(specs) == {"notes", "octop-knowledge", "octop-files"}
    assert "/api/internal/mcp/files?token=" in specs["octop-files"]["url"]
    knowledge = specs["octop-knowledge"]
    assert knowledge["transport"] == "http"
    assert "127.0.0.1:8000/api/internal/mcp/knowledge?token=" in knowledge["url"]
    token = knowledge["url"].split("token=", 1)[1]
    scope = knowledge_scope(token)
    assert scope is not None
    assert scope.knowledge_base_ids == ("kb1",)
    assert scope.catalog_rows()[0]["name"] == "手册"


@pytest.mark.asyncio
async def test_native_turn_leaves_the_request_alone() -> None:
    class Manager:
        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="native")

    request: dict[str, object] = {"configurable": {}}
    await attach_managed_turn(Manager(), "GWN", request)
    assert request["configurable"] == {}


@pytest.mark.asyncio
async def test_ask_mode_does_not_attach_connectors() -> None:
    class Svc:
        async def mcp_configs_for_user(self, user_id: int) -> dict[str, object]:
            return {
                "notes": {
                    "transport": "http",
                    "url": "http://127.0.0.1:9/mcp",
                    "allowed_tools": ["search"],
                }
            }

    class Manager:
        _connector_svc = Svc()
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

    request: dict[str, object] = {
        "user": "7",
        "conversation_mode": "ask",
        "mcp_servers": ["notes"],
        "configurable": {"locale": "zh"},
    }
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert set(specs) == {"octop-files"}
    note = configurable["acp_prompt_note"]
    assert isinstance(note, str)
    assert "send_file_to_user" in note

    request["conversation_mode"] = "craft"
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert "notes" in specs
    note = configurable["acp_prompt_note"]
    assert isinstance(note, str)
    assert "search" in note
