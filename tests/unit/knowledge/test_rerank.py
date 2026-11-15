"""Reranking retrieved knowledge chunks with a provider's /rerank endpoint."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import rerank as rerank_module
from octop.infra.knowledge import retrieve as retrieve_module
from octop.infra.knowledge.index import KnowledgeIndex
from octop.infra.knowledge.rerank import (
    candidate_count,
    get_rerank_capability,
    rerank_models,
    rerank_scores,
    set_rerank_settings,
)


def _provider(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "id": 3,
        "name": "siliconflow",
        "enabled": True,
        "api_key": "sk-test",
        "base_url": "https://api.example.test/v1/",
        "extra_json": None,
        "get_models": lambda: [
            {"id": "BAAI/bge-reranker-v2-m3", "name": "BGE Reranker"},
            {"id": "custom-ranker", "task": "rerank"},
            {"id": "BAAI/bge-m3", "name": "BGE M3"},
            {"id": "chat-1"},
        ],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _Settings:
    def __init__(self, **values: str) -> None:
        self.values = dict(values)

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def _repo(provider: Any | None) -> SimpleNamespace:
    return SimpleNamespace(get=lambda pid: provider if provider and pid == provider.id else None)


def _enabled_settings() -> _Settings:
    return _Settings(
        knowledge_rerank_enabled="true",
        knowledge_rerank_provider_id="3",
        knowledge_rerank_model="BAAI/bge-reranker-v2-m3",
    )


def test_only_rerank_models_are_offered() -> None:
    assert rerank_models(_provider()) == [
        {"id": "BAAI/bge-reranker-v2-m3", "name": "BGE Reranker"},
        {"id": "custom-ranker", "name": "custom-ranker"},
    ]


@pytest.mark.parametrize(("k", "expected"), [(1, 20), (8, 32), (20, 50), (60, 60)])
def test_candidate_count_widens_the_fetch(k: int, expected: int) -> None:
    assert candidate_count(k) == expected


def test_capability_is_off_by_default() -> None:
    assert get_rerank_capability(_Settings().get, _repo(_provider())) == {
        "enabled": False,
        "provider_id": "",
        "model": "",
        "ready": False,
        "usable": False,
    }


def test_enabling_saves_the_choice() -> None:
    settings = _Settings()
    repo = _repo(_provider())

    set_rerank_settings(
        settings.set, enabled=True, provider_id="3", model="custom-ranker", provider_repo=repo
    )

    assert get_rerank_capability(settings.get, repo) == {
        "enabled": True,
        "provider_id": "3",
        "model": "custom-ranker",
        "ready": True,
        "usable": True,
    }


@pytest.mark.parametrize(
    ("provider", "provider_id", "model"),
    [
        (_provider(), "3", "BAAI/bge-m3"),  # an embedding model, not a reranker
        (_provider(), "3", ""),
        (_provider(), "9", "custom-ranker"),
        (_provider(enabled=False), "3", "custom-ranker"),
        (_provider(api_key=""), "3", "custom-ranker"),
    ],
)
def test_enabling_needs_a_provider_that_serves_the_model(
    provider: Any, provider_id: str, model: str
) -> None:
    settings = _Settings()
    with pytest.raises(ValueError, match="knowledge rerank"):
        set_rerank_settings(
            settings.set,
            enabled=True,
            provider_id=provider_id,
            model=model,
            provider_repo=_repo(provider),
        )
    assert settings.values == {}


def test_disabling_keeps_the_last_choice_when_none_is_sent() -> None:
    settings = _enabled_settings()
    set_rerank_settings(
        settings.set, enabled=False, provider_id=None, model=None, provider_repo=_repo(None)
    )
    assert settings.values["knowledge_rerank_enabled"] == "false"
    assert settings.values["knowledge_rerank_model"] == ""


def test_a_stored_choice_stops_being_usable_when_the_provider_goes_away() -> None:
    capability = get_rerank_capability(_enabled_settings().get, _repo(None))
    assert (capability["enabled"], capability["ready"], capability["usable"]) == (
        True,
        False,
        False,
    )


def _stub_http(monkeypatch: pytest.MonkeyPatch, payload: Any, status: int = 200) -> list[Any]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=payload)

    real_client = httpx.Client
    monkeypatch.setattr(
        rerank_module.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return requests


def _services(settings: _Settings, provider: Any | None = None) -> SimpleNamespace:
    return SimpleNamespace(settings_repo=settings, provider_repo=_repo(provider or _provider()))


def test_scores_come_back_aligned_with_the_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _stub_http(
        monkeypatch,
        {"results": [{"index": 2, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]},
    )

    scores = rerank_scores(_services(_enabled_settings()), "question", ["a", "b", "c"])

    assert scores == [0.2, float("-inf"), 0.9]
    [request] = requests
    assert str(request.url) == "https://api.example.test/v1/rerank"
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "question",
        "documents": ["a", "b", "c"],
        "top_n": 3,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"output": {"results": [{"index": 0, "relevance_score": 0.5}]}},  # DashScope
        [{"index": 0, "score": 0.5}],  # text-embeddings-inference
    ],
)
def test_other_response_shapes_are_read(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    _stub_http(monkeypatch, payload)
    assert rerank_scores(_services(_enabled_settings()), "q", ["a"]) == [0.5]


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"results": [{"index": 5, "relevance_score": 0.1}]},
        {"results": [{"index": 0, "relevance_score": "high"}]},
        {"results": ["nope"]},
    ],
)
def test_a_malformed_response_raises(monkeypatch: pytest.MonkeyPatch, payload: Any) -> None:
    _stub_http(monkeypatch, payload)
    with pytest.raises(RuntimeError, match="knowledge rerank response"):
        rerank_scores(_services(_enabled_settings()), "q", ["a"])


def test_an_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_http(monkeypatch, {"error": "bad key"}, status=401)
    with pytest.raises(httpx.HTTPStatusError):
        rerank_scores(_services(_enabled_settings()), "q", ["a"])


def test_no_request_is_made_when_rerank_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = _stub_http(monkeypatch, {"results": []})
    assert rerank_scores(_services(_Settings()), "q", ["a"]) is None
    assert rerank_scores(_services(_enabled_settings()), "q", []) is None
    assert requests == []


def _indexed_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, int, str]:
    """A base whose vector order is ``far`` < ``near`` for the query vector [1, 0]."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    services = SimpleNamespace(
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        provider_repo=_repo(_provider()),
    )
    user = services.user_repo.create(username="reader", password_hash="h", role="user")
    base = services.knowledge_repo.create_base(owner_user_id=user, name="Docs")
    document = services.knowledge_repo.create_document(
        kb_id=base.id,
        filename="facts.md",
        content_type="text/markdown",
        byte_size=1,
        status="ready",
    )
    KnowledgeIndex(base.id).replace_doc_chunks(
        document.id,
        ["looks similar", "answers the question", "unrelated"],
        [[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]],
    )
    monkeypatch.setattr(retrieve_module, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        retrieve_module, "embed_knowledge_texts", lambda _services, _texts: [[1.0, 0.0]]
    )
    return services, user, base.id


