"""Tests for ONNX source race + download."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from octop.infra.agents.providers.onnx_catalog import get_onnx_model_meta
from octop.infra.agents.providers.onnx_download import (
    HF_ENDPOINT_MIRROR,
    HF_ENDPOINT_OFFICIAL,
    DownloadCandidate,
    build_download_candidates,
    download_model_raced,
    race_download_sources,
)


def test_bge_small_zh_infers_hf_repo_without_fastembed(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_catalog as catalog

    monkeypatch.setattr(catalog, "_fastembed_meta_map", lambda: {})
    meta = get_onnx_model_meta("BAAI/bge-small-zh-v1.5")
    assert meta["hf_source"] == "Qdrant/bge-small-zh-v1.5"
    assert "direct_url" not in meta


def test_candidates_are_hf_and_mirror_with_inferred_urls(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_catalog as catalog

    monkeypatch.setattr(catalog, "_fastembed_meta_map", lambda: {})
    cands = build_download_candidates("BAAI/bge-small-zh-v1.5")
    assert [c.kind for c in cands] == ["hf", "hf-mirror"]
    assert cands[0].probe_url == (
        f"{HF_ENDPOINT_OFFICIAL}/Qdrant/bge-small-zh-v1.5/resolve/main/config.json"
    )
    assert cands[1].probe_url == (
        f"{HF_ENDPOINT_MIRROR}/Qdrant/bge-small-zh-v1.5/resolve/main/config.json"
    )
    assert cands[0].hf_endpoint == HF_ENDPOINT_OFFICIAL
    assert cands[1].hf_endpoint == HF_ENDPOINT_MIRROR


def test_unknown_model_uses_model_id_as_hf_repo(monkeypatch) -> None:
    from octop.infra.agents.providers import onnx_catalog as catalog

    monkeypatch.setattr(catalog, "_fastembed_meta_map", lambda: {})
    cands = build_download_candidates("jinaai/jina-embeddings-v2-base-zh")
    assert [c.kind for c in cands] == ["hf", "hf-mirror"]
    assert cands[0].hf_repo == "jinaai/jina-embeddings-v2-base-zh"
    assert cands[0].probe_url.startswith(
        f"{HF_ENDPOINT_OFFICIAL}/jinaai/jina-embeddings-v2-base-zh/"
    )
    assert cands[1].probe_url.startswith(f"{HF_ENDPOINT_MIRROR}/jinaai/jina-embeddings-v2-base-zh/")


def test_race_orders_by_ttfb_and_skips_failures() -> None:
    cands = [
        DownloadCandidate(
            kind="hf",
            probe_url="http://hf",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo="org/model",
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="org/model",
        ),
    ]

    def probe(url: str, timeout_s: float) -> float:
        if url.endswith("hf"):
            raise TimeoutError("official blocked")
        return 0.12

    ranked = race_download_sources(cands, probe=probe)
    assert [c.kind for c in ranked] == ["hf-mirror", "hf"]


def test_race_returns_before_slow_probe_finishes() -> None:
    cands = [
        DownloadCandidate(
            kind="hf",
            probe_url="http://hf",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo="org/model",
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="org/model",
        ),
    ]
    release = threading.Event()

    def probe(url: str, _timeout_s: float) -> float:
        if url.endswith("hf"):
            release.wait(timeout=5)
            return 5.0
        return 0.05

    started = time.monotonic()
    try:
        ranked = race_download_sources(cands, probe=probe)
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert [c.kind for c in ranked] == ["hf-mirror", "hf"]
    assert elapsed < 0.5


def test_race_keeps_catalog_order_when_all_probes_fail() -> None:
    cands = [
        DownloadCandidate(
            kind="hf",
            probe_url="http://hf",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo="org/model",
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="org/model",
        ),
    ]

    def probe(_url: str, _timeout_s: float) -> float:
        raise OSError("offline")

    ranked = race_download_sources(cands, probe=probe)
    assert [c.kind for c in ranked] == ["hf", "hf-mirror"]


def test_download_uses_winner_then_falls_back(monkeypatch, tmp_path: Path) -> None:
    from octop.infra.agents.providers import onnx_download as mod

    cands = [
        DownloadCandidate(
            kind="hf",
            probe_url="http://hf",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo="Qdrant/bge-small-zh-v1.5",
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="Qdrant/bge-small-zh-v1.5",
        ),
    ]
    tried: list[str] = []

    monkeypatch.setattr(mod, "build_download_candidates", lambda _name: cands)
    monkeypatch.setattr(mod, "race_download_sources", lambda items, **_kw: items)

    def fake_download(cand: DownloadCandidate, cache_dir: Path, **_kwargs: object) -> None:
        tried.append(cand.kind)
        if cand.kind == "hf":
            raise RuntimeError("hf 403")

    monkeypatch.setattr(mod, "_download_hf_snapshot", fake_download)
    winner = download_model_raced("BAAI/bge-small-zh-v1.5", tmp_path)
    assert winner == "hf-mirror"
    assert tried == ["hf", "hf-mirror"]


def test_hf_snapshot_emits_tqdm_byte_progress(monkeypatch, tmp_path: Path) -> None:
    import types

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    seen: list[tuple[int, int | None, str]] = []

    def fake_snapshot_download(**kwargs: object) -> str:
        tqdm_class = kwargs.get("tqdm_class")
        assert callable(tqdm_class)
        transfer = tqdm_class(total=1_000_000, desc="Downloading bytes", unit="B")
        transfer.update(400_000)
        reconstruct = tqdm_class(total=800_000, desc="Reconstructing", unit="B")
        reconstruct.update(800_000)
        return "ok"

    hub = sys.modules.get("huggingface_hub")
    if hub is None:
        hub = types.ModuleType("huggingface_hub")
        monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setattr(hub, "snapshot_download", fake_snapshot_download, raising=False)

    from octop.infra.agents.providers.onnx_download import _download_hf_snapshot

    _download_hf_snapshot(
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="Qdrant/bge-small-zh-v1.5",
        ),
        tmp_path / "cache",
        on_progress=lambda n, total, desc: seen.append((n, total, desc)),
    )

    assert (400_000, None, "Downloading bytes") in seen
    assert (800_000, 800_000, "Reconstructing") in seen


def test_snapshot_disables_xet_before_hub_import(monkeypatch, tmp_path: Path) -> None:
    import types

    from octop.infra.agents.providers import onnx_download as mod

    seen: dict[str, object] = {}
    constants = types.ModuleType("huggingface_hub.constants")
    constants.HF_HUB_DISABLE_XET = False
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    def fake_snapshot_download(**kwargs: object) -> str:
        seen["env"] = os.environ.get("HF_HUB_DISABLE_XET")
        seen["const"] = constants.HF_HUB_DISABLE_XET
        seen["endpoint"] = kwargs.get("endpoint")
        return "ok"

    hub = types.ModuleType("huggingface_hub")
    hub.snapshot_download = fake_snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    mod._download_hf_snapshot(
        DownloadCandidate(
            kind="hf-mirror",
            probe_url="http://mirror",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo="Qdrant/bge-small-zh-v1.5",
        ),
        tmp_path / "cache",
    )

    assert seen["env"] == "1"
    assert seen["const"] is True
    assert seen["endpoint"] == HF_ENDPOINT_MIRROR
