"""Resolve agent memory storage backend for harness-agent / harness-memory."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, unquote, urlparse

from octop.config import OctopConfig
from octop.infra.agents.workspace_dir import host_system_dir
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

MemoryBackendChoice = Literal["follow", "sqlite", "postgres"]
_MEMORY_CHOICES = frozenset({"follow", "sqlite", "postgres"})
_NS_RE = re.compile(r"^agent_[A-Za-z0-9_-]+$")
_MEMORY_TABLES = ("raw_events", "atoms", "entities", "episodes", "candidates")


def memory_backend_from_agent_config(
    cfg: dict[str, Any],
    *,
    octop_config: OctopConfig,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Return HarnessAgentConfig kwargs for memory storage (may be empty).

    Recognized ``config_json.memory.backend`` shapes:

    * omitted / null → empty on SQLite control plane (harness default
      ``memory.sqlite``); on PostgreSQL control plane, default to the same
      DSN with per-agent schema (``use_control_plane_dsn``)
    * ``{"type": "sqlite", "db_path": "..."}`` (db_path optional)
    * ``{"type": "postgres", "dsn": "..."}``
    * ``{"type": "postgres", "use_control_plane_dsn": true}``
    """
    mem = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    backend = mem.get("backend") if isinstance(mem, dict) else None
    if backend is None:
        if octop_config.database.is_postgresql:
            return {
                "memory_backend": {
                    "type": "postgres",
                    "dsn": octop_config.database.postgresql_conninfo(),
                }
            }
        return {}
    if not isinstance(backend, dict):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "memory.backend must be an object")

    btype = str(backend.get("type") or "sqlite").strip().lower()
    if btype == "sqlite":
        db_path = backend.get("db_path")
        if not db_path and workspace_dir is not None:
            db_path = str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")
        spec: dict[str, Any] = {"type": "sqlite"}
        if db_path:
            spec["db_path"] = str(db_path)
        return {"memory_backend": spec}

    if btype == "postgres":
        dsn = backend.get("dsn")
        if backend.get("use_control_plane_dsn") or not dsn:
            if not octop_config.database.is_postgresql:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    "memory.backend use_control_plane_dsn requires postgresql control plane",
                )
            dsn = octop_config.database.postgresql_conninfo()
        return {"memory_backend": {"type": "postgres", "dsn": str(dsn)}}

    raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unsupported memory.backend.type: {btype!r}")


def open_memory_kwargs(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> tuple[str, str, dict[str, Any] | None]:
    """Return ``(namespace, backend_type, backend_config)`` for ``Memory(...)``."""
    ns = f"agent_{agent_id}"
    resolved = memory_backend_from_agent_config(
        cfg, octop_config=octop_config, workspace_dir=workspace_dir
    )
    spec = resolved.get("memory_backend")
    if not isinstance(spec, dict):
        return ns, "sqlite", {"db_path": str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")}
    btype = str(spec.get("type") or "sqlite")
    if btype == "postgres":
        return ns, "postgres", {"dsn": spec["dsn"]}
    db_path = spec.get("db_path") or str(host_system_dir(workspace_dir, cfg) / "memory.sqlite")
    return ns, "sqlite", {"db_path": str(db_path)}


def memory_backend_choice(cfg: dict[str, Any]) -> MemoryBackendChoice:
    """Return the stored UI choice: omitted backend means follow the control plane."""
    mem = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    backend = mem.get("backend") if isinstance(mem, dict) else None
    if not isinstance(backend, dict):
        return "follow"
    btype = str(backend.get("type") or "").strip().lower()
    if btype == "sqlite":
        return "sqlite"
    if btype == "postgres":
        return "postgres"
    return "follow"


def normalize_memory_dsn(raw: str | None) -> str | None:
    """Return a stripped DSN, or None if empty. Reject non-postgres URLs."""
    text = (raw or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "memory postgres DSN must be postgresql://host[/database]",
        )
    return text


def build_memory_postgres_dsn(
    *,
    host: str,
    database: str,
    user: str,
    port: int = 5432,
    password: str | None = None,
) -> str:
    """Build a libpq URL from the same fields the setup wizard uses."""
    host_n = host.strip()
    database_n = database.strip()
    user_n = user.strip()
    if not host_n or not database_n or not user_n:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "memory postgres host, database, and user are required",
        )
    auth = quote_plus(user_n)
    if password:
        auth = f"{auth}:{quote_plus(password)}"
    return f"postgresql://{auth}@{host_n}:{int(port)}/{database_n}"


def probe_memory_postgres_dsn(dsn: str, *, timeout: int = 5) -> None:
    """Open a short-lived connection and run ``SELECT 1``. Does not persist config."""
    normalized = normalize_memory_dsn(dsn)
    if not normalized:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "memory postgres DSN is required")
    import psycopg  # noqa: PLC0415

    try:
        with psycopg.connect(normalized, connect_timeout=timeout) as con, con.cursor() as cur:
            cur.execute("SELECT 1")
    except OctopError:
        raise
    except Exception as exc:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"database connection failed: {exc}",
        ) from exc


