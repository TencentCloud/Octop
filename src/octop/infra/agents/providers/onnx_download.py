"""Race COS, Hugging Face, and hf-mirror, then download from the winner."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
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
# Same public bucket that hosts install.sh; objects live under /models/embedding/.
COS_ENDPOINT_DEFAULT = "https://octop-1258344699.cos.ap-guangzhou.myqcloud.com"
COS_PREFIX = "models/embedding"
COS_MANIFEST_NAME = "files.json"
COS_REVISION = "cos-mirror"
_COS_BASE_ENV = "OCTOP_ONNX_COS_BASE"

_PROBE_TIMEOUT_S = 4.0
_USER_AGENT = "octop-onnx-download"
_HF_ALLOW_PATTERNS = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "preprocessor_config.json",
    "vocab.txt",
    "vocab.json",
    "merges.txt",
    "sentencepiece.bpe.model",
    "*.onnx",
    "*.onnx_data",
    "onnx/*.onnx",
    "onnx/*.onnx_data",
    "onnx/*.json",
)
# Extra ONNX variants in upstream repos; COS trees keep the primary weights only.
_COS_SKIP_ONNX_NAMES = frozenset({"model_fp16.onnx", "model_quantized.onnx", "model_int8.onnx"})


@dataclass(frozen=True)
class DownloadCandidate:
    """One endpoint that can be probed and then fetched."""

    kind: str
    probe_url: str
    hf_endpoint: str
    hf_repo: str
    model_name: str = ""


ProbeFn = Callable[[str, float], float]
# n bytes so far, real total if known, tqdm description.
SnapshotProgressFn = Callable[[int, int | None, str], None]


def _hf_repo_id(model_name: str) -> str:
    """Resolve the Hugging Face repo: catalog ``hf_source``, else the model id."""
    meta = get_onnx_model_meta(model_name)
    hf_source = meta.get("hf_source")
    if not isinstance(hf_source, str) or not hf_source.strip():
        return model_name.strip()
    return hf_source.strip()


def cos_base_url() -> str:
    """Public COS origin; override with ``OCTOP_ONNX_COS_BASE`` for a private bucket."""
    return os.environ.get(_COS_BASE_ENV, COS_ENDPOINT_DEFAULT).rstrip("/")


def cos_object_key(model_name: str, rel_path: str = "") -> str:
    """Return the COS object key under ``/models/embedding/{model_id}/``."""
    prefix = f"{COS_PREFIX}/{model_name.strip().strip('/')}"
    rel = rel_path.replace("\\", "/").lstrip("/")
    return f"{prefix}/{rel}" if rel else prefix


def cos_file_url(model_name: str, rel_path: str) -> str:
    """HTTPS URL for one COS object in the embedding tree."""
    return f"{cos_base_url()}/{cos_object_key(model_name, rel_path)}"


def cos_local_model_dir(dest_root: Path, model_name: str) -> Path:
    """Local directory that mirrors ``/models/embedding/{model_id}/``."""
    return dest_root / COS_PREFIX / model_name.strip().strip("/")


def build_download_candidates(model_name: str) -> list[DownloadCandidate]:
    """Build COS + official HF + hf-mirror candidates."""
    hf_repo = _hf_repo_id(model_name)
    probe_file = "config.json"
    return [
        DownloadCandidate(
            kind="cos",
            probe_url=cos_file_url(model_name, probe_file),
            hf_endpoint="",
            hf_repo=hf_repo,
            model_name=model_name,
        ),
        DownloadCandidate(
            kind="hf",
            probe_url=f"{HF_ENDPOINT_OFFICIAL}/{hf_repo}/resolve/main/{probe_file}",
            hf_endpoint=HF_ENDPOINT_OFFICIAL,
            hf_repo=hf_repo,
            model_name=model_name,
        ),
        DownloadCandidate(
            kind="hf-mirror",
            probe_url=f"{HF_ENDPOINT_MIRROR}/{hf_repo}/resolve/main/{probe_file}",
            hf_endpoint=HF_ENDPOINT_MIRROR,
            hf_repo=hf_repo,
            model_name=model_name,
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
    pool = ThreadPoolExecutor(max_workers=min(len(candidates), 3))
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
            _download_candidate(cand, cache_dir, on_progress=on_progress)
            logger.info("ONNX model %s downloaded from %s", model_name, cand.kind)
            return cand.kind
        except Exception as exc:
            logger.warning("ONNX download via %s failed: %s", cand.kind, exc)
            errors.append(f"{cand.kind}: {exc}")
    detail = "; ".join(errors) if errors else "no sources"
    raise RuntimeError(f"All embedding download sources failed: {detail}")


def _download_candidate(
    cand: DownloadCandidate,
    cache_dir: Path,
    *,
    on_progress: SnapshotProgressFn | None = None,
) -> None:
    if cand.kind == "cos":
        _download_cos_snapshot(cand, cache_dir, on_progress=on_progress)
        return
    _download_hf_snapshot(cand, cache_dir, on_progress=on_progress)


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


def _safe_rel_path(raw: str) -> str:
    """Reject empty, absolute, or parent-escaping object paths."""
    rel = raw.replace("\\", "/").strip().lstrip("/")
    if not rel or rel.startswith("../") or "/../" in f"/{rel}/" or rel == "..":
        raise ValueError(f"unsafe COS object path: {raw!r}")
    return rel


def _manifest_files(payload: object) -> list[str]:
    raw_files: object
    if isinstance(payload, list):
        raw_files = payload
    elif isinstance(payload, dict):
        raw_files = payload.get("files")
    else:
        raise ValueError("COS manifest must be an object or a file list")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("COS manifest has no files")
    files: list[str] = []
    for item in raw_files:
        if isinstance(item, str):
            files.append(_safe_rel_path(item))
            continue
        if isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str) and path.strip():
                files.append(_safe_rel_path(path))
                continue
        raise ValueError(f"invalid COS manifest entry: {item!r}")
    return files


def write_cos_manifest(model_dir: Path, *, model_id: str, hf_repo: str) -> Path:
    """Write ``files.json`` listing every file under *model_dir* except the manifest."""
    files = sorted(
        path.relative_to(model_dir).as_posix()
        for path in model_dir.rglob("*")
        if path.is_file() and path.name != COS_MANIFEST_NAME
    )
    payload = {"model_id": model_id, "hf_repo": hf_repo, "files": files}
    dest = model_dir / COS_MANIFEST_NAME
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def hf_cache_snapshot_dir(cache_dir: Path, hf_repo: str, *, revision: str = COS_REVISION) -> Path:
    """Create a Hugging Face cache snapshot that ``huggingface_hub`` will reuse."""
    repo_dir = cache_dir / ("models--" + hf_repo.replace("/", "--"))
    refs = repo_dir / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(revision + "\n", encoding="utf-8")
    dest = repo_dir / "snapshots" / revision
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _download_http_file(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    on_progress: SnapshotProgressFn | None,
    downloaded_so_far: int,
    total: int | None,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    written = 0
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes(64 * 1024):
                handle.write(chunk)
                written += len(chunk)
                if on_progress is not None:
                    on_progress(downloaded_so_far + written, total, dest.name)
    tmp.replace(dest)
    return written


def _download_cos_snapshot(
    cand: DownloadCandidate,
    cache_dir: Path,
    *,
    on_progress: SnapshotProgressFn | None = None,
) -> None:
    model_name = cand.model_name or cand.hf_repo
    if not model_name:
        raise RuntimeError("COS download is missing a model id")
    logger.info("ONNX COS snapshot %s via %s", model_name, cand.kind)
    timeout = httpx.Timeout(120.0, connect=10.0)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        manifest = client.get(cos_file_url(model_name, COS_MANIFEST_NAME))
        manifest.raise_for_status()
        files = _manifest_files(manifest.json())
        dest = hf_cache_snapshot_dir(cache_dir, cand.hf_repo or model_name)
        downloaded = 0
        for rel in files:
            written = _download_http_file(
                client,
                cos_file_url(model_name, rel),
                dest / rel,
                on_progress=on_progress,
                downloaded_so_far=downloaded,
                total=None,
            )
            downloaded += written
    if not any(dest.rglob("*.onnx")):
        raise RuntimeError(f"COS snapshot for {model_name} has no ONNX weights")


def export_model_tree_for_cos(
    model_name: str,
    dest_root: Path,
    *,
    hf_endpoint: str = HF_ENDPOINT_MIRROR,
    on_progress: SnapshotProgressFn | None = None,
) -> Path:
    """Download *model_name* and write the COS object tree under *dest_root*.

    Layout: ``{dest_root}/models/embedding/{model_id}/…`` plus ``files.json``.
    """
    _disable_hf_xet()
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required to stage COS model trees") from exc
    hf_repo = _hf_repo_id(model_name)
    dest = cos_local_model_dir(dest_root, model_name)
    tqdm_cls = _progress_tqdm(on_progress) if on_progress is not None else None
    with tempfile.TemporaryDirectory(prefix="octop-onnx-cos-") as tmp:
        snapshot = Path(
            snapshot_download(
                repo_id=hf_repo,
                cache_dir=tmp,
                endpoint=hf_endpoint,
                allow_patterns=list(_HF_ALLOW_PATTERNS),
                ignore_patterns=[f"**/{name}" for name in _COS_SKIP_ONNX_NAMES],
                tqdm_class=tqdm_cls,
            )
        )
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for path in snapshot.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(snapshot)
            if rel.as_posix().startswith("."):
                continue
            if path.name in _COS_SKIP_ONNX_NAMES:
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    write_cos_manifest(dest, model_id=model_name, hf_repo=hf_repo)
    logger.info("Staged COS tree for %s at %s", model_name, dest)
    return dest
