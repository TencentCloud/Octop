"""Admin editor for the process ``config.json`` file."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.app_config import read_app_config, save_raw_config, save_structured_config
from octop.infra.server import OctopServer

router = APIRouter(prefix="/admin/app-config", tags=["admin"])


class DatabaseConfigBody(BaseModel):
    driver: Literal["sqlite", "postgresql"] = "sqlite"
    sqlite_path: str = "octop.db"
    host: str = "127.0.0.1"
    port: int = 5432
    database: str = "octop"
    user: str = "octop"
    password: str | None = Field(
        default=None,
        description="Null keeps the saved password, an empty string clears it, any other value replaces it.",
    )
    url: str | None = Field(
        default=None,
        description="PostgreSQL URL. When set, it replaces host, port, database, user, and password.",
    )


class TlsConfigBody(BaseModel):
    enabled: bool = False
    mode: str = ""
    domains: list[str] = Field(default_factory=list)
    cert_file: str = ""
    key_file: str = ""
    issued_at: str = ""
    expires_at: str = ""
    acme_staging: bool = False
    http_port: int = 80


class AppConfigBody(BaseModel):
    bind_host: str
    port: int
    log_level: str
    access_token_ttl_seconds: int
    login_max_attempts: int
    login_lockout_seconds: int
    cors_origins: list[str] = Field(default_factory=list)
    default_timezone: str
    enable_dashboard: bool
    enable_api_docs: bool
    require_setup_password: bool
    max_upload_mb: int
    database: DatabaseConfigBody
    tls: TlsConfigBody


class RawConfigBody(BaseModel):
    raw: str = Field(description="Full config.json document.")


class AppConfigView(BaseModel):
    path: str
    raw: str = Field(description="On-disk config.json text, including secrets.")
    valid: bool
    error: str | None = None
    config: AppConfigBody | None = None
    has_database_password: bool = False
    overrides: list[str] = Field(
        default_factory=list,
        description="Environment variables that override the file after restart.",
    )
    service_mode: str | None = None
    restart_available: bool = False


def _view(server: OctopServer) -> AppConfigView:
    snap = read_app_config(server.paths.config)
    config = AppConfigBody.model_validate(snap.config) if snap.config is not None else None
    return AppConfigView(
        path=snap.path,
        raw=snap.raw,
        valid=snap.valid,
        error=snap.error,
        config=config,
        has_database_password=snap.has_database_password,
        overrides=snap.overrides,
        service_mode=snap.service_mode,
        restart_available=snap.restart_available,
    )


@router.get("", summary="Read config.json", response_model=AppConfigView)
async def get_app_config(
    _: Any = Depends(require_permission("app_config")),
    server: OctopServer = Depends(get_server),
) -> AppConfigView:
    """Return the on-disk process config. ``database.password`` is omitted from the form payload."""
    return _view(server)


@router.put("", summary="Update config.json from the form", response_model=AppConfigView)
async def put_app_config(
    body: AppConfigBody,
    _: Any = Depends(require_permission("app_config")),
    server: OctopServer = Depends(get_server),
) -> AppConfigView:
    """Merge the form into config.json. Unknown keys such as plugins and backup are kept.

    The running process keeps its current settings until it is restarted.
    """
    save_structured_config(server.paths.config, body.model_dump())
    return _view(server)


@router.put("/raw", summary="Replace config.json text", response_model=AppConfigView)
async def put_raw_app_config(
    body: RawConfigBody,
    _: Any = Depends(require_permission("app_config")),
    server: OctopServer = Depends(get_server),
) -> AppConfigView:
    """Replace config.json after checking that the JSON object can be loaded.

    The file is rewritten with stable indentation. Restart to apply it.
    """
    save_raw_config(server.paths.config, body.raw)
    return _view(server)
