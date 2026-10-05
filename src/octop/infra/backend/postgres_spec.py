"""Map Octop postgres storage rows / inline specs onto PostgresConfig fields.

``deepagents_backends.PostgresConfig`` is a dataclass of split fields. Passing a
libpq URI as ``connection_string`` raises ``TypeError``. Discrete credentials
must also stay out of a URL so passwords containing ``@`` / ``#`` / ``/`` are
not mis-parsed.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from octop.infra.db.repos.backends import BackendRow

POSTGRES_SPEC_FIELDS: frozenset[str] = frozenset(
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
_URI_KEYS: frozenset[str] = frozenset({"connection_string", "dsn"})
_URI_SCHEMES: frozenset[str] = frozenset({"postgres", "postgresql"})


def row_to_postgres_spec(row: BackendRow, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Build a harness postgres spec from a storage row + parsed ``config_json``."""
    spec: dict[str, Any] = {"type": "postgres"}
    uri = _first_uri(cfg)
    if uri is not None:
        spec.update(parse_postgres_conninfo(uri))

    for key, value in cfg.items():
        if key in POSTGRES_SPEC_FIELDS:
            spec[key] = value

    if row.endpoint:
        host, port = split_host_port(row.endpoint)
        if host:
            spec["host"] = host
        if port is not None:
            spec["port"] = port
    if row.access_key:
        spec["user"] = row.access_key
    if row.secret_key:
        spec["password"] = row.secret_key
    if row.bucket:
        spec["database"] = row.bucket
    if row.region:
        spec["schema"] = row.region

    if not spec.get("host"):
        return None
    has_discrete = all(spec.get(key) for key in ("user", "password", "database"))
    if not has_discrete and uri is None:
        return None
    return spec


def normalize_postgres_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Turn an inline postgres spec into split fields (drops URI / unknown keys)."""
    out: dict[str, Any] = {"type": "postgres"}
    uri = _first_uri(spec)
    if uri is not None:
        out.update(parse_postgres_conninfo(uri))
    for key, value in spec.items():
        if key in POSTGRES_SPEC_FIELDS:
            out[key] = value
    return out


def _first_uri(spec: dict[str, Any]) -> str | None:
    for key in _URI_KEYS:
        value = spec.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def split_host_port(endpoint: str) -> tuple[str, int | None]:
    """Split ``host:port``, ``[ipv6]:port``, or a bare host."""
    text = endpoint.strip()
    if not text:
        return "", None
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return text, None
        host = text[1:end]
        rest = text[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host, int(port)
    return text, None


def parse_postgres_conninfo(value: str) -> dict[str, Any]:
    """Parse a libpq URI or keyword conninfo. Never echoes the secret in errors."""
    text = value.strip()
    try:
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        return _parse_postgres_uri(text)
    try:
        raw = conninfo_to_dict(text)
    except Exception:
        raise ValueError("invalid postgres connection_string") from None
    return _map_libpq_dict(raw)


def _parse_postgres_uri(text: str) -> dict[str, Any]:
    parsed = urlparse(text)
    if parsed.scheme not in _URI_SCHEMES:
        raise ValueError("invalid postgres connection_string")
    raw: dict[str, Any] = {}
    if parsed.hostname:
        raw["host"] = parsed.hostname
    if parsed.port is not None:
        raw["port"] = parsed.port
    if parsed.username is not None:
        raw["user"] = unquote(parsed.username)
    if parsed.password is not None:
        raw["password"] = unquote(parsed.password)
    path = parsed.path.lstrip("/")
    if path:
        raw["dbname"] = unquote(path)
    query = parse_qs(parsed.query, keep_blank_values=False)
    sslmode = query.get("sslmode")
    if sslmode:
        raw["sslmode"] = sslmode[0]
    return _map_libpq_dict(raw)


def _map_libpq_dict(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if raw.get("host"):
        out["host"] = str(raw["host"])
    port = raw.get("port")
    if port is not None and port != "":
        try:
            out["port"] = int(port)
        except (TypeError, ValueError):
            raise ValueError("invalid postgres connection_string") from None
    database = raw.get("dbname") or raw.get("database")
    if database:
        out["database"] = str(database)
    if raw.get("user"):
        out["user"] = str(raw["user"])
    if raw.get("password") is not None:
        out["password"] = str(raw["password"])
    if raw.get("sslmode"):
        out["sslmode"] = str(raw["sslmode"])
    return out
