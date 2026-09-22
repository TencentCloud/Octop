"""AutoTagger — policy enforcement and write-only-when-empty behavior."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents import auto_tag
from octop.infra.agents.auto_tag import (
    AUTO_THREAD_TAGS_KEY,
    AutoTagger,
    build_auto_tag_prompt,
    enforce_tag_policy,
    split_llm_tags,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.providers import ProviderRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


class _FakeChat:
    """Records the prompt and replies with a canned text (or raises)."""

    def __init__(self, reply: str | BaseException):
        self._reply = reply
        self.prompt: str | None = None
        self.model_id: str | None = None

    async def ainvoke(self, prompt: str) -> Any:
        self.prompt = prompt
        if isinstance(self._reply, BaseException):
            raise self._reply
        return SimpleNamespace(content=self._reply)


TaggerFixture = tuple[AutoTagger, ThreadRepo, AgentRepo, SettingsRepo, ProviderRepo]


@pytest.fixture
def tagger(tmp_path: Path) -> TaggerFixture:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    agents = AgentRepo(db)
    agents.create(
        agent_id="a1",
        user_id=1,
        name="Agent 1",
        config_json=json.dumps({AUTO_THREAD_TAGS_KEY: True}),
    )
    threads = ThreadRepo(db)
    settings = SettingsRepo(db)
    providers = ProviderRepo(db)
    providers.create(
        name="p1",
        kind="openai",
        api_key="k",
        models_json=json.dumps([{"id": "m1", "name": "m1"}]),
    )
    settings.set_active_model("p1", "m1")
    return AutoTagger(threads, agents, settings, providers), threads, agents, settings, providers


def _insert(
    threads: ThreadRepo,
    thread_id: str,
    *,
    agent_id: str = "a1",
    **kwargs: Any,
) -> None:
    threads.insert(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=1,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=1),
        **kwargs,
    )


def _use_chat(monkeypatch: pytest.MonkeyPatch, chat: _FakeChat) -> None:
    def _fake(provider: object, *, model_id: str | None = None) -> _FakeChat:
        chat.model_id = model_id
        return chat

    monkeypatch.setattr(auto_tag, "build_probe_chat_model", _fake)


# ---- pure helpers ----


def test_split_llm_tags_handles_separators_and_noise():
    assert split_llm_tags("工作、日常，学习\n代码; 部署") == [
        "工作",
        "日常",
        "学习",
        "代码",
        "部署",
    ]
    assert split_llm_tags('1. 工作\n2. "日常"\n3）部署。') == ["工作", "日常", "部署"]


def test_enforce_tag_policy_caps_new_and_total():
    assert enforce_tag_policy(["甲", "乙", "工作"], ["工作"]) == ["甲", "工作"]
    assert enforce_tag_policy(["a", "b", "c", "d"], ["a", "b", "c", "d"]) == [
        "a",
        "b",
        "c",
    ]
    assert enforce_tag_policy(["工作", "工作", "日常"], ["工作", "日常"]) == ["工作", "日常"]


def test_build_prompt_contains_sources_and_candidates():
    prompt = build_auto_tag_prompt(title="写周报", message="帮我写一份周报", candidates=["日常"])
    assert "写周报" in prompt
    assert "帮我写一份周报" in prompt
    assert "日常" in prompt
    empty = build_auto_tag_prompt(title="", message="", candidates=[])
    assert "（无）" in empty


# ---- Agent-level feature switch ----


@pytest.mark.asyncio
async def test_missing_config_defaults_disabled_before_model_resolution(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, agents, _settings, _providers = tagger
    agents.update_config("a1", config_json=json.dumps({}))
    _insert(threads, "thr_1", title="t")
    resolved = False

    def _resolve_model(thread_id: str) -> None:
        nonlocal resolved
        resolved = True

    monkeypatch.setattr(auto, "_resolve_model", _resolve_model)
    chat = _FakeChat(RuntimeError("must not be called"))
    _use_chat(monkeypatch, chat)

    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )

    assert not resolved
    assert chat.prompt is None
    assert threads.get("thr_1").tags == ()  # type: ignore[union-attr]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [False, "true", 1, None])
async def test_only_strict_true_enables_auto_tagging(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
):
    auto, threads, agents, _settings, _providers = tagger
    agents.update_config("a1", config_json=json.dumps({AUTO_THREAD_TAGS_KEY: value}))
    _insert(threads, "thr_1", title="t")
    chat = _FakeChat(RuntimeError("must not be called"))
    _use_chat(monkeypatch, chat)

    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )

    assert chat.prompt is None
    assert threads.get("thr_1").tags == ()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_legacy_settings_value_does_not_disable_enabled_agent(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, settings, _providers = tagger
    settings.set(AUTO_THREAD_TAGS_KEY, "0")
    _insert(threads, "thr_1", title="t")
    chat = _FakeChat("工作")
    _use_chat(monkeypatch, chat)

    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )

    assert chat.prompt is not None
    assert threads.get("thr_1").tags == ("工作",)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_agent_switches_are_isolated(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, agents, _settings, _providers = tagger
    agents.create(
        agent_id="a2",
        user_id=1,
        name="Agent 2",
        config_json=json.dumps({AUTO_THREAD_TAGS_KEY: False}),
    )
    _insert(threads, "thr_1", title="enabled")
    _insert(threads, "thr_2", agent_id="a2", title="disabled")
    chat = _FakeChat("工作")
    _use_chat(monkeypatch, chat)

    await auto.maybe_tag_thread(
        agent_id="a2", user_id=1, thread_id="thr_2", title="disabled", first_message="m"
    )
    assert chat.prompt is None
    assert threads.get("thr_2").tags == ()  # type: ignore[union-attr]

    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="enabled", first_message="m"
    )
    assert chat.prompt is not None
    assert threads.get("thr_1").tags == ("工作",)  # type: ignore[union-attr]


# ---- AutoTagger behavior ----


@pytest.mark.asyncio
async def test_writes_tags_when_empty(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, _settings, _providers = tagger
    _insert(threads, "thr_seed", tags=["日常"])
    _insert(threads, "thr_1", title="写周报")
    chat = _FakeChat("工作、日常、临时新词甲、临时新词乙")
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1",
        user_id=1,
        thread_id="thr_1",
        title="写周报",
        first_message="帮我写周报",
    )
    assert threads.get("thr_1").tags == ("工作", "日常")  # type: ignore[union-attr]
    assert chat.prompt is not None and "日常" in chat.prompt


@pytest.mark.asyncio
async def test_skips_when_tags_already_set(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, _settings, _providers = tagger
    _insert(threads, "thr_1", tags=["manual"])
    chat = _FakeChat(RuntimeError("must not be called"))
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ("manual",)  # type: ignore[union-attr]
    assert chat.prompt is None


@pytest.mark.asyncio
async def test_swallows_llm_failure(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, _settings, _providers = tagger
    _insert(threads, "thr_1", title="t")
    _use_chat(monkeypatch, _FakeChat(RuntimeError("provider down")))
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_no_active_model_skips(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, settings, _providers = tagger
    settings.delete("active_model")
    _insert(threads, "thr_1", title="t")
    chat = _FakeChat(RuntimeError("must not be called"))
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert chat.prompt is None


@pytest.mark.asyncio
async def test_user_edit_during_llm_call_wins(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, _settings, _providers = tagger

    class _SlowChat:
        async def ainvoke(self, prompt: str) -> Any:
            threads.set_tags("thr_1", ["用户手打的"])
            return SimpleNamespace(content="工作")

    _use_chat(monkeypatch, _SlowChat())
    _insert(threads, "thr_1", title="t")
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ("用户手打的",)  # type: ignore[union-attr]


# ---- model fallback chain ----


@pytest.mark.asyncio
async def test_falls_back_to_thread_model_ref(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, settings, _providers = tagger
    settings.delete("active_model")
    _insert(threads, "thr_1", title="t")
    threads.update_composer("thr_1", model_ref="p1/m1")
    chat = _FakeChat("工作")
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ("工作",)  # type: ignore[union-attr]
    assert chat.model_id == "m1"


@pytest.mark.asyncio
async def test_falls_back_to_injected_fallback(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    _auto, threads, agents, settings, providers = tagger
    settings.delete("active_model")
    _insert(threads, "thr_1", title="t")
    auto = AutoTagger(
        threads,
        agents,
        settings,
        providers,
        fallback_model_ref=lambda: "p1/m1",
    )
    chat = _FakeChat("工作")
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ("工作",)  # type: ignore[union-attr]
    assert chat.model_id == "m1"


@pytest.mark.asyncio
async def test_settings_provider_missing_falls_back_to_thread_ref(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    auto, threads, _agents, settings, _providers = tagger
    settings.set_active_model("ghost", "m1")
    _insert(threads, "thr_1", title="t")
    threads.update_composer("thr_1", model_ref="p1/m1")
    chat = _FakeChat("工作")
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert threads.get("thr_1").tags == ("工作",)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_fallback_ref_unusable_skips(
    tagger: TaggerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    _auto, threads, agents, settings, providers = tagger
    settings.delete("active_model")
    _insert(threads, "thr_1", title="t")
    auto = AutoTagger(
        threads,
        agents,
        settings,
        providers,
        fallback_model_ref=lambda: "ghost/m1",
    )
    chat = _FakeChat(RuntimeError("must not be called"))
    _use_chat(monkeypatch, chat)
    await auto.maybe_tag_thread(
        agent_id="a1", user_id=1, thread_id="thr_1", title="t", first_message="m"
    )
    assert chat.prompt is None
    assert threads.get("thr_1").tags == ()  # type: ignore[union-attr]
