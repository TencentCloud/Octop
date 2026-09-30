"""Map Octop ``storage_backends`` rows to octop-harness backend specs (no I/O)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from octop.infra.db.repos.backends import BackendRow

_OBJECT_KINDS = frozenset({"cos", "s3", "oss", "obs", "custom"})
_AGENT_RESOLVABLE_KINDS = frozenset(
    {
        "cos",
        "s3",
        "oss",
        "obs",
        "custom",
        "filesystem",
        "shell",
        "postgres",
        "docker",
        "opensandbox",
    }
)
_OPENSANDBOX_PROTOCOLS = frozenset({"http", "https"})
_DEFAULT_OPENSANDBOX_IMAGE = "python:3.12"

# ``octop_harness.backends.resolve_backend`` forwards every non-``type`` spec key to
# ``deepagents_backends.PostgresConfig(**kwargs)``, and that dataclass has no
# ``connection_string`` slot: a spec carrying a libpq URI raises ``TypeError`` and the
# agent never starts. Keep the field names in sync with the dataclass.
_POSTGRES_CONFIG_FIELDS = frozenset(
    {
        "host",
        "port",
        "database",
        "user",
        "password",
        "table",
        "schema",
        "min_pool_size",
        "max_pool_size",
        "max_idle_seconds",
        "connection_timeout",
        "sslmode",
    }
)
_POSTGRES_NUMBER_FIELDS = frozenset(
    {"port", "min_pool_size", "max_pool_size", "max_idle_seconds", "connection_timeout"}
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


def _postgres_value(name: str, value: Any) -> Any | None:
    """Coerce *value* for ``PostgresConfig`` field *name*; ``None`` means "drop it".

    Dropping is the only safe answer for a key the dataclass has no slot for: passing it
    through would raise ``TypeError`` inside ``resolve_backend``. Empty values are dropped
    too so the dataclass default applies, rather than an empty string overriding one.
    """
    if name not in _POSTGRES_CONFIG_FIELDS or value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if name in _POSTGRES_NUMBER_FIELDS:
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return None
    return text


def _postgres_uri_fields(conn: str) -> dict[str, Any]:
    """Split a libpq URI into ``PostgresConfig`` fields, decoding userinfo once.

    Percent-encoded credentials are read back as their literal characters (``%40`` →
    ``@``); re-encoding them would be a second layer, which is what makes a saved
    credential unusable. Query parameters are kept only when their key already names a
    ``PostgresConfig`` field — libpq spellings without a slot (``connect_timeout``,
    ``options``) are dropped instead of guessed at.
    """
    parsed = urlsplit(conn)
    try:
        port = parsed.port
    except ValueError:
        # A malformed URI says nothing usable about this backend; let the row's discrete
        # fields stand instead of failing agent start.
        return {}
    out: dict[str, Any] = {}
    for name, raw in (
        ("host", parsed.hostname),
        ("user", parsed.username),
        ("password", parsed.password),
        ("database", parsed.path.lstrip("/") or None),
    ):
        if raw:
            decoded = unquote(raw)
            coerced = _postgres_value(name, decoded)
            if coerced is not None:
                out[name] = coerced
    if port:
        out["port"] = port
    for name, value in parse_qsl(parsed.query, keep_blank_values=False):
        coerced = _postgres_value(name.lower(), value)
        if coerced is not None:
            out[name] = coerced
    return out


def normalize_postgres_spec(values: dict[str, Any]) -> dict[str, Any]:
    """Return a postgres harness spec built from ``PostgresConfig``'s discrete fields.

    Accepts a full URI (``connection_string`` / ``dsn``), discrete fields, or both; a
    discrete field wins over the URI it came from, matching the storage-form precedence.
    """
    out: dict[str, Any] = {}
    uri = values.get("connection_string") or values.get("dsn")
    if isinstance(uri, str) and uri.strip():
        out.update(_postgres_uri_fields(uri.strip()))
    for name, value in values.items():
        coerced = _postgres_value(name, value)
        if coerced is not None:
            out[name] = coerced
    return {"type": "postgres", **out}


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
        uri = cfg.get("connection_string") or cfg.get("dsn")
        has_uri = isinstance(uri, str) and bool(uri.strip())
        values: dict[str, Any] = dict(cfg)
        for name, raw in (
            ("host", row.endpoint),
            ("user", row.access_key),
            ("password", row.secret_key),
            ("database", row.bucket),
            ("schema", row.region),
        ):
            if raw:
                values[name] = raw
        spec = normalize_postgres_spec(values)
        if "host" not in spec:
            return None
        if has_uri:
            return spec
        # Same completeness rule the form has always had: without a saved URI, the
        # discrete credentials must all be filled or the backend is "incomplete".
        return spec if all(name in spec for name in ("user", "password", "database")) else None

    if kind == "docker":
        image = cfg.get("image") or row.bucket
        if not image:
            return None
        from octop.infra.backend.docker_spec import apply_docker_cfg_keys

        spec = {"type": "docker", "image": str(image)}
        apply_docker_cfg_keys(spec, cfg)
        return spec

    if kind == "opensandbox":
        image = cfg.get("image") or row.bucket or _DEFAULT_OPENSANDBOX_IMAGE
        spec = {"type": "opensandbox", "image": str(image)}
        api_key = row.secret_key or cfg.get("api_key")
        if api_key:
            spec["api_key"] = api_key
        domain = row.endpoint or cfg.get("domain")
        if domain:
            spec["domain"] = str(domain)
        protocol = str(row.region or cfg.get("protocol") or "http").strip().lower()
        spec["protocol"] = protocol if protocol in _OPENSANDBOX_PROTOCOLS else "http"
        for key in ("timeout", "command_timeout", "use_server_proxy"):
            if key in cfg:
                spec[key] = cfg[key]
        return spec

    return None


def storage_spec_previewable(spec: Any) -> bool:
    """Whether Admin storage UI may browse this backend's files.

    OpenSandbox is an agent-lifecycle remote sandbox (create on start, destroy
    on stop), so it is not browseable unless ``previewable`` is set.
    """
    if not isinstance(spec, dict):
        return True
    if str(spec.get("type") or "").lower() == "opensandbox":
        if "previewable" in spec:
            return bool(spec["previewable"])
        return False
    from octop.infra.backend.docker_spec import docker_spec_previewable

    return docker_spec_previewable(spec)