def _retrieve(services: Any, user: int, base_id: str, k: int = 1) -> str:
    return asyncio.run(
        retrieve_module.retrieve_context(
            services,
            user_id=user,
            is_admin=False,
            query="what answers the question?",
            knowledge_base_ids=[base_id],
            k=k,
        )
    )


def _enable(services: Any) -> None:
    for key, value in _enabled_settings().values.items():
        services.settings_repo.set(key, value)


def test_retrieval_keeps_the_rerankers_pick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    services, user, base_id = _indexed_services(tmp_path, monkeypatch)
    assert "looks similar" in _retrieve(services, user, base_id)

    _enable(services)
    seen: list[list[str]] = []

    def scores(_services: Any, _query: str, texts: list[str]) -> list[float]:
        seen.append(texts)
        return [0.1 if text != "answers the question" else 0.9 for text in texts]

    monkeypatch.setattr(retrieve_module, "rerank_scores", scores)

    context = _retrieve(services, user, base_id)

    # k=1, yet the reranker saw every candidate and its choice replaced the nearest vector.
    assert seen == [["looks similar", "answers the question", "unrelated"]]
    assert "answers the question" in context
    assert "looks similar" not in context


def test_retrieval_falls_back_to_vector_order_when_rerank_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    services, user, base_id = _indexed_services(tmp_path, monkeypatch)
    _enable(services)

    def boom(*_args: Any) -> list[float]:
        raise httpx.ConnectError("provider is down")

    monkeypatch.setattr(retrieve_module, "rerank_scores", boom)

    context = _retrieve(services, user, base_id)

    assert "looks similar" in context
    assert "knowledge rerank failed" in caplog.text
