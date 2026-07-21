"""Providers router (admin-only write operations)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from octop.api.deps import current_admin, current_user, get_server
from octop.infra.agents.providers.presets import load_provider_presets
from octop.infra.agents.providers.probe import (
    make_probe_provider_row,
    probe_provider_row,
)
from octop.infra.agents.providers.resolved import list_resolved_models as _list_resolved_models
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.providers.codex_apply import (
    CODEX_PROVIDER_NAME,
    apply_codex_credentials,
    sync_refreshed_codex_api_key,
)
from octop.infra.providers.codex_oauth import (
    exchange_authorization_code,
    get_valid_access_token,
    prepare_pkce_authorize,
)
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderCreateBody(BaseModel):
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    extra_json: str | None = None
    models: list[dict[str, Any]] | None = None
    note: str | None = None


class ProviderPatchBody(BaseModel):
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    extra_json: str | None = None
    models: list[dict[str, Any]] | None = None
    note: str | None = None
    enabled: bool | None = None


# Fields that affect harness factory / agent runtime when patched.
_PROVIDER_REHYDRATE_FIELDS = frozenset(
    {"kind", "base_url", "api_key", "extra_json", "models", "enabled"}
)


def _patch_requires_provider_rehydrate(body: ProviderPatchBody) -> bool:
    """True when the patch touches fields that require ``on_provider_changed``."""
    return bool(body.model_fields_set & _PROVIDER_REHYDRATE_FIELDS)


class ProviderTestBody(BaseModel):
    model_id: str | None = None


class ProviderTestDraftBody(BaseModel):
    name: str
    kind: str
    api_key: str | None = None
    base_url: str | None = None
    model_id: str
    extra_json: str | None = None


class CodexOAuthStartBody(BaseModel):
    redirect_after: str | None = None


def _provider_headers(row: Any) -> dict[str, str]:
    raw = getattr(row, "extra_json", None)
    if not raw:
        return {}
    try:
        extra = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(extra, dict):
        return {}
    headers = extra.get("headers")
    return dict(headers) if isinstance(headers, dict) else {}


def _is_codex_base_url(base_url: str | None) -> bool:
    return bool(base_url and "chatgpt.com/backend-api/codex" in base_url)


async def _maybe_refresh_codex_row(server: Any, row: Any) -> Any:
    if row.name != CODEX_PROVIDER_NAME and not _is_codex_base_url(row.base_url):
        return row
    paths = server.services.paths
    token = await asyncio.to_thread(get_valid_access_token, paths)
    if not token:
        return row
    if row.api_key != token:
        sync_refreshed_codex_api_key(server.services, paths, token)
        refreshed = server.services.provider_repo.get(row.id)
        return refreshed if refreshed is not None else row
    return row


def _row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "kind": r.kind,
        "base_url": r.base_url,
        "api_key": r.api_key,
        "models": r.get_models(),
        "note": r.note,
        "enabled": bool(r.enabled),
    }


@router.get("/presets")
async def list_provider_presets(
    _: Any = Depends(current_user),
) -> list[dict[str, Any]]:
    """Return built-in provider presets from harness-agent."""
    return load_provider_presets()


@router.get("/resolved")
async def list_resolved_models(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Return all enabled models across all providers.

    Used by the Agent model selector to show available candidates.
    """
    return _list_resolved_models(server.services.provider_repo.list_all())


class ActiveModelBody(BaseModel):
    provider_name: str
    model: str


