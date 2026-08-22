"""Tests for local ONNX embedding service helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from octop.infra.agents.providers.onnx_catalog import (
    ONNX_PRESET_MODEL_IDS,
    get_onnx_model_meta,
    list_onnx_catalog_models,
)
from octop.infra.agents.providers.onnx_service import (
    OnnxDownloadState,
    OnnxServiceConfig,
    embedding_models_dir,
    is_model_downloaded,
    load_config,
    local_embedding_deps_available,
    save_config,
    status_payload,
)


def test_catalog_includes_finnie_presets() -> None:
    ids = [m["id"] for m in list_onnx_catalog_models()]
    for mid in ONNX_PRESET_MODEL_IDS:
        assert mid in ids
    recommended = {m["id"] for m in list_onnx_catalog_models() if m.get("recommended")}
    assert set(ONNX_PRESET_MODEL_IDS) <= recommended


def test_catalog_models_have_approximate_sizes() -> None:
    for model_id in (
        *ONNX_PRESET_MODEL_IDS,
        "thenlper/gte-base",
        "thenlper/gte-large",
        "jinaai/jina-embeddings-v2-base-en",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ):
        size = get_onnx_model_meta(model_id).get("size_gb")
        assert size is not None, model_id
        assert float(size) > 0


def test_config_roundtrip_via_settings_dict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    store: dict[str, str] = {}

    def getter(key: str) -> str | None:
        return store.get(key)

    def setter(key: str, value: str) -> None:
        store[key] = value

    cfg = OnnxServiceConfig(enabled=True, model=ONNX_PRESET_MODEL_IDS[1])
    save_config(setter, cfg)
    loaded = load_config(getter)
    assert loaded.enabled is True
    assert loaded.model == ONNX_PRESET_MODEL_IDS[1]
    assert json.loads(store["onnx_local_service"])["model"] == ONNX_PRESET_MODEL_IDS[1]

    payload = status_payload(getter, OnnxDownloadState())
    assert payload["enabled"] is True
    assert payload["ready"] is False
    assert "deps_available" in payload
    assert payload["deps_available"] is local_embedding_deps_available()
    assert embedding_models_dir() == tmp_path / "embedding_models"
    assert is_model_downloaded("no/such-model") is False


def test_ensure_deps_noop_when_available(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)

    def boom(*_args, **_kwargs) -> str:
        raise AssertionError("should not install packages")

    monkeypatch.setattr(mod, "install_packages", boom)
    assert mod.ensure_local_embedding_deps() == "ready"


def test_ensure_deps_refuses_install_by_default(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.delenv("OCTOP_ALLOW_RUNTIME_PIP", raising=False)
    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: False)
    with pytest.raises(RuntimeError, match="Enable the ONNX service"):
        mod.ensure_local_embedding_deps()


def test_ensure_deps_installs_when_env_allows(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.setenv("OCTOP_ALLOW_RUNTIME_PIP", "1")
    state = {"ok": False}

    def available() -> bool:
        return state["ok"]

    def fake_install(*_args, **_kwargs) -> str:
        state["ok"] = True
        return "installed"

    monkeypatch.setattr(mod, "local_embedding_deps_available", available)
    monkeypatch.setattr(mod, "install_packages", fake_install)
    assert mod.ensure_local_embedding_deps() == "installed"
    assert state["ok"] is True


def test_ensure_deps_installs_when_allow_install_true(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.delenv("OCTOP_ALLOW_RUNTIME_PIP", raising=False)
    state = {"ok": False}

    def available() -> bool:
        return state["ok"]

    def fake_install(*_args, **_kwargs) -> str:
        state["ok"] = True
        return "installed"

    monkeypatch.setattr(mod, "local_embedding_deps_available", available)
    monkeypatch.setattr(mod, "install_packages", fake_install)
    assert mod.ensure_local_embedding_deps(allow_install=True) == "installed"
    assert state["ok"] is True


def test_status_payload_omits_install_commands(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    store: dict[str, str] = {}

    payload = status_payload(store.get, OnnxDownloadState())
    assert "deps_install_hint" not in payload


def test_assert_catalog_rejects_unknown_and_path_tricks() -> None:
    from octop.infra.agents.providers import onnx_service as mod

    with pytest.raises(ValueError, match="catalog"):
        mod.assert_catalog_model("evil/not-in-catalog")
    with pytest.raises(ValueError, match="invalid"):
        mod.assert_catalog_model("../etc/passwd")
    with pytest.raises(ValueError, match="invalid"):
        mod.assert_catalog_model("/abs/path")
    assert mod.assert_catalog_model(ONNX_PRESET_MODEL_IDS[0]) == ONNX_PRESET_MODEL_IDS[0]


def test_partial_cache_without_onnx_is_not_downloaded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.agents.providers import onnx_service as mod

    mid = ONNX_PRESET_MODEL_IDS[0]
    partial = mod.model_cache_dir(mid)
    partial.mkdir(parents=True)
    (partial / "config.json").write_text("{}", encoding="utf-8")
    mod.mark_model_downloaded(mid)
    assert mod.is_model_downloaded(mid) is False


def test_is_downloaded_recognizes_fastembed_hf_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.agents.providers import onnx_catalog as catalog
    from octop.infra.agents.providers import onnx_service as mod

    # CI often lacks the optional local-embedding extra; alias detection must
    # still work via static HF source fallbacks.
    monkeypatch.setattr(catalog, "_fastembed_meta_map", lambda: {})

    cache = mod.embedding_models_dir()
    alias = cache / "models--Qdrant--bge-small-zh-v1.5" / "snapshots" / "abc"
    alias.mkdir(parents=True)
    (alias / "model.onnx").write_bytes(b"x")
    assert mod.is_model_downloaded("BAAI/bge-small-zh-v1.5") is True
    assert "BAAI/bge-small-zh-v1.5" in mod.list_downloaded_models()


def test_embedding_prerequisites_ignore_service_enabled(tmp_path, monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    store: dict[str, str] = {}
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(mod, "is_model_downloaded", lambda _m: True)
    mod.save_config(
        store.__setitem__,
        mod.OnnxServiceConfig(enabled=False, model=mod._DEFAULT_MODEL),
    )
    assert mod.embedding_prerequisites_ok(store.get) is True


def test_embed_texts_returns_vectors(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    class FakeEmb:
        def embed(self, texts):
            for _ in texts:
                yield [0.1, 0.2, 0.3]

    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(mod, "_build_text_embedding", lambda _model: FakeEmb())
    vectors = mod.embed_texts("BAAI/bge-small-zh-v1.5", ["hello"])
    assert len(vectors) == 1 and len(vectors[0]) == 3


def test_embed_texts_empty_input(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    called = {"n": 0}

    def boom(_model: str) -> None:
        called["n"] += 1
        raise AssertionError("should not build embedding for empty input")

    monkeypatch.setattr(mod, "_build_text_embedding", boom)
    assert mod.embed_texts("BAAI/bge-small-zh-v1.5", []) == []
    assert called["n"] == 0


def test_embedding_prerequisites_ok_for_model(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(
        mod,
        "is_model_downloaded",
        lambda m: m == "BAAI/bge-small-zh-v1.5",
    )
    assert mod.embedding_prerequisites_ok_for_model("BAAI/bge-small-zh-v1.5") is True
    assert mod.embedding_prerequisites_ok_for_model("BAAI/bge-small-en-v1.5") is False


def test_require_embedding_prerequisites_for_model(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(mod, "is_model_downloaded", lambda _m: True)
    assert (
        mod.require_embedding_prerequisites_for_model("BAAI/bge-small-zh-v1.5")
        == "BAAI/bge-small-zh-v1.5"
    )


def test_require_embedding_prerequisites_for_model_raises(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_service as mod

    monkeypatch.setattr(mod, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(mod, "is_model_downloaded", lambda _m: False)
    with pytest.raises(RuntimeError, match="not configured or not downloaded"):
        mod.require_embedding_prerequisites_for_model("BAAI/bge-small-zh-v1.5")


def test_delete_stays_under_cache_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.agents.providers import onnx_service as mod

    mid = ONNX_PRESET_MODEL_IDS[0]
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    # Symlink attack: cache entry pointing outside should not delete outside.
    cache_entry = mod.model_cache_dir(mid)
    cache_entry.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache_entry.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    mod.delete_downloaded_model(mid)
    assert outside.is_file()
    assert outside.read_text(encoding="utf-8") == "secret"


def test_is_downloaded_finds_nested_onnx_weights(tmp_path, monkeypatch) -> None:
    """Regression: weights under ``onnx/`` with a non-``model.onnx`` name.

    ``jinaai/jina-clip-v1`` ships ``onnx/text_model.onnx`` /
    ``onnx/vision_model.onnx``. Fixed-name matching missed both, so the model
    downloaded fine but every enable attempt reported it as missing.
    """
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.agents.providers import onnx_service as mod

    mid = "jinaai/jina-clip-v1"
    snap = mod.model_cache_dir(mid) / "snapshots" / "abc123"
    (snap / "onnx").mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    for name in ("text_model.onnx", "vision_model.onnx"):
        (snap / "onnx" / name).write_bytes(b"onnx")

    assert mod.is_model_downloaded(mid) is True
    assert mid in mod.list_downloaded_models()


def test_is_downloaded_ignores_dangling_snapshot_symlink(tmp_path, monkeypatch) -> None:
    """A snapshot entry whose blob is still downloading must not count."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.agents.providers import onnx_service as mod

    mid = ONNX_PRESET_MODEL_IDS[0]
    root = mod.model_cache_dir(mid)
    snap = root / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (root / "blobs").mkdir(parents=True)
    try:
        (snap / "model.onnx").symlink_to(root / "blobs" / "not-fetched-yet")
    except OSError:
        pytest.skip("symlinks unavailable")

    assert mod.is_model_downloaded(mid) is False

    (root / "blobs" / "not-fetched-yet").write_bytes(b"onnx")
    assert mod.is_model_downloaded(mid) is True


