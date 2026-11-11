"""Initial-admin setup wizard."""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_database, resolve_user_from_token, sign_token
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.agents.providers.probe import make_probe_provider_row, probe_provider_row
from octop.infra.desktop import desktop_shell_enabled
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup import password_file as _wizard
from octop.infra.setup.wizard_tokens import RateLimited
from octop.infra.users.identity import Role
from octop.infra.utils.locale import normalize_locale, resolve_request_locale

logger = logging.getLogger(__name__)

router = APIRouter()

# Username the desktop wizard pre-fills. A session for this user skips login.
LOCAL_DESKTOP_USERNAME = "local"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})


class VerifyBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class SetupBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Required while the wizard password gate is on. Optional when "
            "``require_setup_password`` is off: the server then mints an "
            "unguessable one, so the admin row keeps a hashed credential "
            "without a password the client has to hold."
        ),
    )
    display_name: str | None = None
    email: str | None = Field(default=None, max_length=254)
    locale: str | None = Field(
        default=None,
        description="UI locale for the initial admin (zh|en). Defaults to Accept-Language.",
    )


class ProviderModelDraft(BaseModel):
    id: str
    name: str
    enabled: bool = True
    input: list[str] = Field(default_factory=list)
    thinking: Any | None = None
    reasoning: bool | None = None


class ProviderDraftBody(BaseModel):
    name: str
    type: str
    api_key: str = ""
    base_url: str | None = None
    models: list[ProviderModelDraft] = Field(default_factory=list)
    extras: dict[str, Any] | None = None


class FinishBody(BaseModel):
    provider_draft: ProviderDraftBody | None = None


class ProviderTestBody(BaseModel):
    name: str
    type: str
    api_key: str = ""
    base_url: str | None = None
    model_id: str = Field(min_length=1)


class DatabaseSetupBody(BaseModel):
    driver: str = Field(description="sqlite | postgresql")
    sqlite_path: str | None = None
    host: str | None = None
    port: int = 5432
    database: str | None = None
    user: str | None = None
    password: str | None = None
    url: str | None = None
    adopt_existing: bool = Field(
        default=False,
        description="PostgreSQL only: bind a database that already has users and keep those accounts.",
    )

    def as_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"driver": self.driver.strip().lower()}
        if self.sqlite_path is not None:
            out["sqlite_path"] = self.sqlite_path
        if self.host is not None:
            out["host"] = self.host
        out["port"] = self.port
        if self.database is not None:
            out["database"] = self.database
        if self.user is not None:
            out["user"] = self.user
        if self.password is not None:
            out["password"] = self.password
        if self.url is not None:
            out["url"] = self.url
        return out


def _setup_password_required(server: Any) -> bool:
    cfg = server.services.config if server.services else getattr(server, "config", None)
    return bool(cfg and cfg.require_setup_password)


def _resolve_admin_password(server: Any, provided: str | None) -> str:
    """Return the password to hash for the initial admin.

    With the wizard password gate on, the client must supply one. With the gate
    off (desktop builds), a missing password becomes a random one: the row still
    carries a real hash, but the JWT issued below is the only way in.
    """
    if provided:
        return provided
    if _setup_password_required(server):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "password is required")
    return secrets.token_urlsafe(32)


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _desktop_local_account(request: Request, server: Any) -> bool:
    """Desktop shell adding the ``local`` account beside users that already exist.

    The password gate stays off, and the caller is the shell on loopback. A
    browser deployment of the same database does not enter this path.
    """
    if not desktop_shell_enabled() or _setup_password_required(server):
        return False
    return _client_host(request) in _LOOPBACK_HOSTS


def _enforce_wizard_open(server: Any) -> None:
    um = server.user_manager
    if um is not None and um.count() != 0:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)


