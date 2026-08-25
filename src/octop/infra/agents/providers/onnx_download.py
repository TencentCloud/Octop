"""Race Hugging Face and hf-mirror, then download from the winner."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import httpx

from octop.infra.agents.providers.onnx_catalog import get_onnx_model_meta
from octop.infra.utils.paths import PathLayout

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


def race_download_sources(
    candidates: list[DownloadCandidate],
    *,
    probe: ProbeFn = probe_source,
    timeout_s: float = _PROBE_TIMEOUT_S,
) -> list[DownloadCandidate]:
    """Probe candidates in parallel and return them fastest-first.

    Failed probes are omitted. If every probe fails, the original candidate
    order is returned so the caller can still attempt a full download.
    """
    if not candidates:
        return []
    ranked: list[tuple[float, DownloadCandidate]] = []
    workers = min(len(candidates), 2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe, cand.probe_url, timeout_s): cand for cand in candidates}
        for fut in as_completed(futures):
            cand = futures[fut]
            try:
                ttfb = fut.result()
            except Exception as exc:
                logger.info("ONNX source probe failed (%s): %s", cand.kind, exc)
                continue
            if ttfb < 0:
                continue
            ranked.append((ttfb, cand))
    ranked.sort(key=lambda item: item[0])
    if not ranked:
        logger.info("ONNX source probes all failed; falling back to catalog order")
        return list(candidates)
    winner = ranked[0][1]
    logger.info(
        "ONNX source race winner=%s ttfb=%.3fs (n=%d)",
        winner.kind,
        ranked[0][0],
        len(ranked),
    )
    return [item[1] for item in ranked]


def download_model_raced(model_name: str, cache_dir: Path) -> str:
    """Race sources and download *model_name* into *cache_dir*. Return winner kind."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    candidates = build_download_candidates(model_name)
    ordered = race_download_sources(candidates)
    errors: list[str] = []
    for cand in ordered:
        try:
            _download_hf_snapshot(cand, cache_dir)
            logger.info("ONNX model %s downloaded from %s", model_name, cand.kind)
            return cand.kind
        except Exception as exc:
            logger.warning("ONNX download via %s failed: %s", cand.kind, exc)
            errors.append(f"{cand.kind}: {exc}")
    detail = "; ".join(errors) if errors else "no sources"
    raise RuntimeError(f"All embedding download sources failed: {detail}")


def _tqdm_to_log(log_file: TextIO) -> type[Any] | None:
    """Build a tqdm subclass that writes progress bars into *log_file*."""
    try:
        from tqdm.auto import tqdm as Tqdm
    except ImportError:
        return None

    class LogTqdm(Tqdm):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["file"] = log_file
            kwargs["disable"] = False
            kwargs.setdefault("mininterval", 1.0)
            super().__init__(*args, **kwargs)

    return LogTqdm


def _download_hf_snapshot(cand: DownloadCandidate, cache_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for HF model downloads") from exc
    log_path = PathLayout.from_env().ensure_log()
    logger.info(
        "ONNX HF snapshot %s via %s (progress log: %s)",
        cand.hf_repo,
        cand.kind,
        log_path,
    )
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {cand.kind} {cand.hf_repo} ===\n"
        )
        log_file.flush()
        # tqdm + hf_xet warnings write stdout/stderr directly; keep them off the
        # server console and append into ~/.octop/logs/octop.log instead.
        with redirect_stdout(log_file), redirect_stderr(log_file):
            snapshot_download(
                repo_id=cand.hf_repo,
                cache_dir=str(cache_dir),
                endpoint=cand.hf_endpoint,
                allow_patterns=list(_HF_ALLOW_PATTERNS),
                tqdm_class=_tqdm_to_log(log_file),
            )