def test_fallback_catalog_ids_stay_loadable_by_fastembed() -> None:
    """The deps-missing catalog must be a subset of what fastembed can load.

    Otherwise a user picks a model while the extra is absent, the click
    installs fastembed, and the id disappears from the catalog mid-flow.
    """
    from octop.infra.agents.providers import onnx_catalog as catalog

    meta_map = catalog._fastembed_meta_map()
    if not meta_map:
        pytest.skip("fastembed not installed")

    fallback_ids = {*ONNX_PRESET_MODEL_IDS, *catalog._EXTRA_CATALOG_IDS}
    unsupported = sorted(fallback_ids - set(meta_map))
    assert not unsupported, f"catalog offers models fastembed cannot load: {unsupported}"


async def test_provider_probe_never_leaves_the_host_for_local_onnx(monkeypatch) -> None:
    """Regression: probing ``ONNX (Local)`` POSTed its placeholder key to OpenAI.

    The row is stored as ``kind=openai`` with ``api_key="onnx"`` and no base
    URL, so the generic embedding probe fell back to api.openai.com and got
    ``Incorrect API key provided: onnx``.
    """
    import httpx

    from octop.infra.agents.providers import onnx_service, probe

    def no_network(*_args, **_kwargs):
        raise AssertionError("local ONNX probe must not open a network client")

    monkeypatch.setattr(httpx, "AsyncClient", no_network)

    async def fake_probe(model: str) -> dict[str, object]:
        return {"ok": True, "latency_ms": 12.7, "dim": 512, "model": model}

    monkeypatch.setattr(onnx_service, "probe_local_model", fake_probe)

    row = SimpleNamespace(
        name="ONNX (Local)",
        api_key="onnx",
        base_url=None,
        kind="openai",
        extra_json=None,
        get_models=lambda: [
            {"id": "BAAI/bge-small-zh-v1.5", "enabled": False, "embedding": True},
            {"id": "jinaai/jina-embeddings-v2-base-zh", "enabled": True, "embedding": True},
        ],
    )

    result = await probe.probe_provider_row(row)
    assert result["ok"] is True
    assert result["latency_ms"] == 12
    # The enabled entry wins over models[0].
    assert result["model"] == "jinaai/jina-embeddings-v2-base-zh"

    # ModelListEditor's per-model test link sends {model_id, embedding: true};
    # the local guard must win over the explicit embedding flag.
    explicit = await probe.probe_provider_row(
        row, model_id="BAAI/bge-small-zh-v1.5", embedding=True
    )
    assert explicit["ok"] is True
    assert explicit["model"] == "BAAI/bge-small-zh-v1.5"
