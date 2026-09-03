"""Race Hugging Face and hf-mirror, then download from the winner."""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from octop.infra.agents.providers.onnx_catalog import get_onnx_model_meta

logger = logging.getLogger(__name__)

HF_ENDPOINT_OFFICIAL = "https://huggingface.co"
HF_ENDPOINT_MIRROR = "https://hf-mirror.com"

_PROBE_TIMEOUT_S = 4.0
_USER_AGENT = "octop-onnx-download"
_HF_ALLOW_PATTERNS = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "preprocessor_config.json",
    "*.onnx",
    "onnx/*.onnx",
    "onnx/*.json",
)


@dataclass(frozen=True)
class DownloadCandidate:
    """One Hugging Face endpoint that can be probed and then fetched."""

    kind: str
    probe_url: str
    hf_endpoint: str
    hf_repo: str


ProbeFn = Callable[[str, float], float]
# n bytes so far, real total if known, tqdm description.
SnapshotProgressFn = Callable[[int, int | None, str], None]


def _hf_repo_id(model_name: str) -> str:
    """Resolve the Hugging Face repo: catalog ``hf_source``, else the model id."""
    meta = get_onnx_model_meta(model_name)
    hf_repo = meta.get("hf_source")
    if not isinstance(hf_repo, str) or not hf_repo.strip():
        hf_repo = model_name
    return hf_repo.strip()


def build_download_candidates(model_name: str) -> list[DownloadCandidate]:
    """Build official HF + hf-mirror candidates; URLs are inferred from the repo id."""
    hf_repo = _hf_repo_id(model_name)
    probe_file = "config.json"
    return [
        DownloadCandidate(
            kind="hf",
            probe_url=f"{HF_ENDPOINT_OFFICIAL}/{hf_repo}/resolve/main/{probe_file}",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo=hf_repo,
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url=f"{HF_ENDPOINT_MIRROR}/{hf_repo}/resolve/main/{probe_file}",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo=hf_repo,
        ),
    ]


def probe_source(url: str, timeout_s: float = _PROBE_TIMEOUT_S) -> float:
    """Return TTFB in seconds for a 1 KiB range GET. Raises on HTTP/network errors."""
    started = time.monotonic()
    with httpx.Client(
        timeout=httpx.Timeout(timeout_s, connect=min(3.0, timeout_s)),
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = client.get(url, headers={"Range": "bytes=0-1023"})
        if response.status_code not in {200, 206}:
            response.raise_for_status()
        _ = response.content[:16]
    return time.monotonic() - started


def _first_probe_success(
    futures: dict[Future[float], DownloadCandidate],
) -> tuple[DownloadCandidate, float] | None:
    """Wait until one probe succeeds; ignore failures and keep waiting."""
    pending: set[Future[float]] = set(futures)
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        finished: list[tuple[float, DownloadCandidate]] = []
        for fut in done:
            cand = futures[fut]
            try:
                ttfb = fut.result()
            except Exception as exc:
                logger.info("ONNX source probe failed (%s): %s", cand.kind, exc)
                continue
            if ttfb < 0:
                continue
            finished.append((ttfb, cand))
        if finished:
            finished.sort(key=lambda item: item[0])
            ttfb, cand = finished[0]
            return cand, ttfb
    return None


def race_download_sources(
    candidates: list[DownloadCandidate],
    *,
    probe: ProbeFn = probe_source,
    timeout_s: float = _PROBE_TIMEOUT_S,
) -> list[DownloadCandidate]:
    """Race probes in parallel; first success wins, the rest are fallbacks.

    Losing probes are cancelled instead of being joined, so a blocked official
    source cannot stall a fast mirror. If every probe fails, catalog order
    is returned so the caller can still attempt a full download.
    """
    if not candidates:
        return []
    pool = ThreadPoolExecutor(max_workers=min(len(candidates), 2))
    try:
        futures = {pool.submit(probe, cand.probe_url, timeout_s): cand for cand in candidates}
        result = _first_probe_success(futures)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if result is None:
        logger.info("ONNX source probes all failed; falling back to catalog order")
        return list(candidates)
    winner, winner_ttfb = result
    logger.info(
        "ONNX source race winner=%s ttfb=%.3fs (n=%d)",
        winner.kind,
        winner_ttfb,
        len(candidates),
    )
    return [winner] + [c for c in candidates if c.kind != winner.kind]


def download_model_raced(
    model_name: str,
    cache_dir: Path,
    *,
    on_progress: SnapshotProgressFn | None = None,
) -> str:
    """Race sources and download *model_name* into *cache_dir*. Return winner kind."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    candidates = build_download_candidates(model_name)
    ordered = race_download_sources(candidates)
    errors: list[str] = []
    for cand in ordered:
        try:
            _download_hf_snapshot(cand, cache_dir, on_progress=on_progress)
            logger.info("ONNX model %s downloaded from %s", model_name, cand.kind)
            return cand.kind
        except Exception as exc:
            logger.warning("ONNX download via %s failed: %s", cand.kind, exc)
            errors.append(f"{cand.kind}: {exc}")
    detail = "; ".join(errors) if errors else "no sources"
    raise RuntimeError(f"All embedding download sources failed: {detail}")


def _progress_tqdm(on_progress: SnapshotProgressFn) -> type[Any] | None:
    """tqdm subclass that forwards n/total; bars themselves go to redirected stderr."""
    try:
        from tqdm.auto import tqdm as Tqdm
    except ImportError:
        return None

    class ProgressTqdm(Tqdm):  # type: ignore[misc]
        def update(self, n: float | None = 1) -> Any:
            result = super().update(n)
            desc = str(self.desc or "")
            total = int(self.total) if self.total and "reconstruct" in desc.lower() else None
            on_progress(int(self.n or 0), total, desc)
            return result

    return ProgressTqdm


_HF_HUB_DISABLE_XET = "HF_HUB_DISABLE_XET"


def _disable_hf_xet() -> None:
    """Force HTTP snapshots; Xet CAS 401s or is unreachable via hf-mirror."""
    os.environ[_HF_HUB_DISABLE_XET] = "1"
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None and hasattr(constants, _HF_HUB_DISABLE_XET):
        setattr(constants, _HF_HUB_DISABLE_XET, True)


def _download_hf_snapshot(
    cand: DownloadCandidate,
    cache_dir: Path,
    *,
    on_progress: SnapshotProgressFn | None = None,
) -> None:
    _disable_hf_xet()
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for HF model downloads") from exc
    logger.info("ONNX HF snapshot %s via %s", cand.hf_repo, cand.kind)
    tqdm_cls = _progress_tqdm(on_progress) if on_progress is not None else None
    with (
        open(os.devnull, "w", encoding="utf-8") as sink,
        redirect_stdout(sink),
        redirect_stderr(sink),
    ):
        snapshot_download(
            repo_id=cand.hf_repo,
            cache_dir=str(cache_dir),
            endpoint=cand.hf_endpoint,
            allow_patterns=list(_HF_ALLOW_PATTERNS),
            tqdm_class=tqdm_cls,
        )
