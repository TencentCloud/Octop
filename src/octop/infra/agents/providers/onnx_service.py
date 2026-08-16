"""ONNX local embedding service: config, cache, and download lifecycle.

This is **not** a chat Provider. It prepares local ONNX / fastembed embedding
models under ``~/.octop/embedding_models`` for the Models admin local tab.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from octop.infra.agents.providers.onnx_catalog import (
    ONNX_PRESET_MODEL_IDS,
    get_onnx_model_meta,
    list_onnx_catalog_models,
)
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.runtime_packages import (
    PackageInstallSpec,
    install_packages,
    purge_import_cache,
)

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "onnx_local_service"
_DEFAULT_MODEL = ONNX_PRESET_MODEL_IDS[0]
# Fixed allowlist — never take package names from user input.
_LOCAL_EMBEDDING_PIP_SPECS: tuple[str, ...] = (
    "fastembed>=0.4",
    "huggingface_hub>=0.20",
)
_LOCAL_EMBEDDING_SPEC = PackageInstallSpec(
    packages=_LOCAL_EMBEDDING_PIP_SPECS,
    extra_fallback="local-embedding",
)
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


def runtime_pip_allowed() -> bool:
    """Runtime pip is off by default; set OCTOP_ALLOW_RUNTIME_PIP=1 to enable."""
    return os.environ.get("OCTOP_ALLOW_RUNTIME_PIP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def local_embedding_deps_available() -> bool:
    """True when fastembed can be imported (preferred local embedding runtime)."""
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def _purge_failed_imports() -> None:
    purge_import_cache(("fastembed", "huggingface_hub"))


def require_local_embedding_deps() -> None:
    """Raise RuntimeError when optional local-embedding extras are missing."""
    if local_embedding_deps_available():
        return
    raise RuntimeError(
        "Local embedding components are not installed. "
        "Enable the ONNX service to install them automatically."
    )


def ensure_local_embedding_deps(*, allow_install: bool | None = None) -> str:
    """Ensure deps are importable.

    Admin ONNX actions pass ``allow_install=True``. Other callers default to
    :func:`runtime_pip_allowed`. Returns ``\"ready\"`` or ``\"installed\"``.
    """
    if local_embedding_deps_available():
        return "ready"
    if allow_install is None:
        allow_install = runtime_pip_allowed()
    if not allow_install:
        require_local_embedding_deps()
    outcome = install_packages(
        _LOCAL_EMBEDDING_SPEC,
        is_satisfied=local_embedding_deps_available,
        import_modules=("fastembed", "huggingface_hub"),
    )
    if not local_embedding_deps_available():
        raise RuntimeError(
            "Local embedding components were installed but could not be loaded. "
            "Restart the server and try again."
        )
    return outcome


async def ensure_local_embedding_deps_async(
    *,
    allow_install: bool | None = None,
) -> str:
    """Async wrapper for :func:`ensure_local_embedding_deps`."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: ensure_local_embedding_deps(allow_install=allow_install),
    )


def normalize_onnx_model_id(model_name: str) -> str:
    """Validate and normalize a model id; raises ValueError when unsafe."""
    name = model_name.strip()
    if not name or len(name) > 200:
        raise ValueError("invalid model id")
    if ".." in name or "\\" in name or name.startswith("/") or name.endswith("/"):
        raise ValueError("invalid model id")
    if not _MODEL_ID_RE.fullmatch(name):
        raise ValueError("invalid model id")
    return name


def assert_catalog_model(model_name: str) -> str:
    """Require *model_name* to be a known catalog entry."""
    name = normalize_onnx_model_id(model_name)
    catalog_ids = {str(m["id"]) for m in list_onnx_catalog_models()}
    if name not in catalog_ids:
        raise ValueError(f"model not in ONNX catalog: {name}")
    return name


class OnnxDownloadStatus(StrEnum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    LOADING = "loading"
    DONE = "done"
    FAILED = "failed"


@dataclass
class OnnxDownloadState:
    status: OnnxDownloadStatus = OnnxDownloadStatus.IDLE
    progress: float = 0.0
    error: str | None = None
    model_name: str = ""
    task_id: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "progress": self.progress,
            "error": self.error,
            "model_name": self.model_name,
            "task_id": self.task_id,
        }


