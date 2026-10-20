"""First-party Postgres workspace backend (deepagents 0.7) plus spec helpers.

Hosts (including Octop) may emit a libpq ``connection_string`` / ``dsn`` or
split fields. :func:`postgres_config_kwargs` maps both onto
:class:`PostgresConfig`. :class:`PostgresBackend` stores files as JSON
``FileData`` rows and implements ``BackendProtocol`` via
:class:`~octop_harness.backends.cloud_storage_base.CloudStorageBackend`.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, fields
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from deepagents.backends.protocol import FileData, FileInfo

from octop_harness.backends.cloud_storage_base import CloudStorageBackend

logger = logging.getLogger(__name__)

_URI_KEYS: frozenset[str] = frozenset({"connection_string", "dsn"})
_URI_SCHEMES: frozenset[str] = frozenset({"postgres", "postgresql"})

# Matches deepagents-backends 0.2 ``PostgresConfig``; callers should pass the
# live dataclass field set when the extra is installed.
DEFAULT_POSTGRES_CONFIG_FIELDS: frozenset[str] = frozenset(
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
        "prefix",
    }
)

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def postgres_config_kwargs(
    kwargs: Mapping[str, Any],
    *,
    field_names: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Return kwargs safe to pass to ``PostgresConfig``.

    ``connection_string`` / ``dsn`` are parsed into split fields. Explicit
    split fields in *kwargs* win over the URI. Unknown keys are dropped with
    a warning. An unparseable URI raises ``ValueError`` that does not echo
    the password (libpq's own errors often quote the whole URI).
    """
    fields = set(field_names if field_names is not None else DEFAULT_POSTGRES_CONFIG_FIELDS)
    uri = kwargs.get("connection_string") or kwargs.get("dsn")
    out: dict[str, Any] = {}
    if isinstance(uri, str) and uri.strip():
        out.update({key: value for key, value in _parse_postgres_conninfo(uri).items() if key in fields})

    for key, value in kwargs.items():
        if key in _URI_KEYS:
            continue
        if key in fields:
            out[key] = value
        else:
            logger.warning("ignoring unknown postgres backend spec key %r", key)
    return out


def _parse_postgres_conninfo(value: str) -> dict[str, Any]:
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


