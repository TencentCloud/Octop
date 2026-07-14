"""Connector and agent-binding HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.connectors.builder import (
    mcp_server_name,
    normalize_weiyun_mcp_token,
    validate_create_credentials,
)
from octop.infra.connectors.catalog import (
    catalog_entry_to_dict,
    get_catalog_entry,
    list_catalog,
)
from octop.infra.connectors.oauth import (
    auth_info_for_kind,
    delete_oauth_ctx,
    exchange_oauth_code,
    exchange_pasted_auth_code,
    load_oauth_ctx,
    oauth_ready_for_kind,
    save_oauth_ctx,
    start_oauth,
)
from octop.infra.connectors.probe import prepare_probe_credentials, probe_connector
from octop.infra.connectors.service import ConnectorService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateInstanceBody(BaseModel):
    kind: str
    display_name: str
    credentials: dict[str, Any] = Field(default_factory=dict)


class PatchInstanceBody(BaseModel):
    status: str | None = None


class OAuthStartBody(BaseModel):
    redirect_after: str | None = None


class ExchangeAuthCodeBody(BaseModel):
    code: str
    bkn: str | None = None
    knowledge_base_id: str | None = None


class TestCredentialsBody(BaseModel):
    kind: str
    credentials: dict[str, Any] = Field(default_factory=dict)


def _connector_service(server: Any) -> ConnectorService:
    return ConnectorService(
        repo=server.services.repos.connector_repo,
        secret_repo=server.services.secret_repo,
        settings_repo=server.services.settings_repo,
        config=server.services.config,
    )


def _instance_to_dict(inst: Any) -> dict[str, Any]:
    return {
        "instance_id": inst.instance_id,
        "kind": inst.kind,
        "display_name": inst.display_name,
        "status": inst.status,
        "mcp_server_name": inst.mcp_server_name,
        "has_credentials": inst.has_credentials,
        "created_at": inst.created_at,
        "updated_at": inst.updated_at,
    }


async def _prepare_credentials(
    kind: str,
    credentials: dict[str, Any],
    settings_repo: Any,
) -> dict[str, Any]:
    entry = get_catalog_entry(kind)
    if entry is None:
        raise ValueError(f"unknown connector kind: {kind}")
    cred_payload = dict(credentials)
    if entry.auth_kind == "auth_code" and cred_payload.get("code"):
        code = str(cred_payload.pop("code")).strip()
        extra = {
            k: cred_payload.pop(k) for k in ("bkn", "knowledge_base_id") if cred_payload.get(k)
        }
        exchanged = await exchange_pasted_auth_code(
            kind=kind,
            code=code,
            settings_repo=settings_repo,
            extra=extra or None,
        )
        cred_payload.update(exchanged)
    elif entry.kind == "tencent-weiyun" and entry.auth_kind == "personal_token":
        raw = str(cred_payload.get("token") or cred_payload.get("access_token") or "").strip()
        token = normalize_weiyun_mcp_token(raw)
        if not token:
            raise ValueError("token is required")
        cred_payload = {"token": token}
    return validate_create_credentials(kind, cred_payload)


def _merge_credentials(
    old: dict[str, Any],
    new: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(old)
    for key, value in new.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def _credentials_preview(kind: str, creds: dict[str, Any]) -> dict[str, Any]:
    entry = get_catalog_entry(kind)
    if entry is None or not creds:
        return {}
    preview: dict[str, Any] = {}
    if entry.auth_kind == "personal_token":
        if entry.kind == "tencent-weiyun":
            if str(creds.get("token") or "").strip():
                preview["token_configured"] = True
        elif str(creds.get("token") or creds.get("access_token") or "").strip():
            preview["token_configured"] = True
    elif entry.auth_kind == "oauth2":
        if str(creds.get("access_token") or "").strip():
            preview["oauth_configured"] = True
        if creds.get("expires_at") is not None:
            preview["expires_at"] = creds.get("expires_at")
    elif entry.auth_kind == "auth_code":
        if str(creds.get("access_token") or creds.get("cookie") or "").strip():
            preview["auth_configured"] = True
        if creds.get("bkn"):
            preview["bkn"] = str(creds["bkn"])
        if creds.get("knowledge_base_id"):
            preview["knowledge_base_id"] = str(creds["knowledge_base_id"])
    elif entry.auth_kind == "api_key":
        if str(creds.get("api_key") or "").strip():
            preview["api_key_configured"] = True
        # Legacy tencent-news instances stored the key as ``cookie``.
        if kind == "tencent-news" and str(creds.get("cookie") or "").strip():
            preview["api_key_configured"] = True
        if kind == "tencent-ima" and creds.get("client_id"):
            preview["client_id"] = str(creds["client_id"])
        if kind == "tencent-lexiang":
            company_from = creds.get("company_from") or creds.get("client_id")
            if company_from:
                preview["client_id"] = str(company_from)
    elif entry.auth_kind == "imap_app_password":
        if creds.get("email"):
            preview["email"] = str(creds["email"])
        if creds.get("mail_provider"):
            preview["mail_provider"] = str(creds["mail_provider"])
        if creds.get("imap_host"):
            preview["imap_host"] = str(creds["imap_host"])
        if creds.get("smtp_host"):
            preview["smtp_host"] = str(creds["smtp_host"])
        if str(creds.get("password") or "").strip():
            preview["password_configured"] = True
    elif entry.auth_kind == "api_credentials":
        if creds.get("app_id"):
            preview["app_id"] = str(creds["app_id"])
        if creds.get("sdk_id"):
            preview["sdk_id"] = str(creds["sdk_id"])
        if str(creds.get("secret_key") or "").strip():
            preview["secret_key_configured"] = True
    return preview


def _schedule_connector_reload(server: Any, user_id: int) -> None:
    assert server.app_runtime is not None

    async def _run() -> None:
        try:
            await server.app_runtime.agent_registry.reload_connectors_for_user(user_id)
        except Exception:
            logger.exception("background connector reload failed for user %s", user_id)

    asyncio.create_task(_run())


@router.get("/connectors/catalog", summary="Connector catalog")
async def get_catalog(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List supported connector kinds and whether OAuth is configured for each."""
    del user
    settings = server.services.settings_repo
    return [
        catalog_entry_to_dict(e, oauth_ready=oauth_ready_for_kind(e.kind, settings))
        for e in list_catalog()
    ]