@dataclass
class OnnxServiceConfig:
    enabled: bool = False
    model: str = _DEFAULT_MODEL

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "model": self.model}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> OnnxServiceConfig:
        if not raw:
            return cls()
        model = str(raw.get("model") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
        return cls(enabled=bool(raw.get("enabled")), model=model)


def embedding_models_dir() -> Path:
    path = PathLayout.from_env().root / "embedding_models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_cache_dir(model_name: str) -> Path:
    safe = "models--" + model_name.replace("/", "--")
    return embedding_models_dir() / safe


def _downloaded_marker_path(model_name: str) -> Path:
    return embedding_models_dir() / ".downloaded" / model_name.replace("/", "--")


def mark_model_downloaded(model_name: str) -> None:
    path = _downloaded_marker_path(model_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model_name, encoding="utf-8")


def _safe_under_cache(path: Path) -> Path | None:
    """Return resolved path if it stays under embedding_models_dir(), else None."""
    root = embedding_models_dir().resolve()
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if resolved == root or root in resolved.parents:
        return resolved
    return None


def _cache_has_onnx_weights(path: Path) -> bool:
    """True when *path* looks like a complete ONNX model cache (not a partial download)."""
    if not path.is_dir():
        return False
    safe = _safe_under_cache(path)
    if safe is None:
        return False
    candidates = (
        "model.onnx",
        "model_optimized.onnx",
        "onnx/model.onnx",
        "onnx/model_optimized.onnx",
    )
    for rel in candidates:
        if (safe / rel).is_file():
            return True
    snapshots = safe / "snapshots"
    if snapshots.is_dir():
        try:
            for snap in snapshots.iterdir():
                if not snap.is_dir():
                    continue
                for rel in candidates:
                    if (snap / rel).is_file():
                        return True
                if any(snap.glob("*.onnx")):
                    return True
        except OSError:
            return False
    try:
        return any(safe.glob("*.onnx"))
    except OSError:
        return False


def _alias_cache_names(model_name: str) -> list[str]:
    """HF / fastembed may store under Qdrant mirror ids, not the public model id."""
    names = [model_name]
    meta = get_onnx_model_meta(model_name)
    hf = meta.get("hf_source")
    if isinstance(hf, str) and hf.strip() and hf not in names:
        names.append(hf.strip())
    return names


def is_model_downloaded(model_name: str) -> bool:
    """True only when catalog-safe id has actual ONNX weight files on disk."""
    try:
        model_name = normalize_onnx_model_id(model_name)
    except ValueError:
        return False
    for name in _alias_cache_names(model_name):
        if _cache_has_onnx_weights(model_cache_dir(name)):
            return True
        suffix = name.split("/")[-1] if "/" in name else name
        for candidate in (
            embedding_models_dir() / suffix,
            embedding_models_dir() / f"fast-{suffix}",
        ):
            if _cache_has_onnx_weights(candidate):
                return True
    return False


def list_downloaded_models() -> list[str]:
    root = embedding_models_dir()
    found: set[str] = set()
    catalog_ids = {str(m["id"]) for m in list_onnx_catalog_models()}
    for mid in catalog_ids:
        if is_model_downloaded(mid):
            found.add(mid)
    marker_root = root / ".downloaded"
    if marker_root.is_dir():
        for child in marker_root.iterdir():
            if not child.is_file():
                continue
            try:
                mid = child.read_text(encoding="utf-8").strip()
            except OSError:
                mid = child.name.replace("--", "/", 1)
            if mid in catalog_ids and is_model_downloaded(mid):
                found.add(mid)
    return sorted(found)


def delete_downloaded_model(model_name: str) -> bool:
    name = assert_catalog_model(model_name)
    removed = False
    targets = [model_cache_dir(name), _downloaded_marker_path(name)]
    for alias in _alias_cache_names(name):
        targets.append(model_cache_dir(alias))
        suffix = alias.split("/")[-1] if "/" in alias else alias
        targets.extend(
            [
                embedding_models_dir() / suffix,
                embedding_models_dir() / f"fast-{suffix}",
            ]
        )
    for path in targets:
        safe = _safe_under_cache(path)
        if safe is None:
            continue
        if safe.is_file():
            safe.unlink(missing_ok=True)
            removed = True
        elif safe.is_dir():
            shutil.rmtree(safe, ignore_errors=True)
            removed = True
    return removed


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def load_config(settings_get: Any) -> OnnxServiceConfig:
    raw = settings_get(_SETTINGS_KEY)
    if not raw:
        return OnnxServiceConfig()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return OnnxServiceConfig()
    if not isinstance(data, dict):
        return OnnxServiceConfig()
    return OnnxServiceConfig.from_dict(data)


def embedding_prerequisites_ok_for_model(model: str) -> bool:
    if not local_embedding_deps_available():
        return False
    if not model:
        return False
    try:
        model = assert_catalog_model(model)
    except ValueError:
        return False
    return is_model_downloaded(model)


def require_embedding_prerequisites_for_model(model: str) -> str:
    require_local_embedding_deps()
    if not model:
        raise RuntimeError("ONNX embedding model is not configured or not downloaded")
    model = assert_catalog_model(model)
    if not is_model_downloaded(model):
        raise RuntimeError("ONNX embedding model is not configured or not downloaded")
    return model


def embedding_prerequisites_ok(settings_get: Any) -> bool:
    cfg = load_config(settings_get)
    return embedding_prerequisites_ok_for_model(cfg.model)


def require_embedding_prerequisites(settings_get: Any) -> OnnxServiceConfig:
    cfg = load_config(settings_get)
    require_embedding_prerequisites_for_model(cfg.model)
    return cfg


def _build_text_embedding(model: str) -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model, cache_dir=str(embedding_models_dir()))


