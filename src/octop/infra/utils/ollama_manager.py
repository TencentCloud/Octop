from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_OLLAMA_SERVER_STARTED = False
SETTINGS_KEY_MODELS_DIR = "ollama_models_dir"

_UNSET = object()
_original_ollama_models: object = _UNSET
_applied_models_dir: str | None = None

_DEFAULT_REGISTRY = "registry.ollama.ai"
_DEFAULT_NAMESPACE = "library"


class OllamaModelInfo(BaseModel):
    """Metadata for a single Ollama model returned by ``ollama.list()``."""

    name: str = Field(..., description="Model name, e.g. 'llama3:8b'")
    size: int = Field(0, description="Approximate size in bytes (if provided)")
    digest: str | None = Field(default=None, description="Model digest/id")
    modified_at: str | None = Field(
        default=None,
        description="Last modified time string (from Ollama, if present)",
    )

    @field_validator("modified_at", mode="before")
    @classmethod
    def convert_datetime_to_str(
        cls,
        v: str | datetime | None,
    ) -> str | None:
        """Convert datetime objects to ISO format strings."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


# ── SDK bootstrap ────────────────────────────────────────────────


def _ensure_ollama_sdk() -> Any:
    """Import the ollama Python SDK, raising ``ImportError`` if missing."""
    try:
        import ollama
    except ImportError:
        raise ImportError(
            "The 'ollama' Python package is not installed. Please install it manually: pip install ollama"
        ) from None
    return ollama


def is_ollama_sdk_available() -> bool:
    """Return ``True`` if the ollama SDK can be imported, without side-effects."""
    try:
        import ollama  # noqa: F401

        return True
    except ImportError:
        return False


# ── Models directory ────────────────────────────────────────────


def normalize_models_dir(raw: str) -> str:
    """Return an absolute models-dir path, or ``""`` to use Ollama's default.

    Raises ``ValueError`` when a non-empty value is not an absolute path.
    """
    text = raw.strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("Ollama models directory must be an absolute path")
    return str(path)


def apply_models_dir(path: str | None) -> str | None:
    """Set ``OLLAMA_MODELS`` for this process (and children such as ``ollama serve``).

    An empty/None *path* restores the environment value that was present when
    this helper first ran, so a cleared Octop setting does not drop a
    user-level ``OLLAMA_MODELS`` export.
    """
    global _original_ollama_models, _applied_models_dir
    if _original_ollama_models is _UNSET:
        _original_ollama_models = os.environ.get("OLLAMA_MODELS")
    cleaned = (path or "").strip()
    _applied_models_dir = cleaned or None
    if _applied_models_dir:
        os.environ["OLLAMA_MODELS"] = _applied_models_dir
    elif isinstance(_original_ollama_models, str) and _original_ollama_models:
        os.environ["OLLAMA_MODELS"] = _original_ollama_models
    else:
        os.environ.pop("OLLAMA_MODELS", None)
    return _applied_models_dir


def resolve_ollama_models_root(path: str) -> Path:
    """Return the directory that contains ``manifests/`` / ``blobs/``.

    Users sometimes pick the Ollama home (parent of ``models/``) rather than
    ``OLLAMA_MODELS`` itself.
    """
    root = Path(path)
    if (root / "manifests").is_dir():
        return root
    nested = root / "models"
    if (nested / "manifests").is_dir():
        return nested
    return root


def _ollama_name_keys(name: str) -> set[str]:
    n = name.strip()
    if not n:
        return set()
    keys = {n}
    if n.endswith(":latest"):
        bare = n[: -len(":latest")]
        if bare:
            keys.add(bare)
    elif ":" not in n:
        keys.add(f"{n}:latest")
    return keys


def names_match(left: str, right: str) -> bool:
    """True when two Ollama names refer to the same model (``:latest`` aliases)."""
    a = _ollama_name_keys(left)
    b = _ollama_name_keys(right)
    return bool(a and b and a & b)


def _name_from_manifest_rel(rel: Path) -> str | None:
    parts = rel.parts
    if len(parts) < 2:
        return None
    tag = parts[-1]
    if not tag or tag.startswith("."):
        return None
    rest = list(parts[:-1])
    if rest and rest[0] == _DEFAULT_REGISTRY:
        rest = rest[1:]
        if rest and rest[0] == _DEFAULT_NAMESPACE:
            rest = rest[1:]
    if not rest:
        return None
    return f"{'/'.join(rest)}:{tag}"


def list_models_from_dir(path: str | None) -> list[OllamaModelInfo]:
    """Discover models from an Ollama models directory (manifest layout)."""
    text = (path or "").strip()
    if not text:
        return []
    root = resolve_ollama_models_root(text)
    manifests = root / "manifests"
    if not manifests.is_dir():
        return []
    found: dict[str, OllamaModelInfo] = {}
    for manifest in manifests.rglob("*"):
        if not manifest.is_file():
            continue
        try:
            rel = manifest.relative_to(manifests)
        except ValueError:
            continue
        name = _name_from_manifest_rel(rel)
        if not name or name in found:
            continue
        # Manifest files are tiny JSON; do not report their size as the model size.
        found[name] = OllamaModelInfo(name=name, size=0)
    return list(found.values())


def merge_model_lists(
    primary: list[OllamaModelInfo], extra: list[OllamaModelInfo]
) -> list[OllamaModelInfo]:
    """Union two lists; *primary* wins when names are aliases (``:latest``)."""
    seen: set[str] = set()
    out: list[OllamaModelInfo] = []
    for src in (primary, extra):
        for model in src:
            keys = _ollama_name_keys(model.name)
            if not keys or seen.intersection(keys):
                continue
            seen.update(keys)
            out.append(model)
    return out


def _sdk_attr(item: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(item, dict) and key in item:
            value = item.get(key)
            if value is not None:
                return value
        value = getattr(item, key, None)
        if value is not None:
            return value
    return None


def _iter_sdk_models(raw: Any) -> list[Any]:
    if raw is None:
        return []
    models = getattr(raw, "models", None)
    if models is None and isinstance(raw, dict):
        models = raw.get("models")
    if not models:
        return []
    return list(models)


def _model_info_from_sdk(item: Any) -> OllamaModelInfo | None:
    name = str(_sdk_attr(item, "model", "name") or "").strip()
    if not name:
        return None
    size_raw = _sdk_attr(item, "size") or 0
    try:
        size = int(size_raw)
    except (TypeError, ValueError):
        size = 0
    digest = _sdk_attr(item, "digest")
    return OllamaModelInfo(
        name=name,
        size=size,
        digest=str(digest) if digest is not None else None,
        modified_at=_sdk_attr(item, "modified_at"),
    )


# ── Server bootstrap ────────────────────────────────────────────


def _is_ollama_reachable() -> bool:
    """Quick connectivity check to the Ollama HTTP endpoint."""
    import urllib.request

    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _start_ollama_server() -> None:
    """Try to start ``ollama serve`` in the background."""
    global _OLLAMA_SERVER_STARTED

    ollama_bin = shutil.which("ollama")
    if ollama_bin is None and platform.system() == "Darwin":
        candidates = [
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
        ]
        for c in candidates:
            if shutil.which(c):
                ollama_bin = c
                break
    if ollama_bin is None:
        raise OSError(
            "Ollama binary not found on this system. Please install Ollama from https://ollama.com/download"
        )

    logger.info("Ollama daemon not reachable, starting ollama serve …")
    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception as exc:
        raise OSError(f"Failed to start ollama serve: {exc}") from exc

    for _ in range(10):
        time.sleep(1)
        if _is_ollama_reachable():
            logger.info("Ollama daemon is now running.")
            _OLLAMA_SERVER_STARTED = True
            return
    raise OSError("Started ollama serve but it did not become reachable within 10 seconds.")


def _ensure_ollama_server() -> None:
    """Make sure the Ollama daemon is reachable, starting it if needed."""
    if _is_ollama_reachable():
        return
    _start_ollama_server()


def _ensure_ollama() -> Any:
    """Bootstrap both the SDK and the server, then return the module."""
    sdk = _ensure_ollama_sdk()
    _ensure_ollama_server()
    return sdk


def is_ollama_reachable() -> bool:
    """Public wrapper: True when the Ollama HTTP endpoint responds."""
    return _is_ollama_reachable()


def start_ollama_service() -> None:
    """Ensure the Ollama daemon is running (start if needed)."""
    _ensure_ollama_server()


def stop_ollama_service() -> bool:
    """Best-effort stop of an Ollama daemon we started; returns True if stopped."""
    global _OLLAMA_SERVER_STARTED
    if not _OLLAMA_SERVER_STARTED and not _is_ollama_reachable():
        return True

    stopped = False
    try:
        # Prefer polite terminate of `ollama serve` we may have spawned.
        # Cross-platform: try pkill on POSIX; on Windows skip process kill.
        if os.name == "posix":
            subprocess.run(
                ["pkill", "-f", "ollama serve"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # wait briefly
            for _ in range(20):
                if not _is_ollama_reachable():
                    stopped = True
                    break
                time.sleep(0.25)
        else:
            # Windows: leave daemon running; preference flag still gates auto-start.
            stopped = not _is_ollama_reachable()
    except Exception as exc:
        logger.warning("Failed to stop ollama serve: %s", exc)
    _OLLAMA_SERVER_STARTED = False
    return stopped or not _is_ollama_reachable()


class OllamaModelManager:
    """High-level wrapper around the Ollama SDK for model lifecycle."""

    @staticmethod
    def list_models(*, start_if_needed: bool = True) -> list[OllamaModelInfo]:
        """Return the current model list from ``ollama.list()``.

        When *start_if_needed* is false, only talk to an already-running daemon
        (do not spawn ``ollama serve``).
        """
        ollama = _ensure_ollama() if start_if_needed else _ensure_ollama_sdk()
        raw = ollama.list()
        models: list[OllamaModelInfo] = []
        for item in _iter_sdk_models(raw):
            info = _model_info_from_sdk(item)
            if info is not None:
                models.append(info)
        return models

    @staticmethod
    def pull_model(name: str) -> OllamaModelInfo:
        """Pull/download a model via ``ollama.pull``."""
        ollama = _ensure_ollama()
        logger.info("Pulling Ollama model: %s", name)
        ollama.pull(name)
        logger.info("Pull completed: %s", name)

        for model in OllamaModelManager.list_models():
            if names_match(model.name, name):
                return model

        raise ValueError(f"Ollama model '{name}' not found after pull.")

    @staticmethod
    def delete_model(name: str) -> None:
        """Delete a model from the local Ollama instance."""
        ollama = _ensure_ollama()
        logger.info("Deleting Ollama model: %s", name)
        ollama.delete(name)
        logger.info("Ollama model deleted: %s", name)