def stored_memory_dsn(cfg: dict[str, Any]) -> str | None:
    backend = _stored_postgres_backend(cfg)
    if backend is None:
        return None
    raw = backend.get("dsn")
    return str(raw) if raw else None


def memory_postgres_connection_fields(dsn: str | None) -> dict[str, Any] | None:
    """Parse a DSN into wizard fields. Password is never returned."""
    text = (dsn or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return None
    host = parsed.hostname or ""
    database = unquote((parsed.path or "").lstrip("/"))
    user = unquote(parsed.username) if parsed.username else ""
    if not host or not database or not user:
        return None
    return {
        "host": host,
        "port": int(parsed.port or 5432),
        "database": database,
        "user": user,
    }


def _stored_postgres_backend(cfg: dict[str, Any]) -> dict[str, Any] | None:
    mem = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else None
    backend = mem.get("backend") if isinstance(mem, dict) else None
    if not isinstance(backend, dict):
        return None
    if str(backend.get("type") or "").strip().lower() != "postgres":
        return None
    return backend


def memory_config_for_choice(
    choice: str | None,
    octop_config: OctopConfig,
    *,
    dsn: str | None = None,
) -> dict[str, Any] | None:
    """Return the ``memory`` config section for a create-time choice, or None if follow."""
    normalized = (choice or "follow").strip().lower()
    if normalized not in _MEMORY_CHOICES:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported memory_backend: {choice!r}",
        )
    if normalized == "follow":
        return None
    applied = apply_memory_backend_choice({}, normalized, octop_config=octop_config, dsn=dsn)
    mem = applied.get("memory")
    return dict(mem) if isinstance(mem, dict) else None


