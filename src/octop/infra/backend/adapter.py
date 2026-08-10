"""Map Octop ``storage_backends`` rows to harness-agent backend specs (no I/O)."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.db.repos.backends import BackendRow

_OBJECT_KINDS = frozenset({"cos", "s3", "oss", "obs", "custom"})
_AGENT_RESOLVABLE_KINDS = frozenset(
    {"cos", "s3", "oss", "obs", "custom", "filesystem", "shell", "postgres", "docker"}
)


def storage_backend_kind_agent_resolvable(kind: str) -> bool:
    """True when ``row_to_backend_spec`` may produce a harness spec for this kind."""
    return (kind or "").lower() in _AGENT_RESOLVABLE_KINDS


def _parse_config_json(row: BackendRow) -> dict[str, Any]:
    if not row.config_json:
        return {}
    try:
        parsed = json.loads(row.config_json)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def row_to_backend_spec(row: BackendRow) -> dict[str, Any] | None:
    """Convert a DB row into a harness ``resolve_backend`` spec."""
    kind = (row.kind or "").lower()
    cfg = _parse_config_json(row)

    if kind == "cos":
        if not all((row.access_key, row.secret_key, row.bucket, row.region)):
            return None
        spec: dict[str, Any] = {
            "type": "cos",
            "bucket": row.bucket,
            "region": row.region,
            "secret_id": row.access_key,
            "secret_key": row.secret_key,
        }
        if row.endpoint:
            spec["endpoint"] = row.endpoint
        if cfg.get("prefix"):
            spec["prefix"] = cfg["prefix"]
        return spec

    if kind == "oss":
        if not all((row.access_key, row.secret_key, row.bucket, row.endpoint)):
            return None
        spec = {
            "type": "oss",
            "bucket": row.bucket,
            "endpoint": row.endpoint,
            "access_key_id": row.access_key,
            "access_key_secret": row.secret_key,
        }
        if cfg.get("prefix"):
            spec["prefix"] = cfg["prefix"]
        spec.update({k: v for k, v in cfg.items() if k not in spec})
        return spec

    if kind == "obs":
        if not all((row.access_key, row.secret_key, row.bucket, row.endpoint)):
            return None
        spec = {
            "type": "obs",
            "bucket": row.bucket,
            "endpoint": row.endpoint,
            "access_key_id": row.access_key,
            "secret_access_key": row.secret_key,
        }
        if cfg.get("prefix"):
            spec["prefix"] = cfg["prefix"]
        spec.update({k: v for k, v in cfg.items() if k not in spec})
        return spec

    if kind in _OBJECT_KINDS - {"cos", "oss", "obs"}:
        # Generic S3-compatible (AWS S3, MinIO, custom, …)
        if not all((row.access_key, row.secret_key, row.bucket)):
            return None
        spec = {
            "type": "s3",
            "bucket": row.bucket,
            "access_key_id": row.access_key,
            "secret_access_key": row.secret_key,
        }
        if row.region:
            spec["region"] = row.region
        if row.endpoint:
            spec["endpoint_url"] = (
                row.endpoint if "://" in row.endpoint else f"https://{row.endpoint}"
            )
        spec.update({k: v for k, v in cfg.items() if k not in spec})
        return spec

    if kind == "filesystem":
        root = cfg.get("root_dir") or cfg.get("path") or row.bucket
        if not root:
            return None
        return {"type": "filesystem", "root_dir": str(root), "virtual_mode": True}

    if kind == "shell":
        root = cfg.get("root_dir") or row.bucket or "/"
        return {"type": "local_shell", "root_dir": str(root), "virtual_mode": True}

    if kind == "postgres":
        if not row.endpoint:
            return None
        conn = cfg.get("connection_string")
        if not conn:
            user = row.access_key or cfg.get("user")
            password = row.secret_key or cfg.get("password")
            dbname = row.bucket or cfg.get("database")
            if user and password and dbname:
                host = row.endpoint
                schema = row.region or cfg.get("schema") or "public"
                conn = f"postgresql://{user}:{password}@{host}/{dbname}"
                if schema != "public":
                    cfg = {**cfg, "schema": schema}
        if not conn:
            return None
        return {"type": "postgres", "connection_string": conn, **cfg}

    if kind == "docker":
        image = cfg.get("image") or row.bucket
        if not image:
            return None
        from octop.infra.backend.docker_spec import apply_docker_cfg_keys

        spec = {"type": "docker", "image": str(image)}
        apply_docker_cfg_keys(spec, cfg)
        return spec

    return None