@router.get("/active-model")
async def get_active_model(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """Return the globally preferred model (provider_name + model id)."""
    name, model = server.services.settings_repo.get_active_model()
    return {"provider_name": name, "model": model}


@router.put("/active-model")
async def set_active_model(
    body: ActiveModelBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """Set the globally preferred model used when no agent override applies."""
    server.services.settings_repo.set_active_model(body.provider_name, body.model)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.on_provider_changed(active_model_changed=True)
    return {"provider_name": body.provider_name, "model": body.model}


@router.get("")
async def list_providers(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Return all providers. Read-only for regular users."""
    return [_row_to_dict(r) for r in server.services.provider_repo.list_all()]


@router.get("/codex-oauth/callback", summary="ChatGPT OAuth callback")
async def codex_oauth_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    server: Any = Depends(get_server),
) -> HTMLResponse:
    """OAuth redirect target for ChatGPT Codex login. No JWT required."""
    if error:
        return HTMLResponse(f"<html><body>授权失败: {error}</body></html>", status_code=400)
    if not code or not state:
        return HTMLResponse("<html><body>缺少 code 或 state</body></html>", status_code=400)

    settings = server.services.settings_repo
    flow_raw = settings.get(f"codex_oauth.flow.{state}")
    if not flow_raw:
        return HTMLResponse("<html><body>无效或过期的 OAuth 会话</body></html>", status_code=400)
    try:
        flow = json.loads(flow_raw)
    except json.JSONDecodeError:
        return HTMLResponse("<html><body>OAuth 会话损坏</body></html>", status_code=400)

    state_id = flow.get("state_id")
    verifier = flow.get("verifier")
    redirect_after = flow.get("redirect_after") or "/admin/models"
    if not state_id or not verifier:
        return HTMLResponse("<html><body>OAuth 会话不完整</body></html>", status_code=400)

    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/providers/codex-oauth/callback"
    try:
        cred = await asyncio.to_thread(
            exchange_authorization_code,
            code=code,
            verifier=verifier,
            redirect_uri=redirect_uri,
        )
        pid = apply_codex_credentials(server.services, server.services.paths, cred)
        if server.app_runtime is not None:
            await server.app_runtime.agent_registry.on_provider_changed(
                provider_name=CODEX_PROVIDER_NAME,
            )
        settings.set(
            f"codex_oauth.pending.{state_id}",
            json.dumps(
                {
                    "status": "ok",
                    "provider_id": pid,
                    "provider_name": CODEX_PROVIDER_NAME,
                    "user_id": flow.get("user_id"),
                }
            ),
        )
        settings.delete(f"codex_oauth.flow.{state}")
    except Exception as exc:
        logger.exception("codex oauth callback failed")
        settings.set(
            f"codex_oauth.pending.{state_id}",
            json.dumps({"status": "error", "error": str(exc), "user_id": flow.get("user_id")}),
        )

    return HTMLResponse(
        f"""<!DOCTYPE html><html><body><script>
window.opener && window.opener.postMessage({{ type: 'octop:codex-oauth', state_id: '{state_id}' }}, '*');
window.location.href = '{redirect_after}?codex_oauth={state_id}';
</script><p>登录完成，正在返回…</p></body></html>"""
    )


# ── Admin endpoints ─────────────────────────────────────────────────────────

admin_router = APIRouter()


@admin_router.get("")
async def admin_list_providers(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    return [_row_to_dict(r) for r in server.services.provider_repo.list_all()]


@admin_router.post("", status_code=201)
async def admin_create_provider(
    body: ProviderCreateBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    import json as _json

    models_json = _json.dumps(body.models) if body.models is not None else None
    pid = server.services.provider_repo.create(
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_json=body.extra_json,
        models_json=models_json,
        note=body.note,
    )
    if server.app_runtime:
        await server.app_runtime.agent_registry.on_provider_changed(provider_name=body.name)
    return _row_to_dict(server.services.provider_repo.get(pid))


@admin_router.patch("/{provider_id}")
async def admin_patch_provider(
    provider_id: int,
    body: ProviderPatchBody,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    row = server.services.provider_repo.get(provider_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    import json as _json

    models_json = _json.dumps(body.models) if body.models is not None else None
    server.services.provider_repo.update(
        provider_id,
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
        extra_json=body.extra_json,
        models_json=models_json,
        note=body.note,
        enabled=body.enabled,
    )
    if server.app_runtime and _patch_requires_provider_rehydrate(body):
        await server.app_runtime.agent_registry.on_provider_changed(provider_name=row.name)
    return _row_to_dict(server.services.provider_repo.get(provider_id))


@admin_router.delete("/{provider_id}", status_code=204)
async def admin_delete_provider(
    provider_id: int,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    row = server.services.provider_repo.get(provider_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    refs = server.app_runtime.agent_registry.find_agents_using_provider(row.name)
    if refs:
        raise OctopError(
            ErrorCode.PROVIDER_REFERENCED,
            f"provider {row.name!r} is referenced by {len(refs)} agent(s)",
            details={"agents": refs},
        )
    name = row.name
    server.services.provider_repo.delete(provider_id)
    if server.app_runtime:
        await server.app_runtime.agent_registry.on_provider_changed(provider_name=name)


@admin_router.post("/test-draft", summary="Test unsaved provider draft")
async def admin_test_provider_draft(
    body: ProviderTestDraftBody,
    _: Any = Depends(current_admin),
) -> dict[str, Any]:
    """Probe connectivity for a provider draft before it is saved."""
    api_key = (body.api_key or "").strip()
    if not api_key:
        return {"ok": False, "error": "api_key is required"}
    model_id = body.model_id.strip()
    if not model_id:
        return {"ok": False, "error": "model_id is required"}
    row = make_probe_provider_row(
        name=body.name.strip() or "draft",
        kind=body.kind,
        api_key=api_key,
        base_url=(body.base_url or "").strip() or None,
        model_id=model_id,
        extra_json=body.extra_json,
    )
    return await probe_provider_row(row, model_id=model_id)


@admin_router.post("/codex-oauth/start", summary="Start ChatGPT OAuth login")
async def codex_oauth_start(
    body: CodexOAuthStartBody,
    request: Request,
    user: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/providers/codex-oauth/callback"
    authorize_url, pkce_state, verifier = prepare_pkce_authorize(redirect_uri=redirect_uri)
    state_id = new_ulid()
    server.services.settings_repo.set(
        f"codex_oauth.flow.{pkce_state}",
        json.dumps(
            {
                "state_id": state_id,
                "verifier": verifier,
                "user_id": user.id,
                "redirect_after": body.redirect_after or "/admin/models",
            }
        ),
    )
    return {"authorize_url": authorize_url, "state_id": state_id}


@admin_router.get("/codex-oauth/pending/{state_id}", summary="Poll ChatGPT OAuth result")
async def codex_oauth_pending(
    state_id: str,
    user: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    raw = server.services.settings_repo.get(f"codex_oauth.pending.{state_id}")
    if not raw:
        return {"status": "pending"}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "corrupt oauth pending") from None
    flow_user = payload.get("user_id")
    if flow_user is not None and flow_user != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your oauth session")
    return cast(dict[str, Any], payload)


@admin_router.delete("/codex-oauth", status_code=204, summary="Clear ChatGPT OAuth login")
async def codex_oauth_logout(
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> None:
    from octop.infra.providers.codex_oauth import delete_codex_token

    delete_codex_token(server.services.paths)
    row = server.services.provider_repo.get_by_name(CODEX_PROVIDER_NAME)
    if row is not None:
        server.services.provider_repo.update(row.id, api_key=None)
        if server.app_runtime is not None:
            await server.app_runtime.agent_registry.on_provider_changed(
                provider_name=CODEX_PROVIDER_NAME,
            )


@admin_router.post("/{provider_id}/test")
async def admin_test_provider(
    provider_id: int,
    body: ProviderTestBody | None = None,
    _: Any = Depends(current_admin),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe a provider by sending a one-token ping and timing it."""
    row = server.services.provider_repo.get(provider_id)
    if row is None:
        raise OctopError(ErrorCode.NOT_FOUND, "provider not found")
    row = await _maybe_refresh_codex_row(server, row)
    model_id = body.model_id if body else None
    return await probe_provider_row(row, model_id=model_id)