def _enforce_wizard_token_phase(request: Request, server: Any) -> None:
    """Allow wizard token operations while initial setup is still in progress.

    Creating the desktop ``local`` account keeps the token valid after that
    user is added next to accounts that were already there.
    """
    um = server.user_manager
    if um is None or um.count() <= 1:
        return
    if _desktop_local_account(request, server):
        return
    raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise OctopError(ErrorCode.SETUP_TOKEN_INVALID, "wizard token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise OctopError(ErrorCode.SETUP_TOKEN_INVALID, "wizard token required")
    return token


def _require_wizard_token(authorization: str | None, server: Any) -> str:
    token = _extract_bearer(authorization)
    if not server.wizard_tokens.validate(token):
        raise OctopError(ErrorCode.SETUP_TOKEN_INVALID, "invalid or expired wizard token")
    return token


def _authorize_setup_provider_test(authorization: str | None, server: Any) -> None:
    """Accept wizard token or admin JWT while setup is still in progress."""
    _authorize_setup_mid_wizard(authorization, server)


def _authorize_setup_mid_wizard(authorization: str | None, server: Any) -> str | None:
    """Return wizard token when present; None when admin JWT is valid mid-setup."""
    token = _extract_bearer(authorization)
    if server.wizard_tokens.validate(token):
        return token
    um = server.user_manager
    if um is not None and um.count() == 1:
        try:
            user = resolve_user_from_token(server, token)
            if user.is_admin:
                return None
        except OctopError:
            pass
    raise OctopError(ErrorCode.SETUP_TOKEN_INVALID, "invalid or expired wizard token")


async def _bootstrap_default_agent(
    server: Any,
    *,
    user_id: int,
    locale: str = "zh",
    pin_main: bool = True,
) -> None:
    """Create the first default agent for a user.

    Fresh setup pins ``main``. A desktop ``local`` account added later leaves
    the id unset so an existing ``main`` stays with its owner. Workspace root
    comes from that user's policy inside ``bootstrap_first_expert``.
    """
    from octop.infra.agents.experts.default_agent import (  # noqa: PLC0415
        SETUP_DEFAULT_AGENT_ID,
        bootstrap_first_expert,
    )

    if server.app_runtime is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "app_runtime not ready")
    await bootstrap_first_expert(
        server,
        user_id=user_id,
        locale=locale,
        agent_id=SETUP_DEFAULT_AGENT_ID if pin_main else None,
    )


async def _apply_provider_draft(server: Any, draft: ProviderDraftBody) -> None:
    """Persist provider config from the wizard and reload harness providers."""
    api_key = (draft.api_key or "").strip()
    base_url = (draft.base_url or "").strip()
    if not api_key:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "api_key is required", status=400)
    if not base_url:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "base_url is required", status=400)

    def _model_entry(m: ProviderModelDraft) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": m.id,
            "name": m.name,
            "enabled": m.enabled,
            "input": m.input,
            "thinking": m.thinking,
        }
        if m.reasoning:
            entry["reasoning"] = True
        return entry

    models = [_model_entry(m) for m in draft.models if m.enabled]
    if not models and draft.models:
        models = [_model_entry(draft.models[0])]
        models[0]["enabled"] = True
    if not models:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "at least one model is required", status=400)
    server.services.provider_repo.create(
        name=draft.name,
        kind=draft.type,
        base_url=base_url,
        api_key=api_key,
        models_json=json.dumps(models),
        extra_json=json.dumps(draft.extras) if draft.extras else None,
    )
    server.services.settings_repo.set_active_model(draft.name, models[0]["id"])
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.on_provider_changed()


@router.get("/setup/presets", summary="List provider presets")
async def setup_presets() -> list[dict[str, Any]]:
    """Built-in LLM provider templates for the setup wizard (no auth required)."""
    return load_provider_presets()


