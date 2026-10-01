"""tests/integration/test_chat_polish_model_ref.py — polish validates ``default_model``.

``docs/api.md`` documents ``POST /agents/{id}/chat/polish`` as taking
``body {text, default_model?}``. Every other endpoint that accepts a client
supplied model ref rejects one that is not an enabled model on a usable
provider; these tests pin that gate for polish too.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.factory import ChatModelFactory

from tests.support.app import octop_client
from tests.support.auth import (
    auth_header,
    bootstrap_admin,
    create_agent,
    ensure_users,
    seed_openai_provider,
)
from tests.support.fakes import FakeHarnessAgent

# Mirrors the catalog ``seed_openai_provider`` writes to the provider store, so
# the harness factory and ``providers.is_model_ref_usable`` agree on what
# "enabled" means for the same ref.
_PROVIDER = ProviderConfig(
    id="openai",
    base_url="https://api.openai.com/v1",
    api_key="k",
    models=[
        ModelConfig(id="gpt-4o"),
        ModelConfig(id="gpt-4o-mini", enabled=False),
    ],
)


@pytest.fixture
async def env(tmp_octop_home: Path) -> AsyncIterator[Any]:
    fake = FakeHarnessAgent(chunks=[])
    async with octop_client(tmp_octop_home, fake_agent=fake) as (c, srv):
        await bootstrap_admin(c, tmp_octop_home)
        admin_auth = await auth_header(c)
        await seed_openai_provider(c, admin_auth)
        users = await ensure_users(c, admin_auth, "alice")
        aid = await create_agent(c, users["alice"])
        agent = srv.app_runtime.agent_registry.get_agent(aid)
        # A running ``HarnessAgent`` owns a real factory built from the provider
        # catalog; the fake ships without one, so hand it the real class rather
        # than a stub that could not raise what production raises.
        factory = ChatModelFactory([_PROVIDER])
        factory.bind_runtime(get_protocol=lambda _ref: None)
        agent.model_factory = factory
        agent.config.pick_default_model_ref = lambda: "openai/gpt-4o"
        yield c, srv, fake, users["alice"], aid


async def test_polish_rejects_model_on_unknown_provider(env: Any) -> None:
    c, _srv, _fake, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/chat/polish",
        headers=auth,
        json={"text": "make it nicer", "default_model": "nope/gpt-4o"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_polish_rejects_disabled_model(env: Any) -> None:
    c, _srv, _fake, auth, aid = env
    r = await c.post(
        f"/api/agents/{aid}/chat/polish",
        headers=auth,
        json={"text": "make it nicer", "default_model": "openai/gpt-4o-mini"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"


async def test_polish_polishes_with_enabled_model_ref(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, _srv, _fake, auth, aid = env
    asked: list[str] = []

    async def _fake_ainvoke(llm: Any, messages: list[Any], *, timeout: float | None = 30.0) -> str:
        asked.append(llm.model_ref)
        return "Make it nicer, please."

    monkeypatch.setattr(
        "octop.api.routers.chat.routes.ainvoke_text",
        _fake_ainvoke,
    )
    r = await c.post(
        f"/api/agents/{aid}/chat/polish",
        headers=auth,
        json={"text": "make it nicer", "default_model": "openai/gpt-4o"},
    )
    assert r.status_code == 200
    assert r.json() == {"text": "Make it nicer, please."}
    assert asked == ["openai/gpt-4o"]


async def test_polish_falls_back_to_agent_default_model(
    env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An omitted ``default_model`` is the agent's own pick, not client input."""
    c, _srv, _fake, auth, aid = env
    asked: list[str] = []

    async def _fake_ainvoke(llm: Any, messages: list[Any], *, timeout: float | None = 30.0) -> str:
        asked.append(llm.model_ref)
        return "Make it nicer, please."

    monkeypatch.setattr(
        "octop.api.routers.chat.routes.ainvoke_text",
        _fake_ainvoke,
    )
    r = await c.post(
        f"/api/agents/{aid}/chat/polish",
        headers=auth,
        json={"text": "make it nicer"},
    )
    assert r.status_code == 200
    assert asked == ["openai/gpt-4o"]