def embed_texts(model: str, texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    require_local_embedding_deps()
    model = assert_catalog_model(model)
    emb = _build_text_embedding(model)
    out = [[float(x) for x in vec] for vec in emb.embed(list(texts))]
    if len(out) != len(texts):
        raise RuntimeError("embedding count mismatch")
    return out


def save_config(settings_set: Any, config: OnnxServiceConfig) -> OnnxServiceConfig:
    settings_set(_SETTINGS_KEY, json.dumps(config.to_dict(), ensure_ascii=False))
    return config


def status_payload(settings_get: Any, download: OnnxDownloadState) -> dict[str, Any]:
    config = load_config(settings_get)
    downloaded = is_model_downloaded(config.model) if config.model else False
    deps_ok = local_embedding_deps_available()
    return {
        "enabled": config.enabled,
        "model": config.model,
        "ready": bool(config.enabled and downloaded and deps_ok),
        "downloaded": downloaded,
        "cache_dir": str(embedding_models_dir()),
        "download": download.to_dict(),
        "local_models": list_downloaded_models(),
        "presets": list(ONNX_PRESET_MODEL_IDS),
        "deps_available": deps_ok,
    }


class OnnxDownloadManager:
    """In-process download task tracker (one active download at a time)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = OnnxDownloadState()
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> OnnxDownloadState:
        with self._lock:
            return OnnxDownloadState(
                status=self._state.status,
                progress=self._state.progress,
                error=self._state.error,
                model_name=self._state.model_name,
                task_id=self._state.task_id,
                updated_at=self._state.updated_at,
            )

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._state, key, value)
            self._state.updated_at = time.time()

    async def start_download(self, model_name: str) -> OnnxDownloadState:
        model_name = assert_catalog_model(model_name)
        await ensure_local_embedding_deps_async(allow_install=True)
        if is_model_downloaded(model_name):
            self._set(
                status=OnnxDownloadStatus.DONE,
                progress=1.0,
                error=None,
                model_name=model_name,
                task_id="",
            )
            return self.state

        task_id = uuid.uuid4().hex
        with self._lock:
            if self._state.status in {
                OnnxDownloadStatus.DOWNLOADING,
                OnnxDownloadStatus.LOADING,
            }:
                raise RuntimeError("another ONNX download is already running")
            self._state.status = OnnxDownloadStatus.DOWNLOADING
            self._state.progress = 0.05
            self._state.error = None
            self._state.model_name = model_name
            self._state.task_id = task_id
            self._state.updated_at = time.time()

        loop = asyncio.get_running_loop()

        async def _run() -> None:
            try:
                await loop.run_in_executor(None, self._download_sync, model_name)
                self._set(
                    status=OnnxDownloadStatus.DONE,
                    progress=1.0,
                    error=None,
                    model_name=model_name,
                )
            except Exception as exc:
                logger.exception("ONNX model download failed: %s", model_name)
                self._set(
                    status=OnnxDownloadStatus.FAILED,
                    progress=0.0,
                    error=str(exc),
                    model_name=model_name,
                )

        self._task = asyncio.create_task(_run())
        return self.state

    def _download_sync(self, model_name: str) -> None:
        cache = embedding_models_dir()
        meta = get_onnx_model_meta(model_name)
        size_gb = meta.get("size_gb")
        expected_bytes: int | None = None
        try:
            if size_gb is not None:
                expected_bytes = int(float(size_gb) * (1024**3))
        except (TypeError, ValueError):
            expected_bytes = None

        stop = threading.Event()
        baseline = _dir_size_bytes(cache)

        def _watch() -> None:
            while not stop.wait(0.5):
                grown = max(0, _dir_size_bytes(cache) - baseline)
                if expected_bytes and expected_bytes > 0:
                    ratio = min(0.92, 0.08 + 0.84 * (grown / expected_bytes))
                else:
                    # Unknown size: creep toward 0.85 while bytes keep growing.
                    ratio = min(0.85, 0.08 + (grown / (200 * 1024 * 1024)) * 0.7)
                self._set(status=OnnxDownloadStatus.DOWNLOADING, progress=ratio)

        watcher = threading.Thread(target=_watch, name="onnx-dl-progress", daemon=True)
        watcher.start()
        self._set(status=OnnxDownloadStatus.DOWNLOADING, progress=0.08)
        try:
            try:
                from fastembed import TextEmbedding

                self._set(
                    status=OnnxDownloadStatus.LOADING,
                    progress=max(0.15, self.state.progress),
                )
                TextEmbedding(model_name=model_name, cache_dir=str(cache))
                mark_model_downloaded(model_name)
                self._set(progress=0.95)
                return
            except ImportError:
                pass

            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise RuntimeError(
                    "Local embedding download requires optional components that "
                    "could not be loaded. Enable the ONNX service to install them "
                    "automatically."
                ) from exc

            repo_id = str(meta.get("hf_source") or model_name)
            self._set(
                status=OnnxDownloadStatus.DOWNLOADING,
                progress=max(0.12, self.state.progress),
            )
            snapshot_download(repo_id=repo_id, cache_dir=str(cache))
            mark_model_downloaded(model_name)
            self._set(progress=0.95)
        finally:
            stop.set()
            watcher.join(timeout=2.0)


DOWNLOAD_MANAGER = OnnxDownloadManager()