def _map_libpq_dict(raw: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    host = raw.get("host")
    if host:
        out["host"] = str(host)
    port = raw.get("port")
    if port is not None and port != "":
        try:
            out["port"] = int(port)
        except (TypeError, ValueError):
            raise ValueError("invalid postgres connection_string") from None
    database = raw.get("dbname") or raw.get("database")
    if database:
        out["database"] = str(database)
    user = raw.get("user")
    if user:
        out["user"] = str(user)
    password = raw.get("password")
    if password is not None:
        out["password"] = str(password)
    sslmode = raw.get("sslmode")
    if sslmode:
        out["sslmode"] = str(sslmode)
    return out


def _sql_ident(name: str) -> str:
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(f"invalid postgres identifier: {name!r}")
    return name


def _require_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise ImportError(
            "Postgres backend requires 'psycopg'. Install with: pip install 'octop-harness[remote-backends]'.",
        ) from exc
    return psycopg


@dataclass
class PostgresConfig:
    """Connection parameters for the bundled Postgres workspace backend."""

    host: str
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    table: str = "files"
    schema: str = "public"
    sslmode: str = "prefer"
    connection_timeout: float = 30.0
    prefix: str = ""
    min_pool_size: int = 1
    max_pool_size: int = 20
    max_idle_seconds: float = 300.0
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("PostgresConfig.host is required")
        object.__setattr__(self, "schema", _sql_ident(self.schema or "public"))
        object.__setattr__(self, "table", _sql_ident(self.table or "files"))
        object.__setattr__(self, "prefix", self.prefix.strip("/"))

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> PostgresConfig:
        fitted = postgres_config_kwargs(kwargs, field_names={f.name for f in fields(cls)} - {"extra"})
        known = {f.name for f in fields(cls)}
        extra = {k: v for k, v in kwargs.items() if k not in known and k not in _URI_KEYS}
        return cls(**fitted, extra=extra)

    @property
    def conninfo(self) -> str:
        from psycopg.conninfo import make_conninfo

        timeout = max(1, int(self.connection_timeout))
        return str(
            make_conninfo(
                host=self.host,
                port=int(self.port),
                dbname=self.database,
                user=self.user,
                password=self.password,
                sslmode=self.sslmode,
                connect_timeout=timeout,
            )
        )


class PostgresBackend(CloudStorageBackend):
    """Postgres-backed virtual filesystem (sync psycopg, deepagents 0.7).

    Table is created on first use. Rows store the CloudStorageBackend
    ``FileData`` JSON envelope. Legacy ``deepagents-backends`` rows whose
    ``content`` is a line array are readable and rewritten as a string on edit.
    """

    def __init__(self, config: PostgresConfig) -> None:
        _require_psycopg()
        self._config = config
        self._ready = False
        self._lock = threading.Lock()
        self._qualified = f"{config.schema}.{config.table}"

    @property
    def _prefix(self) -> str:
        return self._config.prefix

    def _storage_error_types(self) -> tuple[type[BaseException], ...]:
        psycopg = _require_psycopg()
        return (*super()._storage_error_types(), psycopg.Error)

    def close(self) -> None:
        """No persistent pool; present so probe / hosts can call ``close()``."""

    def _raw_connect(self) -> Any:
        psycopg = _require_psycopg()
        return psycopg.connect(self._config.conninfo)

    def _ensure_ready(self) -> None:
        with self._lock:
            if not self._ready:
                with self._raw_connect() as conn:
                    self._init_schema(conn)
                self._ready = True

    def _init_schema(self, conn: Any) -> None:
        table = self._qualified
        idx = self._config.table
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self._config.schema}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                path TEXT PRIMARY KEY,
                content JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{idx}_path_prefix
            ON {table} (path text_pattern_ops)
            """
        )
        conn.commit()

    def _connect(self) -> Any:
        self._ensure_ready()
        return self._raw_connect()

    def _normalize_stored(self, raw: Any) -> FileData | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            return self._parse_body(raw)
        if not isinstance(raw, dict) or "content" not in raw:
            return None
        content = raw.get("content")
        text = "\n".join(str(line) for line in content) if isinstance(content, list) else str(content)
        out: FileData = {
            "content": text,
            "encoding": str(raw.get("encoding") or "utf-8"),
        }
        if raw.get("created_at"):
            out["created_at"] = str(raw["created_at"])
        if raw.get("modified_at"):
            out["modified_at"] = str(raw["modified_at"])
        return out

    def _get_file_data(self, path: str) -> FileData | None:
        key = self._key(path)
        if not key or key.endswith("/"):
            return None
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT content FROM {self._qualified} WHERE path = %s",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return self._normalize_stored(row[0])

    def _put_file_data(self, path: str, file_data: FileData) -> None:
        from psycopg.types.json import Jsonb

        key = self._key(path)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._qualified} (path, content, created_at, modified_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (path) DO UPDATE SET
                    content = EXCLUDED.content,
                    modified_at = NOW()
                """,
                (key, Jsonb(dict(file_data))),
            )
            conn.commit()

    def _put_dir_marker(self, virtual_dir: str) -> None:
        from psycopg.types.json import Jsonb

        key = self._prefix_key(virtual_dir)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._qualified} (path, content, created_at, modified_at)
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (path) DO NOTHING
                """,
                (key, Jsonb({})),
            )
            conn.commit()

    def _ls_entries(self, path: str) -> list[FileInfo]:
        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/"):
            prefix_key += "/"
        like_all = f"{prefix_key}%" if prefix_key else "%"
        like_nested = f"{prefix_key}%/%" if prefix_key else "%/%"
        entries: list[FileInfo] = []
        with self._connect() as conn:
            file_rows = conn.execute(
                f"""
                SELECT path, content, modified_at
                FROM {self._qualified}
                WHERE path LIKE %s AND path NOT LIKE %s
                ORDER BY path
                """,
                (like_all, like_nested),
            ).fetchall()
            dir_rows = conn.execute(
                f"""
                SELECT DISTINCT split_part(substr(path, %s), '/', 1)
                FROM {self._qualified}
                WHERE path LIKE %s
                ORDER BY 1
                """,
                (len(prefix_key) + 1, like_nested),
            ).fetchall()
        for key, content, modified_at in file_rows:
            if str(key).endswith("/"):
                entries.append({"path": self._virtual_path(str(key).rstrip("/")), "is_dir": True})
                continue
            info: FileInfo = {"path": self._virtual_path(str(key)), "is_dir": False}
            if isinstance(content, dict):
                body = content.get("content")
                if isinstance(body, str):
                    info["size"] = len(body.encode("utf-8"))
                elif isinstance(body, list):
                    info["size"] = len(body)
            if modified_at is not None:
                info["modified_at"] = str(modified_at)
            entries.append(info)
        seen = {e["path"] for e in entries}
        for (name,) in dir_rows:
            if not name:
                continue
            vp = self._virtual_path(f"{prefix_key}{name}".rstrip("/"))
            if vp not in seen:
                entries.append({"path": vp, "is_dir": True})
        entries.sort(key=lambda e: e["path"])
        return entries

    def _collect_recursive(self, path: str) -> dict[str, FileData]:
        prefix_key = self._key(path)
        if prefix_key and not prefix_key.endswith("/") and path != "/":
            prefix_key += "/"
        like = f"{prefix_key}%" if prefix_key else "%"
        files: dict[str, FileData] = {}
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT path, content FROM {self._qualified} WHERE path LIKE %s",
                (like,),
            ).fetchall()
        for key, content in rows:
            if str(key).endswith("/"):
                continue
            fd = self._normalize_stored(content)
            if fd is not None:
                files[self._virtual_path(str(key))] = fd
        return files

    def _iter_prefix_object_keys(self, path: str) -> Iterator[str]:
        prefix_key = self._prefix_key(path)
        like = f"{prefix_key}%" if prefix_key else "%"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT path FROM {self._qualified} WHERE path LIKE %s",
                (like,),
            ).fetchall()
        for (key,) in rows:
            yield str(key)

    def _prefix_has_objects(self, path: str) -> bool:
        prefix_key = self._prefix_key(path)
        like = f"{prefix_key}%" if prefix_key else "%"
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT 1 FROM {self._qualified} WHERE path LIKE %s LIMIT 1",
                (like,),
            ).fetchone()
        return row is not None

    def _copy_object(self, src: str, dest: str) -> None:
        src_key = self._key(src)
        dest_key = self._key(dest)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self._qualified} (path, content, created_at, modified_at)
                SELECT %s, content, NOW(), NOW()
                FROM {self._qualified}
                WHERE path = %s
                ON CONFLICT (path) DO UPDATE SET
                    content = EXCLUDED.content,
                    modified_at = NOW()
                """,
                (dest_key, src_key),
            )
            conn.commit()

    def delete_object(self, path: str) -> None:
        key = self._key(path)
        with self._connect() as conn:
            conn.execute(f"DELETE FROM {self._qualified} WHERE path = %s", (key,))
            conn.commit()

    def delete_prefix(self, path: str) -> int:
        prefix_key = self._prefix_key(path)
        like = f"{prefix_key}%" if prefix_key else "%"
        with self._connect() as conn:
            cur = conn.execute(f"DELETE FROM {self._qualified} WHERE path LIKE %s", (like,))
            conn.commit()
            return int(cur.rowcount or 0)


__all__ = [
    "DEFAULT_POSTGRES_CONFIG_FIELDS",
    "PostgresBackend",
    "PostgresConfig",
    "postgres_config_kwargs",
]