@router.get("/setup/validate-token", summary="Check wizard session token")
async def validate_wizard_token(
    request: Request,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    """Return whether the Bearer wizard token is still valid (setup not yet completed)."""
    _enforce_wizard_token_phase(request, server)
    if not authorization or not authorization.startswith("Bearer "):
        return {"valid": False}
    token = authorization.removeprefix("Bearer ").strip()
    return {"valid": server.wizard_tokens.validate(token)}


@router.get("/setup/status", summary="Setup wizard status")
async def status(server: Any = Depends(get_server)) -> dict[str, Any]:
    """Whether initial setup is still required, and whether the desktop local account exists."""
    wizard_path = str(_wizard.resolve_password_path(server.paths.root, legacy_home=Path.home()))
    password_required = _setup_password_required(server)
    um = server.user_manager
    setup_required = um is None or um.count() == 0
    database_driver = None
    if server.database_bound and server.services is not None:
        database_driver = server.services.config.database.driver
    local_account = (
        desktop_shell_enabled() and um is not None and um.get(LOCAL_DESKTOP_USERNAME) is not None
    )
    return {
        "setup_required": setup_required,
        "local_account": local_account,
        "wizard_password_required": password_required,
        "wizard_password_exists": (
            password_required
            and _wizard.read_password(server.paths.root, legacy_home=Path.home()) is not None
        ),
        "wizard_password_path": wizard_path if password_required else None,
        "database_driver": database_driver,
        "database_bound": server.database_bound,
    }


@router.post("/setup/test-database", summary="Probe control-plane database connectivity")
async def test_database(
    body: DatabaseSetupBody,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Validate DSN/settings with a short-lived pool (does not replace the process pool)."""
    _enforce_wizard_open(server)
    from octop.infra.db.probe import probe_database
    from octop.infra.db.rebind import database_config_from_payload

    try:
        db_cfg = database_config_from_payload(body.as_payload())
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
    user_count = probe_database(db_cfg, server.paths)
    return {"ok": True, "driver": db_cfg.driver, "user_count": user_count}


@router.post("/setup/database", summary="Persist control-plane database and bind")
async def apply_database(
    body: DatabaseSetupBody,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Write ``config.json`` database section, open the pool, migrate, and boot runtime.

    First-run path binds once (no prior pool). If already bound with zero users
    (e.g. changing engine mid-wizard), swaps via rebind. PostgreSQL may adopt a
    database that already has users when ``adopt_existing`` is set; SQLite still
    requires an empty file.
    """
    _enforce_wizard_open(server)
    from octop.infra.db.probe import probe_database
    from octop.infra.db.rebind import (
        assert_control_plane_database_empty,
        database_config_from_payload,
        persist_database_config,
        rebind_control_plane,
    )

    try:
        db_cfg = database_config_from_payload(body.as_payload())
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
    probe_database(db_cfg, server.paths)
    adopt = bool(body.adopt_existing) and db_cfg.is_postgresql
    if not adopt:
        assert_control_plane_database_empty(db_cfg, server.paths)
    persist_database_config(server.paths.config, db_cfg)
    if server.database_bound:
        rebind_control_plane(server, adopt_existing=adopt)
    else:
        await server.bind_control_plane()
    assert server.services is not None
    assert server.user_manager is not None
    return {
        "ok": True,
        "driver": server.services.config.database.driver,
        "adopted": server.user_manager.count() != 0,
    }


@router.post("/setup/begin", summary="Begin setup without wizard password")
async def begin_setup(request: Request, server: Any = Depends(get_server)) -> dict[str, Any]:
    """Issue a wizard token when ``require_setup_password`` is disabled.

    The desktop shell may also begin the guide to add the ``local`` account
    after other users already exist.
    """
    um = server.user_manager
    if um is not None and um.count() != 0:
        if not _desktop_local_account(request, server):
            raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)
    elif _setup_password_required(server):
        raise OctopError(ErrorCode.FORBIDDEN, "setup password required")
    token, ttl = server.wizard_tokens.issue()
    return {"wizard_token": token, "expires_in": ttl}


@router.post("/setup/verify-password", summary="Verify wizard password")
async def verify_password(
    body: VerifyBody,
    request: Request,
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Validate the CLI-generated wizard password and return a short-lived wizard token."""
    _enforce_wizard_open(server)
    if not _setup_password_required(server):
        raise OctopError(ErrorCode.FORBIDDEN, "setup password not required")
    client_ip = request.client.host if request.client else "unknown"
    try:
        server.wizard_tokens.record_attempt(client_ip)
    except RateLimited:
        raise OctopError(ErrorCode.SETUP_RATE_LIMITED, "too many attempts") from None
    expected = _wizard.read_password(server.paths.root, legacy_home=Path.home())
    if expected is None or body.password != expected:
        raise OctopError(ErrorCode.SETUP_PASSWORD_WRONG, "wrong password")
    token, ttl = server.wizard_tokens.issue()
    return {"wizard_token": token, "expires_in": ttl}


@router.post("/setup/initial-admin", status_code=201, summary="Create initial admin")
async def initial_admin(
    body: SetupBody,
    request: Request,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create the first admin user. Default ``main`` agent is created at ``/setup/finish``.

    On the desktop shell, the same call may add the ``local`` account when
    other users already exist. Any other username stays refused.
    """
    um = server.user_manager
    existing = um is not None and um.count() != 0
    if existing and (
        not _desktop_local_account(request, server) or body.username != LOCAL_DESKTOP_USERNAME
    ):
        raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)
    require_database(server)
    _require_wizard_token(authorization, server)
    locale = normalize_locale(body.locale or resolve_request_locale(request))
    assert server.user_manager is not None
    assert server.services is not None
    from octop.infra.db.repos.user_roles import ADMIN_USER_ROLE_ID, UserRoleRepo

    admin_role = UserRoleRepo(server.services.db).get(ADMIN_USER_ROLE_ID)
    user = await server.user_manager.create(
        username=body.username,
        password=_resolve_admin_password(server, body.password),
        role=Role.ADMIN,
        display_name=body.display_name,
        email=body.email,
        locale=locale,
        role_name=admin_role.user_role_name if admin_role is not None else "管理员",
    )
    from octop.infra.auth.tokens import PURPOSE_ACCESS

    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    row = server.services.user_repo.get(user.id)
    mfa_version = int(row.mfa_version) if row is not None else 0
    password_version = int(row.password_version) if row is not None else 0
    access_token = sign_token(
        secret,
        sub=user.id,
        uname=user.username,
        role=user.role,
        purpose=PURPOSE_ACCESS,
        ttl_seconds=ttl,
        mfa_version=mfa_version,
        password_version=password_version,
    )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "locale": user.locale,
        "access_token": access_token,
        "expires_in": ttl,
    }


