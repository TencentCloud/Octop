"""Process-level configuration (config.json + env overrides)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_VALID_DRIVERS = frozenset({"sqlite", "postgresql"})

_DATABASE_ENV_KEYS = (
    "OCTOP_DATABASE_URL",
    "OCTOP_DATABASE_DRIVER",
    "OCTOP_DATABASE_SQLITE_PATH",
    "OCTOP_DATABASE_HOST",
    "OCTOP_DATABASE_PORT",
    "OCTOP_DATABASE_NAME",
    "OCTOP_DATABASE_USER",
    "OCTOP_DATABASE_PASSWORD",
)


def database_env_configured() -> bool:
    """True when any ``OCTOP_DATABASE_*`` env var is set."""
    return any(os.environ.get(k) for k in _DATABASE_ENV_KEYS)


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection settings (SQLite today; PostgreSQL later)."""

    driver: str = "sqlite"
    sqlite_path: str = "octop.db"
    host: str = "127.0.0.1"
    port: int = 5432
    database: str = "octop"
    user: str = "octop"
    password: str | None = None

    @property
    def is_sqlite(self) -> bool:
        return self.driver == "sqlite"

    @property
    def is_postgresql(self) -> bool:
        return self.driver == "postgresql"

    def resolve_sqlite_path(self, octop_root: Path) -> Path:
        """Absolute path to the SQLite file (relative paths are under ``octop_root``)."""
        p = Path(self.sqlite_path)
        return p if p.is_absolute() else octop_root / p


@dataclass(frozen=True)
class TlsConfig:
    """TLS / Let's Encrypt settings persisted in config.json."""

    enabled: bool = False
    mode: str = ""
    domains: list[str] = field(default_factory=list)
    cert_file: str = ""
    key_file: str = ""
    issued_at: str = ""
    expires_at: str = ""
    acme_staging: bool = False
    http_port: int = 80


@dataclass(frozen=True)
class OctopConfig:
    bind_host: str = "127.0.0.1"
    port: int = 8088
    log_level: str = "info"
    access_token_ttl_seconds: int = 86400
    login_max_attempts: int = 5
    login_lockout_seconds: int = 900
    cors_origins: list[str] = field(default_factory=list)
    default_timezone: str = "Asia/Shanghai"
    enable_dashboard: bool = True
    enable_api_docs: bool = False
    require_setup_password: bool = True
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    # False when config.json omits ``database`` (use PathLayout.db unless env overrides).
    database_in_file: bool = False
    tls: TlsConfig = field(default_factory=TlsConfig)


def _defaults_for_file() -> dict[str, Any]:
    data = asdict(OctopConfig())
    data.pop("database_in_file", None)
    db = dict(data["database"])
    db.pop("password", None)
    data["database"] = db
    return data


def _parse_tls_section(raw: object) -> TlsConfig:
    if raw is None:
        return TlsConfig()
    if not isinstance(raw, dict):
        msg = f"config.tls must be an object, got {type(raw).__name__}"
        raise ValueError(msg)
    domains_raw = raw.get("domains") or []
    if not isinstance(domains_raw, list):
        msg = "config.tls.domains must be a list"
        raise ValueError(msg)
    return TlsConfig(
        enabled=bool(raw.get("enabled", False)),
        mode=str(raw.get("mode", "")),
        domains=[str(d).strip() for d in domains_raw if str(d).strip()],
        cert_file=str(raw.get("cert_file", "")),
        key_file=str(raw.get("key_file", "")),
        issued_at=str(raw.get("issued_at", "")),
        expires_at=str(raw.get("expires_at", "")),
        acme_staging=bool(raw.get("acme_staging", False)),
        http_port=int(raw.get("http_port", 80)),
    )


