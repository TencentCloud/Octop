"""Unit tests for knowledge advanced indexing/retrieval settings."""

from __future__ import annotations

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.knowledge import params


def test_advanced_settings_use_defaults_when_unset() -> None:
    assert params.get_advanced_settings(lambda _key: None) == {
        "chunk_size": params.DEFAULT_CHUNK_SIZE,
        "chunk_overlap": params.DEFAULT_CHUNK_OVERLAP,
        "retrieval_k": params.DEFAULT_RETRIEVAL_K,
        "context_char_budget": params.DEFAULT_CONTEXT_CHAR_BUDGET,
    }


def test_advanced_settings_persist_and_reject_invalid_overlap() -> None:
    values: dict[str, str] = {}

    params.set_advanced_settings(
        values.get,
        values.__setitem__,
        chunk_size=1000,
        chunk_overlap=200,
        retrieval_k=5,
        context_char_budget=4000,
    )
    assert params.get_advanced_settings(values.get) == {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "retrieval_k": 5,
        "context_char_budget": 4000,
    }

    with pytest.raises(ValueError, match="chunk_overlap"):
        params.set_advanced_settings(
            values.get, values.__setitem__, chunk_size=100, chunk_overlap=100
        )


def test_capability_includes_advanced_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.knowledge import gate

    monkeypatch.setattr(gate, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(gate, "is_model_downloaded", lambda _model: False)

    capability = gate.get_capability(lambda _key: None)

    assert capability["chunk_size"] == params.DEFAULT_CHUNK_SIZE
    assert capability["chunk_overlap"] == params.DEFAULT_CHUNK_OVERLAP
    assert capability["retrieval_k"] == params.DEFAULT_RETRIEVAL_K
    assert capability["context_char_budget"] == params.DEFAULT_CONTEXT_CHAR_BUDGET


def test_retrieval_defaults_read_both_values_from_one_snapshot(tmp_path) -> None:
    pool = SqlitePool(tmp_path / "snapshot.db")
    k = "knowledge_retrieval_k"
    budget = "knowledge_context_char_budget"
    try:
        run_migrations(pool)
        repo = SettingsRepo(pool)
        repo.set_many({k: "8", budget: "6000"})

        def snapshot_before_save(keys):
            values = repo.get_many(keys)
            repo.set_many({k: "12", budget: "10500"})
            return values

        first = params.get_advanced_settings(repo.get, settings_get_many=snapshot_before_save)
        next_settings = params.get_advanced_settings(repo.get, settings_get_many=repo.get_many)
        assert (first["retrieval_k"], first["context_char_budget"]) == (8, 6000)
        assert (next_settings["retrieval_k"], next_settings["context_char_budget"]) == (12, 10500)
    finally:
        pool.close()
