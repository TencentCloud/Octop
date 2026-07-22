"""Hot-rebind the control-plane database pool during first-run setup."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop.config import DatabaseConfig, OctopConfig, load_config, parse_database_config
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

if TYPE_CHECKING:
    from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def persist_database_config(config_path: Path, db_config: DatabaseConfig) -> OctopConfig:
    """Merge ``database`` into ``config.json`` and return the reloaded config."""
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.INTERNAL_ERROR, "config.json must be a JSON object")
    else:
        raw = {}

    section: dict[str, Any] = {"driver": db_config.driver}
    if db_config.is_sqlite:
        section["sqlite_path"] = db_config.sqlite_path
    else:
        if db_config.url:
            # Prefer discrete fields for file persistence; keep url only if advanced.
            section["host"] = db_config.host
            section["port"] = db_config.port
            section["database"] = db_config.database
            section["user"] = db_config.user
            if db_config.password:
                section["password"] = db_config.password
            # Persist url when query params matter (e.g. sslmode).
            if "?" in db_config.url:
                section["url"] = db_config.url
        else:
            section["host"] = db_config.host
            section["port"] = db_config.port
            section["database"] = db_config.database
            section["user"] = db_config.user
            if db_config.password:
                section["password"] = db_config.password

    raw["database"] = section
    _atomic_write_json(config_path, raw)
    return load_config(config_path)


def database_config_from_payload(payload: dict[str, Any]) -> DatabaseConfig:
    """Validate a setup/API payload into ``DatabaseConfig``."""
    from octop.config import _parse_database_url

    out = dict(payload)
    raw_url = out.get("url")
    if raw_url:
        parsed = _parse_database_url(str(raw_url))
        # URL fields fill gaps; explicit payload keys win for non-url keys already set.
        for key, value in parsed.items():
            out.setdefault(key, value)
        out["url"] = str(raw_url)
    return parse_database_config(out)


def assert_control_plane_database_empty(db_config: DatabaseConfig, paths: PathLayout) -> None:
    """Refuse greenfield setup onto a control-plane DB that already has users."""
    from octop.config import OctopConfig

    cfg = OctopConfig(database=db_config, database_in_file=True)
    db = open_database(cfg, paths)
    try:
        run_migrations(db)
        with db.connect() as conn:
            n = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    finally:
        db.close()
    if n != 0:
        raise OctopError(
            ErrorCode.DATABASE_NOT_EMPTY,
            "target database already has users",
            status=409,
        )


def rebind_control_plane(server: OctopServer) -> None:
    """Close the current pool, open from config, migrate, and retarget runtime repos.

    Only allowed while ``user_count == 0`` (first-run setup). Target DB must also
    be empty (greenfield); otherwise raise ``DATABASE_NOT_EMPTY`` without swapping.
    """
    if server.user_manager is None or server.services is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "server not started")
    if server.user_manager.count() != 0:
        raise OctopError(
            ErrorCode.SETUP_REQUIRED,
            "cannot change database after setup has users",
            status=410,
        )

    config = load_config(server.paths.config)
    old_db = server.services.db
    new_db = open_database(config, server.paths)
    try:
        run_migrations(new_db)
        with new_db.connect() as conn:
            n = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        if n != 0:
            raise OctopError(
                ErrorCode.DATABASE_NOT_EMPTY,
                "target database already has users",
                status=409,
            )
    except Exception:
        new_db.close()
        raise

    new_services = build_shared_services(db=new_db, paths=server.paths, config=config)
    try:
        old_db.close()
    except Exception:
        logger.exception("failed closing previous database pool during rebind")

    server.services = new_services
    if server.app_runtime is not None:
        server.app_runtime.replace_services(new_services, config)
    server._ensure_jwt_secret()  # noqa: SLF001 — re-seed secrets on empty DB
    logger.info("control-plane database rebound to driver=%s", config.database.driver)
