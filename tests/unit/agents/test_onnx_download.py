"""Tests for ONNX source race + download."""

from __future__ import annotations

import sys
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
from octop.infra.utils.paths import PathLayout


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
    assert [c.kind for c in ranked] == ["hf-mirror"]


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

    def fake_download(cand: DownloadCandidate, cache_dir: Path) -> None:
        tried.append(cand.kind)
        if cand.kind == "hf":
            raise RuntimeError("hf 403")

    monkeypatch.setattr(mod, "_download_hf_snapshot", fake_download)
    winner = download_model_raced("BAAI/bge-small-zh-v1.5", tmp_path)
    assert winner == "hf-mirror"
    assert tried == ["hf", "hf-mirror"]


def test_hf_snapshot_progress_goes_to_log_not_stdout(monkeypatch, tmp_path: Path, capsys) -> None:
    import types

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))

    def fake_snapshot_download(**_kwargs: object) -> str:
        print("Downloading bytes: fake-progress", flush=True)
        print("Warning: unauthenticated requests", file=sys.stderr, flush=True)
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
    )

    captured = capsys.readouterr()
    assert "fake-progress" not in captured.out
    assert "unauthenticated" not in captured.err

    log_path = PathLayout.from_env().log
    assert log_path == tmp_path / "logs" / "octop.log"
    text = log_path.read_text(encoding="utf-8")
    assert "hf-mirror Qdrant/bge-small-zh-v1.5" in text
    assert "Downloading bytes: fake-progress" in text
    assert "Warning: unauthenticated requests" in text