@router.get("/connector-instances", summary="List connector instances")
async def list_instances(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List the current user's connected third-party accounts."""
    rows = _connector_service(server).list_user_instances(user.id)
    return [_instance_to_dict(inst) for inst in rows]


@router.get("/connector-instances/{instance_id}", summary="Get connector instance")
async def get_instance(
    instance_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return one connector instance with config and a redacted credentials preview."""
    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")

    data = _instance_to_dict(inst)
    config: dict[str, Any] = {}
    if inst.config_json:
        try:
            parsed = json.loads(inst.config_json)
            if isinstance(parsed, dict):
                config = parsed
        except json.JSONDecodeError:
            config = {}
    data["config"] = config
    if inst.has_credentials:
        svc = _connector_service(server)
        creds = svc.decrypt(instance_id)
        data["credentials_preview"] = _credentials_preview(inst.kind, creds)
    else:
        data["credentials_preview"] = {}
    return data


@router.post("/connector-instances", status_code=201, summary="Create connector instance")
async def create_instance(
    body: CreateInstanceBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Connect a third-party account. Replaces any existing instance of the same kind."""
    entry = get_catalog_entry(body.kind)
    if entry is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {body.kind!r}")
    if entry.phase != "available":
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"{body.kind} not available")

    repo = server.services.repos.connector_repo
    svc = _connector_service(server)
    cred_input = dict(body.credentials)
    for old in repo.list_by_user(user.id):
        if old.kind == body.kind:
            if old.has_credentials:
                cred_input = _merge_credentials(svc.decrypt(old.instance_id), cred_input)
            repo.delete(old.instance_id)
            break

    try:
        cred_payload = await _prepare_credentials(
            body.kind, cred_input, server.services.settings_repo
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc

    instance_id = new_ulid()
    repo.create(
        instance_id=instance_id,
        user_id=user.id,
        kind=body.kind,
        display_name=body.display_name.strip(),
        mcp_server_name=mcp_server_name(body.kind, instance_id),
        config_json=json.dumps({"email": cred_payload.get("email")})
        if body.kind == "qq-mail"
        else None,
    )
    svc.encrypt_and_store(instance_id=instance_id, payload=cred_payload)
    server.services.audit_repo.write(
        actor=user.username,
        action="connector.instance.create",
        target=instance_id,
        payload=body.kind,
    )
    inst = repo.get(instance_id)
    assert inst is not None
    _schedule_connector_reload(server, user.id)
    return _instance_to_dict(inst)


@router.patch("/connector-instances/{instance_id}", summary="Update connector instance")
async def patch_instance(
    instance_id: str,
    body: PatchInstanceBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Enable or disable a connector instance without deleting credentials."""
    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
    if body.status is not None:
        status = body.status.strip()
        if status not in ("active", "disabled"):
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "status must be active or disabled"
            )
        repo.update_status(instance_id, status)
    inst = repo.get(instance_id)
    assert inst is not None
    _schedule_connector_reload(server, user.id)
    return _instance_to_dict(inst)


@router.delete("/connector-instances/{instance_id}", status_code=204, summary="Delete connector")
async def delete_instance(
    instance_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Disconnect and delete stored credentials for a connector instance."""
    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
    user_id = inst.user_id
    repo.delete(instance_id)
    _schedule_connector_reload(server, user_id)
    server.services.audit_repo.write(
        actor=user.username,
        action="connector.instance.delete",
        target=instance_id,
    )


@router.post("/connector-instances/{instance_id}/test", summary="Test connector")
async def test_instance(
    instance_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe the connector with stored credentials and return success or error details."""
    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")

    entry = get_catalog_entry(inst.kind)
    if entry is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, inst.kind)

    svc = _connector_service(server)
    creds = await svc.ensure_fresh_credentials(instance_id, inst.kind)
    if not creds:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "missing credentials")

    try:
        return await probe_connector(
            entry,
            creds,
            instance_id=instance_id,
            config=server.services.config,
        )
    except Exception as exc:
        logger.exception("connector test failed for %s", instance_id)
        return {"ok": False, "error": str(exc)}


@router.post("/connectors/test-credentials", summary="Test credentials")
async def test_credentials(
    body: TestCredentialsBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Validate credentials before creating an instance (no persistence)."""
    del user
    entry = get_catalog_entry(body.kind)
    if entry is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {body.kind!r}")
    if entry.phase != "available":
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"{body.kind} not available")
    try:
        cred_payload = await prepare_probe_credentials(
            body.kind,
            body.credentials,
            full_prepare=lambda k, c: _prepare_credentials(k, c, server.services.settings_repo),
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    try:
        return await probe_connector(
            entry,
            cred_payload,
            instance_id="probe",
            config=server.services.config,
        )
    except Exception as exc:
        logger.exception("connector credential test failed for %s", body.kind)
        return {"ok": False, "error": str(exc)}


@router.post("/connector-instances/{instance_id}/refresh", summary="Refresh OAuth tokens")
async def refresh_instance(
    instance_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Refresh expiring OAuth tokens for a connector instance."""
    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
    svc = _connector_service(server)
    creds = await svc.ensure_fresh_credentials(instance_id, inst.kind)
    return {"ok": True, "expires_at": creds.get("expires_at")}


@router.get("/connectors/auth/{kind}/info", summary="Connector auth info")
async def auth_info(
    kind: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str | None]:
    """Return auth flow metadata (OAuth URLs, required fields) for a connector kind."""
    del user
    if get_catalog_entry(kind) is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {kind!r}")
    return auth_info_for_kind(kind, server.services.settings_repo)


@router.get("/connectors/auth/{kind}/authorize-url", summary="OAuth authorize URL")
async def auth_authorize_url(
    kind: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str | None]:
    """Build the provider authorization URL for manual or embedded OAuth."""
    del user
    if get_catalog_entry(kind) is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {kind!r}")
    info = auth_info_for_kind(kind, server.services.settings_repo)
    return {"authorize_url": info.get("authorize_url")}


@router.post("/connectors/auth/{kind}/exchange-code", summary="Exchange auth code")
async def auth_exchange_code(
    kind: str,
    body: ExchangeAuthCodeBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Exchange a pasted authorization code for connector credentials (device/OOB flow)."""
    del user
    entry = get_catalog_entry(kind)
    if entry is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {kind!r}")
    if entry.auth_kind != "auth_code":
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"{kind} does not use auth code")
    try:
        extra: dict[str, Any] = {}
        if body.bkn:
            extra["bkn"] = body.bkn
        if body.knowledge_base_id:
            extra["knowledge_base_id"] = body.knowledge_base_id
        tokens = await exchange_pasted_auth_code(
            kind=kind,
            code=body.code,
            settings_repo=server.services.settings_repo,
            extra=extra or None,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    return {"credentials": tokens}


@router.post("/connectors/oauth/{kind}/start", summary="Start OAuth flow")
async def oauth_start(
    kind: str,
    body: OAuthStartBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Begin browser OAuth: returns `authorize_url` and `state_id` to poll after redirect."""
    if not oauth_ready_for_kind(kind, server.services.settings_repo):
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            f"OAuth for {kind} is not available",
        )

    state = secrets.token_urlsafe(24)
    state_id = new_ulid()
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/connectors/oauth/callback"

    try:
        authorize_url, verifier, ctx = await start_oauth(
            kind=kind,
            redirect_uri=redirect_uri,
            state=state,
            settings_repo=server.services.settings_repo,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    except Exception as exc:
        logger.exception("oauth start failed for %s", kind)
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            f"无法启动 OAuth: {exc}",
        ) from exc

    server.services.repos.connector_repo.create_oauth_state(
        state_id=state_id,
        state=state,
        user_id=user.id,
        kind=kind,
        code_verifier=verifier,
        redirect_after=body.redirect_after,
    )
    save_oauth_ctx(server.services.settings_repo, state_id, ctx)
    return {"authorize_url": authorize_url, "state_id": state_id}


@router.get("/connectors/oauth/callback", summary="OAuth callback")
async def oauth_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    server: Any = Depends(get_server),
) -> HTMLResponse:
    """OAuth redirect target. Exchanges the code and stores credentials. No JWT required."""
    if error:
        return HTMLResponse(f"<html><body>授权失败: {error}</body></html>", status_code=400)
    if not code or not state:
        return HTMLResponse("<html><body>缺少 code 或 state</body></html>", status_code=400)

    repo = server.services.repos.connector_repo
    row = repo.consume_oauth_state(state)
    if row is None:
        return HTMLResponse("<html><body>无效或过期的 state</body></html>", status_code=400)

    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/api/connectors/oauth/callback"

    try:
        tokens = await exchange_oauth_code(
            kind=row.kind,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=row.code_verifier,
            settings_repo=server.services.settings_repo,
            state_id=row.state_id,
        )
        ctx = load_oauth_ctx(server.services.settings_repo, row.state_id)
        if ctx.get("client_id"):
            tokens["oauth_client_id"] = ctx["client_id"]
        if ctx.get("client_secret"):
            tokens["oauth_client_secret"] = ctx["client_secret"]
        delete_oauth_ctx(server.services.settings_repo, row.state_id)
    except Exception as exc:
        logger.exception("oauth callback failed for %s", row.kind)
        return HTMLResponse(f"<html><body>Token 交换失败: {exc}</body></html>", status_code=400)

    # Store tokens in a short-lived settings key for frontend pickup, or auto-create instance.
    pending_key = f"connector.oauth.pending.{row.state_id}"
    server.services.settings_repo.set(
        pending_key,
        json.dumps({"user_id": row.user_id, "kind": row.kind, "tokens": tokens}),
    )
    redirect = row.redirect_after or "/connectors"
    html = f"""<!DOCTYPE html><html><body>
<script>
  if (window.opener) {{
    window.opener.postMessage({{ type: 'octop:connector-oauth', state_id: '{row.state_id}' }}, '*');
    window.close();
  }} else {{
    window.location.href = '{redirect}?oauth_state={row.state_id}';
  }}
</script>
<p>授权完成，可关闭此窗口。</p>
</body></html>"""
    return HTMLResponse(html)


@router.get("/connectors/oauth/pending/{state_id}", summary="Poll OAuth result")
async def oauth_pending(
    state_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Poll after OAuth redirect until credentials are ready for instance creation."""
    key = f"connector.oauth.pending.{state_id}"
    raw = server.services.settings_repo.get(key)
    if not raw:
        raise OctopError(ErrorCode.NOT_FOUND, "pending oauth not found")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "corrupt pending oauth") from exc
    if int(data.get("user_id") or 0) != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your oauth session")
    server.services.settings_repo.delete(key)
    return {"kind": data.get("kind"), "tokens": data.get("tokens") or {}}


async def validate_chat_mcp_servers(
    server: Any,
    *,
    user_id: int,
    names: list[str] | None,
) -> list[str] | None:
    from octop.api.common.validators import validate_chat_mcp_servers as _validate

    return await _validate(server, user_id=user_id, names=names)
