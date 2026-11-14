"""Read and write the process ``config.json`` without dropping unknown keys."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.config import (
    OctopConfig,
    _parse_database_url,
    _parse_tls_section,
    validate_persisted_config,
)
from octop.infra.desktop import desktop_shell_enabled
from octop.infra.errors import ErrorCode, OctopError, corrupt_config_error
from octop.infra.setup.self_update import green_packages_dir
from octop.infra.setup.service import detect_service_mode
from octop.infra.utils.json_file import JsonFileCorruptError, read_json_object, write_json_atomic

_MAX_BYTES = 1_048_576

# Env vars that override the matching config.json field at process start.
_ENV_OVERRIDE_KEYS = (
    "OCTOP_BIND_HOST",
    "OCTOP_PORT",
    "OCTOP_LOG_LEVEL",
    "OCTOP_ACCESS_TOKEN_TTL",
    "OCTOP_LOGIN_MAX_ATTEMPTS",
    "OCTOP_LOGIN_LOCKOUT_SECONDS",
    "OCTOP_DEFAULT_TIMEZONE",
    "OCTOP_CRON_TIMEZONE",
    "OCTOP_CORS_ORIGINS",
    "OCTOP_ENABLE_DASHBOARD",
    "OCTOP_ENABLE_API_DOCS",
    "OCTOP_REQUIRE_SETUP_PASSWORD",
    "OCTOP_MAX_UPLOAD_MB",
    "OCTOP_DATABASE_URL",
    "OCTOP_DATABASE_DRIVER",
    "OCTOP_DATABASE_SQLITE_PATH",
    "OCTOP_DATABASE_HOST",
    "OCTOP_DATABASE_PORT",
    "OCTOP_DATABASE_NAME",
    "OCTOP_DATABASE_USER",
    "OCTOP_DATABASE_PASSWORD",
)

_LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})


@dataclass(frozen=True)
class AppConfigSnapshot:
    path: str
    raw: str
    valid: bool
    error: str | None
    config: dict[str, Any] | None
    has_database_password: bool
    overrides: list[str]
    service_mode: str | None
    restart_available: bool


def active_config_env_overrides() -> list[str]:
    """Env vars that are set and therefore win over ``config.json`` after restart."""
    found: list[str] = []
    for key in _ENV_OVERRIDE_KEYS:
        raw = os.environ.get(key)
        if raw is not None and raw.strip() != "":
            found.append(key)
    return found


def restart_availability() -> tuple[str | None, bool]:
    """Service mode and whether ``POST /api/update/restart`` can restart this process."""
    mode = detect_service_mode()
    if desktop_shell_enabled():
        return mode, False
    desktop_flag = (os.environ.get("OCTOP_DESKTOP") or "").strip().lower()
    if green_packages_dir() is not None or desktop_flag in {"1", "true", "yes", "on"}:
        return "desktop", True
    return mode, mode is not None


def read_app_config(path: Path) -> AppConfigSnapshot:
    """Load the on-disk file. The structured view omits ``database.password``."""
    service_mode, can_restart = restart_availability()
    overrides = active_config_env_overrides()
    if not path.is_file():
        config, has_password = _display_config({})
        raw = json.dumps(config, indent=2) + "\n"
        return AppConfigSnapshot(
            path=str(path),
            raw=raw,
            valid=True,
            error=None,
            config=config,
            has_database_password=has_password,
            overrides=overrides,
            service_mode=service_mode,
            restart_available=can_restart,
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _invalid_snapshot(
            path,
            "",
            "not valid UTF-8",
            overrides,
            service_mode,
            can_restart,
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return _invalid_snapshot(
            path,
            text,
            f"line {exc.lineno}, column {exc.colno}",
            overrides,
            service_mode,
            can_restart,
        )
    if not isinstance(parsed, dict):
        return _invalid_snapshot(
            path,
            text,
            "expected a JSON object",
            overrides,
            service_mode,
            can_restart,
        )
    try:
        config, has_password = _display_config(parsed)
    except (TypeError, ValueError) as exc:
        return _invalid_snapshot(
            path,
            text,
            _safe_detail(exc),
            overrides,
            service_mode,
            can_restart,
        )
    return AppConfigSnapshot(
        path=str(path),
        raw=text if text.endswith("\n") else text + "\n",
        valid=True,
        error=None,
        config=config,
        has_database_password=has_password,
        overrides=overrides,
        service_mode=service_mode,
        restart_available=can_restart,
    )


def save_structured_config(path: Path, incoming: dict[str, Any]) -> None:
    """Merge the form payload into the existing file and keep unknown keys."""
    try:
        existing = read_json_object(path)
    except JsonFileCorruptError as exc:
        raise corrupt_config_error(exc.path, exc.detail) from exc
    if existing is None:
        existing = {}
    try:
        merged = _apply_structured(existing, incoming)
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid(_safe_detail(exc)) from exc
    _validate(merged)
    write_json_atomic(path, merged)


def save_raw_config(path: Path, text: str) -> None:
    """Replace the file with validated JSON. Formatting is normalized on write."""
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_BYTES:
        raise _invalid("file is larger than 1 MiB")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid(f"line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(parsed, dict):
        raise _invalid("config must be a JSON object")
    _validate(parsed)
    write_json_atomic(path, parsed)


def _validate(data: dict[str, Any]) -> None:
    try:
        validate_persisted_config(data)
    except ValueError as exc:
        raise _invalid(_safe_detail(exc)) from exc


def _invalid(detail: str) -> OctopError:
    return OctopError(ErrorCode.APP_CONFIG_INVALID, detail, details={"detail": detail})


def _safe_detail(exc: BaseException) -> str:
    text = str(exc).strip() or "invalid configuration"
    if len(text) > 240:
        return "invalid configuration"
    return text


def _invalid_snapshot(
    path: Path,
    raw: str,
    detail: str,
    overrides: list[str],
    service_mode: str | None,
    can_restart: bool,
) -> AppConfigSnapshot:
    return AppConfigSnapshot(
        path=str(path),
        raw=raw,
        valid=False,
        error=detail,
        config=None,
        has_database_password=False,
        overrides=overrides,
        service_mode=service_mode,
        restart_available=can_restart,
    )


def _display_config(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    base = OctopConfig()
    if "tls" in data and data["tls"] is not None and not isinstance(data["tls"], dict):
        raise ValueError("tls must be an object")
    if (
        "database" in data
        and data["database"] is not None
        and not isinstance(data["database"], dict)
    ):
        raise ValueError("database must be an object")
    db_in = data["database"] if isinstance(data.get("database"), dict) else {}
    has_password = bool(db_in.get("password"))
    driver = str(db_in.get("driver", base.database.driver) or "sqlite").strip().lower()
    if driver not in {"sqlite", "postgresql"}:
        driver = base.database.driver
    url = db_in.get("url")
    url_text = str(url).strip() if isinstance(url, str) and str(url).strip() else None
    tls = _parse_tls_section(data.get("tls"))
    level = str(data.get("log_level", base.log_level) or base.log_level).strip().lower()
    if level not in _LOG_LEVELS:
        level = base.log_level
    origins = data.get("cors_origins", base.cors_origins)
    if not isinstance(origins, list):
        raise ValueError("cors_origins must be a list of strings")
    config = {
        "bind_host": str(data.get("bind_host", base.bind_host) or base.bind_host),
        "port": _coerce_display_int(data.get("port", base.port), base.port),
        "log_level": level,
        "access_token_ttl_seconds": _coerce_display_int(
            data.get("access_token_ttl_seconds", base.access_token_ttl_seconds),
            base.access_token_ttl_seconds,
        ),
        "login_max_attempts": _coerce_display_int(
            data.get("login_max_attempts", base.login_max_attempts),
            base.login_max_attempts,
        ),
        "login_lockout_seconds": _coerce_display_int(
            data.get("login_lockout_seconds", base.login_lockout_seconds),
            base.login_lockout_seconds,
        ),
        "cors_origins": [str(item) for item in origins if str(item).strip()],
        "default_timezone": str(
            data.get("default_timezone", base.default_timezone) or base.default_timezone
        ),
        "enable_dashboard": _coerce_display_bool(
            data.get("enable_dashboard"), base.enable_dashboard
        ),
        "enable_api_docs": _coerce_display_bool(data.get("enable_api_docs"), base.enable_api_docs),
        "require_setup_password": _coerce_display_bool(
            data.get("require_setup_password"),
            base.require_setup_password,
        ),
        "max_upload_mb": _coerce_display_int(
            data.get("max_upload_mb", base.max_upload_mb), base.max_upload_mb
        ),
        "database": {
            "driver": driver,
            "sqlite_path": str(
                db_in.get("sqlite_path", base.database.sqlite_path) or base.database.sqlite_path
            ),
            "host": str(db_in.get("host", base.database.host) or base.database.host),
            "port": _coerce_display_int(db_in.get("port", base.database.port), base.database.port),
            "database": str(
                db_in.get("database", base.database.database) or base.database.database
            ),
            "user": str(db_in.get("user", base.database.user) or base.database.user),
            "password": None,
            "url": url_text,
        },
        "tls": {
            "enabled": tls.enabled,
            "mode": tls.mode,
            "domains": list(tls.domains),
            "cert_file": tls.cert_file,
            "key_file": tls.key_file,
            "issued_at": tls.issued_at,
            "expires_at": tls.expires_at,
            "acme_staging": tls.acme_staging,
            "http_port": tls.http_port,
        },
    }
    return config, has_password


def _coerce_display_int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("expected an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value.strip())
    raise ValueError("expected an integer")


def _coerce_display_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("expected a boolean")


def _apply_structured(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    out["bind_host"] = str(incoming.get("bind_host", "")).strip()
    out["port"] = int(incoming["port"])
    out["log_level"] = str(incoming.get("log_level", "info")).strip().lower()
    out["access_token_ttl_seconds"] = int(incoming["access_token_ttl_seconds"])
    out["login_max_attempts"] = int(incoming["login_max_attempts"])
    out["login_lockout_seconds"] = int(incoming["login_lockout_seconds"])
    origins = incoming.get("cors_origins") or []
    out["cors_origins"] = [str(item).strip() for item in origins if str(item).strip()]
    out["default_timezone"] = str(incoming.get("default_timezone", "")).strip()
    out["enable_dashboard"] = bool(incoming.get("enable_dashboard"))
    out["enable_api_docs"] = bool(incoming.get("enable_api_docs"))
    out["require_setup_password"] = bool(incoming.get("require_setup_password"))
    out["max_upload_mb"] = int(incoming["max_upload_mb"])
    out["database"] = _merge_database(existing.get("database"), incoming.get("database") or {})
    out["tls"] = _merge_tls(existing.get("tls"), incoming.get("tls") or {})
    return out


def _apply_password(section: dict[str, Any], password: object) -> None:
    if password == "":
        section.pop("password", None)
    elif isinstance(password, str) and password:
        section["password"] = password


def _merge_database(existing: object, incoming: dict[str, Any]) -> dict[str, Any]:
    section = dict(existing) if isinstance(existing, dict) else {}
    driver = str(incoming.get("driver", "sqlite")).strip().lower()
    sqlite_path = str(
        incoming.get("sqlite_path") or section.get("sqlite_path") or "octop.db"
    ).strip()
    section["sqlite_path"] = sqlite_path or "octop.db"
    if driver == "sqlite":
        section["driver"] = "sqlite"
        section.pop("url", None)
        _apply_password(section, incoming.get("password"))
        return section

    url_raw = incoming.get("url")
    url = str(url_raw).strip() if isinstance(url_raw, str) else ""
    section["driver"] = "postgresql"
    if url:
        parsed = _parse_database_url(url)
        section["host"] = parsed["host"]
        section["port"] = int(parsed["port"])
        section["database"] = parsed["database"]
        if parsed.get("user"):
            section["user"] = parsed["user"]
        section["url"] = url
        if parsed.get("password"):
            section["password"] = parsed["password"]
        else:
            section.pop("password", None)
        return section

    section.pop("url", None)
    section["host"] = str(incoming.get("host", "")).strip()
    section["port"] = int(incoming.get("port", 5432))
    section["database"] = str(incoming.get("database", "")).strip()
    section["user"] = str(incoming.get("user", "")).strip()
    _apply_password(section, incoming.get("password"))
    return section


def _merge_tls(existing: object, incoming: dict[str, Any]) -> dict[str, Any]:
    section = dict(existing) if isinstance(existing, dict) else {}
    domains = incoming.get("domains") or []
    section.update(
        {
            "enabled": bool(incoming.get("enabled")),
            "mode": str(incoming.get("mode", "")).strip(),
            "domains": [str(item).strip() for item in domains if str(item).strip()],
            "cert_file": str(incoming.get("cert_file", "")).strip(),
            "key_file": str(incoming.get("key_file", "")).strip(),
            "issued_at": str(incoming.get("issued_at", "")).strip(),
            "expires_at": str(incoming.get("expires_at", "")).strip(),
            "acme_staging": bool(incoming.get("acme_staging")),
            "http_port": int(incoming.get("http_port", 80)),
        }
    )
    return section