@router.post("/setup/test-provider", summary="Test provider draft connectivity")
async def test_provider_draft(
    body: ProviderTestBody,
    request: Request,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Probe LLM connectivity for an unsaved wizard provider draft."""
    _enforce_wizard_token_phase(request, server)
    _authorize_setup_provider_test(authorization, server)
    if not body.api_key.strip():
        return {"ok": False, "error": "api_key is required"}
    row = make_probe_provider_row(
        name=body.name,
        kind=body.type,
        api_key=body.api_key or None,
        base_url=body.base_url,
        model_id=body.model_id,
    )
    return await probe_provider_row(row, locale=resolve_request_locale(request))


@router.post("/setup/finish", summary="Finish setup wizard")
async def finish(
    body: FinishBody,
    request: Request,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Apply optional provider draft, bootstrap default ``main`` agent, clear wizard token."""
    _enforce_wizard_token_phase(request, server)
    require_database(server)
    assert server.user_manager is not None
    wizard_token = _authorize_setup_mid_wizard(authorization, server)
    if body.provider_draft is not None:
        try:
            await _apply_provider_draft(server, body.provider_draft)
        except OctopError:
            raise
        except Exception as exc:
            logger.exception("setup provider bootstrap failed")
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"failed to save provider: {exc}",
            ) from exc
    users = server.user_manager.list()
    local_user = server.user_manager.get(LOCAL_DESKTOP_USERNAME)
    adding_local = (
        server.user_manager.count() > 1
        and local_user is not None
        and _desktop_local_account(request, server)
    )
    if adding_local and local_user is not None:
        try:
            await _bootstrap_default_agent(
                server, user_id=local_user.id, locale=local_user.locale, pin_main=False
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("could not auto-create default agent: %s", exc)
    else:
        admin = next((u for u in users if u.is_admin), users[0] if users else None)
        if admin is not None:
            try:
                await _bootstrap_default_agent(server, user_id=admin.id, locale=admin.locale)
            except Exception as exc:  # pragma: no cover
                logger.warning("could not auto-create default agent: %s", exc)
    if wizard_token is not None:
        server.wizard_tokens.consume(wizard_token)
    return {"ok": True}
