"""Initial-admin setup wizard."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from octop.api.deps import get_server, resolve_user_from_token, sign_token
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.agents.providers.probe import make_probe_provider_row, probe_provider_row
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.setup import password_file as _wizard
from octop.infra.setup.wizard_tokens import RateLimited
from octop.infra.users.identity import Role
from octop.infra.utils.locale import normalize_locale, resolve_request_locale

logger = logging.getLogger(__name__)

router = APIRouter()


class VerifyBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class SetupBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    display_name: str | None = None
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


def _setup_password_required(server: Any) -> bool:
    return bool(server.services and server.services.config.require_setup_password)


def _enforce_wizard_open(server: Any) -> None:
    if server.user_manager.count() != 0:
        _wizard.remove_password(Path.home())
        raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)


def _enforce_wizard_token_phase(server: Any) -> None:
    """Allow wizard token operations while initial setup is still in progress."""
    if server.user_manager.count() > 1:
        raise OctopError(ErrorCode.SETUP_REQUIRED, "setup already completed", status=410)


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise OctopError(ErrorCode.AUTH_FAILED, "wizard token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise OctopError(ErrorCode.AUTH_FAILED, "wizard token required")
    return token


def _require_wizard_token(authorization: str | None, server: Any) -> str:
    token = _extract_bearer(authorization)
    if not server.wizard_tokens.validate(token):
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid or expired wizard token")
    return token


def _authorize_setup_provider_test(authorization: str | None, server: Any) -> None:
    """Accept wizard token or admin JWT while setup is still in progress."""
    _authorize_setup_mid_wizard(authorization, server)


def _authorize_setup_mid_wizard(authorization: str | None, server: Any) -> str | None:
    """Return wizard token when present; None when admin JWT is valid mid-setup."""
    token = _extract_bearer(authorization)
    if server.wizard_tokens.validate(token):
        return token
    if server.user_manager.count() == 1:
        try:
            user = resolve_user_from_token(server, token)
            if user.is_admin:
                return None
        except OctopError:
            pass
    raise OctopError(ErrorCode.AUTH_FAILED, "invalid or expired wizard token")


async def _bootstrap_default_agent(server: Any, *, user_id: int, locale: str = "zh") -> None:
    """Create the first default agent for a fresh install."""
    from octop.infra.agents.experts.catalog import build_create_spec_from_expert

    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    if registry.get_row("main") is not None:
        return
    if registry.list_agents(user_id):
        return
    catalog = server.expert_catalog
    expert = None if catalog is None else catalog.get("general-assistant")
    if expert is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "general-assistant expert template missing")
    loc = normalize_locale(locale)
    spec = build_create_spec_from_expert(
        expert_id="general-assistant",
        expert=expert,
        user_id=user_id,
        agent_id="main",
        locale=loc,
    )
    await registry.create(spec, defer_bootstrap=True)


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
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    """Return whether the Bearer wizard token is still valid (setup not yet completed)."""
    _enforce_wizard_token_phase(server)
    if not authorization or not authorization.startswith("Bearer "):
        return {"valid": False}
    token = authorization.removeprefix("Bearer ").strip()
    return {"valid": server.wizard_tokens.validate(token)}


@router.get("/setup/status", summary="Setup wizard status")
async def status(server: Any = Depends(get_server)) -> dict[str, Any]:
    """Whether initial admin creation is still required and wizard password file state."""
    wizard_path = str(Path.home() / _wizard.WIZARD_FILE_NAME)
    password_required = _setup_password_required(server)
    return {
        "setup_required": server.user_manager.count() == 0,
        "wizard_password_required": password_required,
        "wizard_password_exists": (
            password_required and _wizard.read_password(Path.home()) is not None
        ),
        "wizard_password_path": wizard_path if password_required else None,
    }


@router.post("/setup/begin", summary="Begin setup without wizard password")
async def begin_setup(server: Any = Depends(get_server)) -> dict[str, Any]:
    """Issue a wizard token when ``require_setup_password`` is disabled."""
    _enforce_wizard_open(server)
    if _setup_password_required(server):
        raise OctopError(ErrorCode.AUTH_FAILED, "setup password required")
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
        raise OctopError(ErrorCode.AUTH_FAILED, "setup password not required")
    client_ip = request.client.host if request.client else "unknown"
    try:
        server.wizard_tokens.record_attempt(client_ip)
    except RateLimited:
        raise OctopError(ErrorCode.AUTH_FAILED, "too many attempts", status=429) from None
    expected = _wizard.read_password(Path.home())
    if expected is None or body.password != expected:
        raise OctopError(ErrorCode.AUTH_FAILED, "wrong password")
    token, ttl = server.wizard_tokens.issue()
    return {"wizard_token": token, "expires_in": ttl}


@router.post("/setup/initial-admin", status_code=201, summary="Create initial admin")
async def initial_admin(
    body: SetupBody,
    request: Request,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create the first admin user. Default ``main`` agent is created at ``/setup/finish``."""
    _enforce_wizard_open(server)
    _require_wizard_token(authorization, server)
    locale = normalize_locale(body.locale or resolve_request_locale(request))
    user = await server.user_manager.create(
        username=body.username,
        password=body.password,
        role=Role.ADMIN,
        display_name=body.display_name,
        locale=locale,
    )
    _wizard.remove_password(Path.home())
    secret = server.services.secret_repo.get("jwt")
    ttl = server.services.config.access_token_ttl_seconds
    access_token = sign_token(
        secret, sub=user.id, uname=user.username, role=user.role.value, ttl_seconds=ttl
    )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "locale": user.locale,
        "access_token": access_token,
        "expires_in": ttl,
    }


@router.post("/setup/resume-wizard", summary="Issue a fresh wizard token mid-setup")
async def resume_wizard(server: Any = Depends(get_server)) -> dict[str, Any]:
    """Issue a new wizard token after the admin exists but before finish."""
    _enforce_wizard_token_phase(server)
    if server.user_manager.count() == 0:
        raise OctopError(ErrorCode.AUTH_FAILED, "admin not created yet", status=400)
    token, ttl = server.wizard_tokens.issue()
    return {"wizard_token": token, "expires_in": ttl}


@router.post("/setup/test-provider", summary="Test provider draft connectivity")
async def test_provider_draft(
    body: ProviderTestBody,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Probe LLM connectivity for an unsaved wizard provider draft."""
    _enforce_wizard_token_phase(server)
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
    return await probe_provider_row(row)


@router.post("/setup/finish", summary="Finish setup wizard")
async def finish(
    body: FinishBody,
    server: Any = Depends(get_server),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Apply optional provider draft, bootstrap default ``main`` agent, clear wizard token."""
    _enforce_wizard_token_phase(server)
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
    admin = next((u for u in users if u.is_admin), users[0] if users else None)
    if admin is not None:
        try:
            await _bootstrap_default_agent(server, user_id=admin.id, locale=admin.locale)
        except Exception as exc:  # pragma: no cover
            logger.warning("could not auto-create default agent: %s", exc)
    if wizard_token is not None:
        server.wizard_tokens.consume(wizard_token)
    return {"ok": True}
