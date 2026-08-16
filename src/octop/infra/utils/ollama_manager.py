from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_OLLAMA_SERVER_STARTED = False


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


# ── Server bootstrap ────────────────────────────────────────────


def _is_ollama_reachable() -> bool:
    """Quick connectivity check to the Ollama HTTP endpoint."""
    import urllib.error
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
    import os

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
    def list_models() -> list[OllamaModelInfo]:
        """Return the current model list from ``ollama.list()``."""
        ollama = _ensure_ollama()
        raw = ollama.list()
        models: list[OllamaModelInfo] = []
        for m in raw.get("models", []):
            models.append(
                OllamaModelInfo(
                    name=m.get("model", ""),
                    size=m.get("size", 0) or 0,
                    digest=m.get("digest"),
                    modified_at=m.get("modified_at"),
                ),
            )
        return models

    @staticmethod
    def pull_model(name: str) -> OllamaModelInfo:
        """Pull/download a model via ``ollama.pull``."""
        ollama = _ensure_ollama()
        logger.info("Pulling Ollama model: %s", name)
        ollama.pull(name)
        logger.info("Pull completed: %s", name)

        for model in OllamaModelManager.list_models():
            if model.name == name:
                return model

        raise ValueError(f"Ollama model '{name}' not found after pull.")

    @staticmethod
    def delete_model(name: str) -> None:
        """Delete a model from the local Ollama instance."""
        ollama = _ensure_ollama()
        logger.info("Deleting Ollama model: %s", name)
        ollama.delete(name)
        logger.info("Ollama model deleted: %s", name)
