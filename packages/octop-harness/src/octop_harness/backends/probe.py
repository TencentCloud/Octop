"""Connectivity probes for harness backend specs (write → read → delete)."""

from __future__ import annotations

import contextlib
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop_harness.backends.s3_backend import cos_spec_to_s3_compat
from octop_harness.backends.storage_errors import (
    classify_probe_exception,
    classify_storage_error,
)

from .utils import materialize_storage_path

logger = logging.getLogger(__name__)

_PROBE_CONTENT = "harness-backend-probe"
_PROBE_PREFIX = ".harness-probe-"


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str | None = None
    message_key: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.message_key is not None:
            out["message_key"] = self.message_key
        if self.message is not None:
            out["message"] = self.message
        return out


def probe_backend(
    spec: dict[str, Any],
    *,
    workspace_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Round-trip probe for a resolved harness backend spec.

    Returns a JSON-friendly dict: ``{ok, message?}`` or ``{ok, message_key?}``.
    """
    backend_type = str(spec.get("type") or "")
    workspace = tempfile.mkdtemp(prefix="harness-probe-")
    test_name = f"{_PROBE_PREFIX}{uuid.uuid4().hex}.txt"
    test_path = f"/{test_name}"
    result = ProbeResult(ok=False, message="probe did not complete")
    backend: Any = None

    try:
        backend = _resolve_probe_backend(spec, workspace_dir=workspace_dir or workspace)
        result = _run_probe_roundtrip(spec, backend, test_path, workspace)
    except (ImportError, ModuleNotFoundError, OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
        logger.info("backend probe failed for type=%s: %s", backend_type, exc)
        classified = classify_probe_exception(exc)
        result = ProbeResult(ok=False, message=classified.message, message_key=classified.message_key)
    finally:
        if backend is not None:
            close = getattr(backend, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
        _cleanup_probe_workspace(workspace, test_name)

    return result.as_dict()


def _run_probe_roundtrip(
    spec: dict[str, Any],
    backend: Any,
    test_path: str,
    workspace: str,
) -> ProbeResult:
    write_result = backend.write(test_path, _PROBE_CONTENT)
    if getattr(write_result, "error", None):
        return _probe_io_failure("write", write_result.error)

    read_result = backend.read(test_path)
    if getattr(read_result, "error", None):
        return _probe_io_failure("read", read_result.error)

    file_data = getattr(read_result, "file_data", None) or {}
    content = file_data.get("content") if isinstance(file_data, dict) else None
    if content != _PROBE_CONTENT:
        return ProbeResult(
            ok=False,
            message="Read-back content did not match what was written.",
            message_key="probe_content_mismatch",
        )

    deleted, delete_err = _delete_probe_object(spec, backend, test_path, workspace)
    if not deleted:
        return _probe_io_failure("delete", delete_err or "delete failed")

    return ProbeResult(ok=True, message_key="probe_roundtrip_ok")


def _probe_io_failure(op: str, raw: str | BaseException | None) -> ProbeResult:
    classified = classify_storage_error(raw, op=op)
    return ProbeResult(ok=False, message=classified.message, message_key=classified.message_key)


def _cleanup_probe_workspace(workspace: str, test_name: str) -> None:
    with contextlib.suppress(OSError):
        probe_file = Path(workspace) / test_name.lstrip("/")
        if probe_file.exists():
            probe_file.unlink()
    with contextlib.suppress(OSError):
        Path(workspace).rmdir()


def _resolve_probe_backend(spec: dict[str, Any], *, workspace_dir: str | Path) -> Any:
    from octop_harness.backends import resolve_backend

    try:
        return resolve_backend(spec, workspace_dir=workspace_dir)
    except (ImportError, ModuleNotFoundError) as exc:
        if spec.get("type") != "cos":
            raise
        alt = cos_spec_to_s3_compat(spec)
        if alt is None:
            raise
        logger.info("cos SDK unavailable (%s), falling back to S3-compatible probe", exc)
        return resolve_backend(alt, workspace_dir=workspace_dir)


def _delete_probe_object(
    spec: dict[str, Any],
    backend: Any,
    test_path: str,
    workspace: str,
) -> tuple[bool, str | None]:
    backend_type = str(spec.get("type") or "")

    if backend_type in {"cos", "s3", "oss", "obs", "postgres"}:
        # All cloud backends inherit CloudStorageBackend and expose delete_object().
        # When the native COS SDK is unavailable, _resolve_probe_backend already
        # falls back to S3Backend, so backend is always one of these concrete types.
        return _delete_via_backend(backend, test_path)
    if backend_type in {"docker", "opensandbox"}:
        execute = getattr(backend, "execute", None)
        if callable(execute):
            with contextlib.suppress(Exception):
                execute(f"rm -f -- {test_path}")
            return True, None
        return False, "sandbox backend has no execute method"
    if backend_type == "state":
        return True, None

    root = spec.get("root_dir") or workspace if backend_type in {"filesystem", "local_shell"} else workspace
    return _delete_local_path(str(root), test_path)


def _delete_local_path(root: str, test_path: str) -> tuple[bool, str | None]:
    local = materialize_storage_path(test_path, host_mount=root)
    if local is None or not local.exists():
        return True, None
    try:
        local.unlink()
        return True, None
    except OSError as exc:
        return False, str(exc)


def _delete_via_backend(backend: Any, test_path: str) -> tuple[bool, str | None]:
    """Delete using the backend's own ``delete_object(path)`` method."""
    delete_fn = getattr(backend, "delete_object", None)
    if callable(delete_fn):
        try:
            delete_fn(test_path)
            return True, None
        except (OSError, RuntimeError) as exc:
            return False, str(exc)
    return False, "backend has no delete_object method"