def apply_memory_backend_choice(
    cfg: dict[str, Any],
    choice: str,
    *,
    octop_config: OctopConfig,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Return a copy of ``cfg`` with ``memory.backend`` set for ``choice``.

    ``follow`` drops only ``memory.backend`` so extract-trigger keys stay.
    PostgreSQL on a SQLite control plane requires an explicit DSN unless one
    is already stored.
    """
    normalized = (choice or "follow").strip().lower()
    if normalized not in _MEMORY_CHOICES:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported memory_backend: {choice!r}",
        )
    normalized_dsn = normalize_memory_dsn(dsn)

    out = dict(cfg)
    existing_mem = out.get("memory")
    mem = dict(existing_mem) if isinstance(existing_mem, dict) else {}
    if normalized == "follow":
        mem.pop("backend", None)
    elif normalized == "sqlite":
        mem["backend"] = {"type": "sqlite"}
    elif normalized_dsn:
        mem["backend"] = {"type": "postgres", "dsn": normalized_dsn}
    else:
        current = _stored_postgres_backend(out)
        if current and (current.get("dsn") or current.get("use_control_plane_dsn")):
            mem["backend"] = dict(current)
        elif octop_config.database.is_postgresql:
            mem["backend"] = {"type": "postgres", "use_control_plane_dsn": True}
        else:
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "memory.backend type=postgres requires a DSN when control plane is sqlite",
            )
    if mem:
        out["memory"] = mem
    else:
        out.pop("memory", None)
    memory_backend_from_agent_config(out, octop_config=octop_config)
    return out


def redact_memory_location(*, backend_type: str, db_path: str | None, dsn: str | None) -> str:
    """Human-readable store location without credentials."""
    if backend_type == "sqlite":
        return db_path or ""
    if not dsn:
        return "PostgreSQL"
    parsed = urlparse(dsn)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    database = (parsed.path or "").lstrip("/")
    if host and database:
        return f"{host}{port}/{database}"
    if host:
        return f"{host}{port}"
    return "PostgreSQL"


def describe_memory_store(
    *,
    agent_id: str,
    cfg: dict[str, Any],
    octop_config: OctopConfig,
    workspace_dir: Path,
) -> dict[str, Any]:
    """Describe where this agent's memory lives and whether any rows exist."""
    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=octop_config,
        workspace_dir=workspace_dir,
    )
    db_path = (backend_config or {}).get("db_path") if backend == "sqlite" else None
    dsn = (backend_config or {}).get("dsn") if backend == "postgres" else None
    has_data, has_data_unknown = memory_store_has_data(
        backend=backend,
        namespace=ns,
        db_path=str(db_path) if db_path else None,
        dsn=str(dsn) if dsn else None,
    )
    control_plane = "postgresql" if octop_config.database.is_postgresql else "sqlite"
    stored = _stored_postgres_backend(cfg)
    stored_dsn = stored_memory_dsn(cfg)
    connection = memory_postgres_connection_fields(
        stored_dsn or (str(dsn) if backend == "postgres" and dsn else None)
    )
    return {
        "choice": memory_backend_choice(cfg),
        "control_plane": control_plane,
        "resolved": {
            "type": backend,
            "location": redact_memory_location(
                backend_type=backend,
                db_path=str(db_path) if db_path else None,
                dsn=str(dsn) if dsn else None,
            ),
            "namespace": ns,
        },
        "has_data": has_data,
        "has_data_unknown": has_data_unknown,
        "has_custom_dsn": bool(stored and stored.get("dsn")),
        "connection": connection,
    }


def memory_store_has_data(
    *,
    backend: str,
    namespace: str,
    db_path: str | None = None,
    dsn: str | None = None,
) -> tuple[bool, bool]:
    """Return ``(has_data, unknown)``. Probe failure is ``(True, True)`` so the UI warns."""
    if not _NS_RE.fullmatch(namespace):
        return True, True
    try:
        if backend == "sqlite":
            return _sqlite_has_memory_rows(Path(db_path or ""), namespace), False
        if backend == "postgres":
            return _postgres_has_memory_rows(str(dsn or ""), namespace), False
    except Exception:
        logger.warning(
            "memory store occupancy probe failed backend=%s namespace=%s",
            backend,
            namespace,
            exc_info=True,
        )
        return True, True
    return False, False


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_has_memory_rows(db_path: Path, namespace: str) -> bool:
    if not db_path.is_file() or db_path.stat().st_size == 0:
        return False
    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        for table in _MEMORY_TABLES:
            name = f"{namespace}_{table}"
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone()
            if exists is None:
                continue
            if con.execute(f"SELECT 1 FROM {_quote_ident(name)} LIMIT 1").fetchone():
                return True
        return False
    finally:
        con.close()


def _postgres_has_memory_rows(dsn: str, namespace: str) -> bool:
    if not dsn:
        raise ValueError("postgres memory probe requires a DSN")
    import psycopg  # noqa: PLC0415

    with psycopg.connect(dsn) as con, con.cursor() as cur:
        for table in _MEMORY_TABLES:
            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'harness_memory' AND table_name = %s
                """,
                (table,),
            )
            if cur.fetchone() is None:
                continue
            cur.execute(
                f"SELECT 1 FROM harness_memory.{table} WHERE namespace = %s LIMIT 1",
                (namespace,),
            )
            if cur.fetchone() is not None:
                return True
    return False