def _coerce_int(name: str, value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        logger.warning("env %s=%r is not int; using %s", name, value, default)
        return default


def _coerce_bool(name: str, value: str, default: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("env %s=%r is not bool; using %s", name, value, default)
    return default


def _parse_database_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        msg = f"OCTOP_DATABASE_URL scheme must be postgresql, got {parsed.scheme!r}"
        raise ValueError(msg)
    if not parsed.hostname:
        raise ValueError("OCTOP_DATABASE_URL missing host")
    if not parsed.path or parsed.path == "/":
        raise ValueError("OCTOP_DATABASE_URL missing database name in path")
    out: dict[str, Any] = {
        "driver": "postgresql",
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
    }
    if parsed.username:
        out["user"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def _parse_database_section(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"config.database must be an object, got {type(raw).__name__}"
        raise ValueError(msg)
    return raw


def parse_database_config(merged: dict[str, Any]) -> DatabaseConfig:
    """Validate and build ``DatabaseConfig`` from a merged dict (file + env)."""
    driver = str(merged.get("driver", "sqlite")).strip().lower()
    if driver not in _VALID_DRIVERS:
        allowed = ", ".join(sorted(_VALID_DRIVERS))
        msg = f"database.driver must be one of {allowed}, got {driver!r}"
        raise ValueError(msg)

    if driver == "sqlite":
        sqlite_path = str(merged.get("sqlite_path", "octop.db")).strip()
        if not sqlite_path:
            raise ValueError("database.sqlite_path must not be empty")
        return DatabaseConfig(driver=driver, sqlite_path=sqlite_path)

    host = str(merged.get("host", "")).strip()
    database = str(merged.get("database", "")).strip()
    user = str(merged.get("user", "")).strip()
    port = int(merged.get("port", 5432))
    if not host:
        raise ValueError("database.host is required for postgresql")
    if not database:
        raise ValueError("database.database is required for postgresql")
    if not user:
        raise ValueError("database.user is required for postgresql")
    if not (1 <= port <= 65535):
        raise ValueError(f"database.port must be 1-65535, got {port}")

    password = merged.get("password")
    if password is not None:
        password = str(password)
        if not password:
            password = None

    return DatabaseConfig(
        driver=driver,
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )


def _apply_database_env(merged_db: dict[str, Any]) -> dict[str, Any]:
    out = dict(merged_db)
    if v := os.environ.get("OCTOP_DATABASE_URL"):
        out.update(_parse_database_url(v))
    if v := os.environ.get("OCTOP_DATABASE_DRIVER"):
        out["driver"] = v.strip().lower()
    if v := os.environ.get("OCTOP_DATABASE_SQLITE_PATH"):
        out["sqlite_path"] = v
    if v := os.environ.get("OCTOP_DATABASE_HOST"):
        out["host"] = v
    if v := os.environ.get("OCTOP_DATABASE_PORT"):
        out["port"] = _coerce_int("OCTOP_DATABASE_PORT", v, int(out.get("port", 5432)))
    if v := os.environ.get("OCTOP_DATABASE_NAME"):
        out["database"] = v
    if v := os.environ.get("OCTOP_DATABASE_USER"):
        out["user"] = v
    if v := os.environ.get("OCTOP_DATABASE_PASSWORD"):
        out["password"] = v
    return out


def load_config(path: Path) -> OctopConfig:
    """Load ``config.json``; write defaults if absent. Apply env overrides."""
    file_defaults = _defaults_for_file()
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        database_in_file = "database" in raw
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(file_defaults, indent=2), encoding="utf-8")
        raw = {}
        database_in_file = False

    merged = {**file_defaults, **raw}
    # Legacy key: prefer default_timezone when both are present in the file.
    if "default_timezone" not in raw and "cron_timezone" in raw:
        merged["default_timezone"] = raw["cron_timezone"]
    merged.pop("cron_timezone", None)

    merged_db = {
        **file_defaults["database"],
        **_parse_database_section(raw.get("database")),
    }
    merged_db = _apply_database_env(merged_db)

    if v := os.environ.get("OCTOP_BIND_HOST"):
        merged["bind_host"] = v
    if v := os.environ.get("OCTOP_PORT"):
        merged["port"] = _coerce_int("OCTOP_PORT", v, merged["port"])
    if v := os.environ.get("OCTOP_LOG_LEVEL"):
        merged["log_level"] = v
    if v := os.environ.get("OCTOP_ACCESS_TOKEN_TTL"):
        merged["access_token_ttl_seconds"] = _coerce_int(
            "OCTOP_ACCESS_TOKEN_TTL", v, merged["access_token_ttl_seconds"]
        )
    if v := os.environ.get("OCTOP_LOGIN_MAX_ATTEMPTS"):
        merged["login_max_attempts"] = _coerce_int(
            "OCTOP_LOGIN_MAX_ATTEMPTS", v, merged.get("login_max_attempts", 5)
        )
    if v := os.environ.get("OCTOP_LOGIN_LOCKOUT_SECONDS"):
        merged["login_lockout_seconds"] = _coerce_int(
            "OCTOP_LOGIN_LOCKOUT_SECONDS", v, merged.get("login_lockout_seconds", 900)
        )
    if (v := os.environ.get("OCTOP_DEFAULT_TIMEZONE")) or (
        v := os.environ.get("OCTOP_CRON_TIMEZONE")
    ):
        merged["default_timezone"] = v
    if v := os.environ.get("OCTOP_CORS_ORIGINS"):
        merged["cors_origins"] = [s.strip() for s in v.split(",") if s.strip()]
    if v := os.environ.get("OCTOP_ENABLE_DASHBOARD"):
        merged["enable_dashboard"] = _coerce_bool(
            "OCTOP_ENABLE_DASHBOARD", v, bool(merged["enable_dashboard"])
        )
    if v := os.environ.get("OCTOP_ENABLE_API_DOCS"):
        merged["enable_api_docs"] = _coerce_bool(
            "OCTOP_ENABLE_API_DOCS", v, bool(merged["enable_api_docs"])
        )
    if v := os.environ.get("OCTOP_REQUIRE_SETUP_PASSWORD"):
        merged["require_setup_password"] = _coerce_bool(
            "OCTOP_REQUIRE_SETUP_PASSWORD", v, bool(merged["require_setup_password"])
        )

    return OctopConfig(
        bind_host=merged["bind_host"],
        port=int(merged["port"]),
        log_level=merged["log_level"],
        access_token_ttl_seconds=int(merged["access_token_ttl_seconds"]),
        login_max_attempts=int(merged.get("login_max_attempts", 5)),
        login_lockout_seconds=int(merged.get("login_lockout_seconds", 900)),
        cors_origins=list(merged.get("cors_origins") or []),
        default_timezone=str(merged.get("default_timezone") or "Asia/Shanghai"),
        enable_dashboard=bool(merged["enable_dashboard"]),
        enable_api_docs=bool(merged["enable_api_docs"]),
        require_setup_password=bool(merged["require_setup_password"]),
        database=parse_database_config(merged_db),
        database_in_file=database_in_file,
        tls=_parse_tls_section(raw.get("tls")),
    )
