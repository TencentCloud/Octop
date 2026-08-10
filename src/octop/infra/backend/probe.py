"""Octop-specific storage backend probes (docker + row → harness probe)."""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import tempfile
import uuid
from typing import Any, cast

from harness_agent.backends.probe import probe_backend

from octop.infra.backend.adapter import row_to_backend_spec
from octop.infra.backend.docker_spec import (
    DEFAULT_SANDBOX_PREFIX,
    enrich_docker_backend_spec,
)
from octop.infra.db.repos.backends import BackendRow

logger = logging.getLogger(__name__)

_PROBE_CONTENT = "octop-docker-probe"
_PROBE_TEST_ID = "test"


def row_for_probe(
    *,
    kind: str,
    endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    bucket: str | None = None,
    region: str | None = None,
    config_json: str | None = None,
    base: BackendRow | None = None,
) -> BackendRow:
    """Build a :class:`BackendRow` for probing from form fields (+ optional stored row)."""
    if base is None:
        return BackendRow(
            id=0,
            name="probe",
            kind=kind,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            region=region,
            config_json=config_json,
            note=None,
            enabled=1,
            created_at=0,
            updated_at=0,
        )
    return BackendRow(
        id=base.id,
        name=base.name,
        kind=kind or base.kind,
        endpoint=endpoint if endpoint is not None else base.endpoint,
        access_key=access_key if access_key else base.access_key,
        secret_key=secret_key if secret_key else base.secret_key,
        bucket=bucket if bucket is not None else base.bucket,
        region=region if region is not None else base.region,
        config_json=config_json if config_json is not None else base.config_json,
        note=base.note,
        enabled=base.enabled,
        created_at=base.created_at,
        updated_at=base.updated_at,
    )


def probe_storage_backend(row: BackendRow) -> dict[str, Any]:
    """Return ``{ok: bool, message?: str, message_key?: str}`` after a probe."""
    kind = (row.kind or "").lower()

    if kind == "docker":
        return _probe_docker(row)

    spec = row_to_backend_spec(row)
    if spec is None:
        return {"ok": False, "message": "configuration incomplete"}

    if kind == "postgres" and not spec.get("connection_string"):
        if not row.endpoint:
            return {"ok": False, "message": "host/endpoint not configured"}
        return {"ok": True, "message": "postgres configuration present (no file round-trip)"}

    return probe_backend(spec)


def _docker_probe_spec(row: BackendRow) -> dict[str, Any] | None:
    """Build a docker harness spec with probe test ids (``agent_id`` / ``username`` = test)."""
    spec = row_to_backend_spec(row)
    if spec is None:
        return None
    scope = str(spec.get("sandbox_scope") or "agent").strip().lower() or "agent"
    if scope == "user":
        return enrich_docker_backend_spec(
            {**spec, "sandbox_scope": "user"},
            agent_id=_PROBE_TEST_ID,
            username=str(spec.get("username") or _PROBE_TEST_ID),
        )
    if scope == "fixed":
        out = enrich_docker_backend_spec(
            {**spec, "sandbox_scope": "fixed"},
            agent_id=_PROBE_TEST_ID,
        )
        out.setdefault("sandbox_id", str(spec.get("sandbox_id") or _PROBE_TEST_ID))
        return out
    return enrich_docker_backend_spec(
        {**spec, "sandbox_scope": "agent"},
        agent_id=_PROBE_TEST_ID,
    )


def _probe_docker(row: BackendRow) -> dict[str, Any]:
    """Ensure image, then write→read a probe file inside a real container."""
    image: str | None = None
    if row.config_json:
        try:
            cfg = json.loads(row.config_json)
            if isinstance(cfg, dict) and cfg.get("image"):
                image = str(cfg["image"])
        except Exception:
            pass
    if not image and row.bucket:
        image = str(row.bucket)
    if not image:
        return {"ok": False, "message": "docker image not configured"}

    try:
        import docker  # noqa: PLC0415 — optional; only needed for docker kind probe
    except ImportError:
        return {
            "ok": False,
            "message": (
                "docker Python package not installed (pip install 'orcakit-harness-agent[docker]')"
            ),
        }

    try:
        client = cast(Any, docker).from_env()
        client.ping()
    except Exception as exc:
        return {"ok": False, "message": f"docker daemon unreachable: {exc}"}

    try:
        from harness_agent.backends import resolve_backend
        from harness_agent.backends.docker_sandbox import ensure_docker_image
    except ImportError:
        return {
            "ok": False,
            "message": (
                "docker sandbox helpers unavailable (pip install 'orcakit-harness-agent[docker]')"
            ),
        }

    try:
        pulled = ensure_docker_image(image, client=client)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    spec = _docker_probe_spec(row)
    if spec is None:
        return {"ok": False, "message": "configuration incomplete"}
    spec.setdefault("sandbox_prefix", DEFAULT_SANDBOX_PREFIX)
    # Ephemeral probe container: close() removes it.
    spec["auto_remove"] = True

    workspace = tempfile.mkdtemp(prefix="octop-docker-probe-")
    test_name = f".octop-probe-{uuid.uuid4().hex}.txt"
    test_path = f"/{test_name}"
    backend: Any = None
    try:
        backend = resolve_backend(spec, workspace_dir=workspace)
        write_result = backend.write(test_path, _PROBE_CONTENT)
        if getattr(write_result, "error", None):
            return {"ok": False, "message": f"write failed: {write_result.error}"}
        read_result = backend.read(test_path)
        if getattr(read_result, "error", None):
            return {"ok": False, "message": f"read failed: {read_result.error}"}
        file_data = getattr(read_result, "file_data", None) or {}
        content = file_data.get("content") if isinstance(file_data, dict) else None
        if content != _PROBE_CONTENT:
            return {"ok": False, "message": "read content mismatch"}
        with contextlib.suppress(Exception):
            execute = getattr(backend, "execute", None)
            if callable(execute):
                execute(f"rm -f -- {test_path}")
        return {
            "ok": True,
            "message": (
                f"docker probe ok (image pulled: {image})"
                if pulled
                else f"docker probe ok (image={image})"
            ),
            "message_key": "docker_probe_roundtrip_ok",
        }
    except Exception as exc:
        logger.info("docker storage probe failed: %s", exc)
        return {"ok": False, "message": str(exc)}
    finally:
        if backend is not None:
            destroy = getattr(backend, "destroy", None)
            if callable(destroy):
                with contextlib.suppress(Exception):
                    destroy()
            else:
                close = getattr(backend, "close", None)
                if callable(close):
                    with contextlib.suppress(Exception):
                        close()
        shutil.rmtree(workspace, ignore_errors=True)
