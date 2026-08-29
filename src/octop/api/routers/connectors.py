"""Connector and agent-binding HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from octop.api.common.public_base import resolve_public_base
from octop.api.deps import current_user, get_server, require_permission
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
from octop.infra.connectors.custom_mcp import (
    CUSTOM_MCP_KIND,
    is_custom_mcp_kind,
    oauth_configured,
    parse_synthetic_instance_id,
    redact_servers_for_api,
)
from octop.infra.connectors.default_open import (
    build_instance_config_json,
    read_default_open,
)
from octop.infra.connectors.gateway.cli_dirs import cleanup_creds_cli_dirs, cleanup_keys_for_creds
from octop.infra.connectors.gateway.cli_install import (
    cli_install_status,
    get_cli_install_spec,
    install_connector_cli,
)
from octop.infra.connectors.gateway.feishu_user_auth import live_user_auth_preview
from octop.infra.connectors.oauth import (
    auth_info_for_kind,
    delete_oauth_ctx,
    exchange_oauth_code,
    exchange_pasted_auth_code,
    load_oauth_ctx,
    oauth_ready_for_kind,
    save_oauth_ctx,
    start_oauth_for_target,
)
from octop.infra.connectors.oauth.registry import (
    oauth_state_kind_for_target,
    oauth_target_requires_https,
)
from octop.infra.connectors.probe import (
    detect_local_weknora,
    prepare_probe_credentials,
    probe_connector,
    probe_custom_mcp_server,
)
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.repos.connectors import ConnectorRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateInstanceBody(BaseModel):
    kind: str
    display_name: str
    credentials: dict[str, Any] = Field(default_factory=dict)
    default_open: bool = Field(
        default=False,
        description=(
            "Per-account default: when true, inject this connector's tools for "
            "the owner on IM and on Cron jobs with no explicit connector picks. "
            "Dashboard and Cron with explicit picks follow the selection."
        ),
    )


class PatchInstanceBody(BaseModel):
    status: str | None = None
    default_open: bool | None = Field(
        default=None,
        description=(
            "When set, update per-account default-open. IM / empty Cron follow "
            "it for this user; Dashboard and Cron with explicit picks use the "
            "selection."
        ),
    )


class OAuthStartBody(BaseModel):
    redirect_after: str | None = None
    target: dict[str, Any] | None = Field(
        default=None,
        description='OAuth target, e.g. {"type":"catalog","kind":"notion"} or '
        '{"type":"custom_mcp","server_name":"my-server"}',
    )


class OAuthStartLegacyBody(BaseModel):
    redirect_after: str | None = None


class ExchangeAuthCodeBody(BaseModel):
    code: str
    bkn: str | None = None
    knowledge_base_id: str | None = None


class TestCredentialsBody(BaseModel):
    kind: str
    credentials: dict[str, Any] = Field(default_factory=dict)


class FeishuUserAuthStartBody(BaseModel):
    app_id: str
    app_secret: str
    cli_config_key: str | None = None
    domains: list[str] | None = None


class FeishuUserAuthCompleteBody(BaseModel):
    app_id: str
    app_secret: str
    device_code: str
    cli_config_key: str | None = None


class CustomMcpPutBody(BaseModel):
    servers: dict[str, Any] = Field(default_factory=dict)


class CustomMcpServerPatchBody(BaseModel):
    enabled: bool | None = None
    default_open: bool | None = None

    @model_validator(mode="after")
    def _require_one_field(self) -> CustomMcpServerPatchBody:
        if self.enabled is None and self.default_open is None:
            raise ValueError("provide enabled and/or default_open")
        return self


class CustomMcpTestBody(BaseModel):
    """Probe one server by name (saved) or by inline spec."""

    name: str | None = None
    server: dict[str, Any] | None = None


def _resolve_custom_mcp_url(svc: ConnectorService, user_id: int, server_name: str) -> str:
    saved = svc.get_custom_servers(user_id)
    raw = saved.get(server_name)
    if not isinstance(raw, dict):
        raise OctopError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"custom MCP server {server_name!r} not found; save configuration before OAuth",
        )
    if str(raw.get("transport") or "") not in ("streamable_http", "http"):
        raise OctopError(
            ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
            "OAuth is only supported for streamable HTTP custom MCP servers",
        )
    mcp_url = str(raw.get("url") or "").strip()
    if not mcp_url:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "server url is required")
    return mcp_url


async def _begin_oauth_flow(
    *,
    request: Request,
    user: Any,
    server: Any,
    target: dict[str, Any],
    redirect_after: str | None,
) -> dict[str, Any]:
    target_type = str(target.get("type") or "").strip()
    if target_type == "catalog":
        kind = str(target.get("kind") or "").strip()
        if not oauth_ready_for_kind(kind, server.services.settings_repo):
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                f"OAuth for {kind} is not available",
            )
    elif target_type != "custom_mcp":
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "unsupported oauth target")

    state = secrets.token_urlsafe(24)
    state_id = new_ulid()
    base = resolve_public_base(request)
    redirect_uri = f"{base}/api/connectors/oauth/callback"
    if oauth_target_requires_https(target) and _is_public_http_uri(redirect_uri):
        label = str(target.get("kind") or target.get("server_name") or "MCP")
        raise OctopError(
            ErrorCode.CONNECTOR_OAUTH_HTTPS_REQUIRED,
            f"{label} OAuth callbacks require HTTPS for non-loopback addresses",
        )

    mcp_url: str | None = None
    if target_type == "custom_mcp":
        server_name = str(target.get("server_name") or "").strip()
        if not server_name:
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                "custom_mcp target requires server_name",
            )
        mcp_url = _resolve_custom_mcp_url(_connector_service(server), user.id, server_name)

    try:
        authorize_url, verifier, ctx = await start_oauth_for_target(
            target=target,
            redirect_uri=redirect_uri,
            state=state,
            settings_repo=server.services.settings_repo,
            mcp_url=mcp_url,
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    except Exception as exc:
        logger.exception("oauth start failed for target %s", target)
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            f"无法启动 OAuth: {exc}",
        ) from exc

    server.services.repos.connector_repo.create_oauth_state(
        state_id=state_id,
        state=state,
        user_id=user.id,
        kind=oauth_state_kind_for_target(target),
        code_verifier=verifier,
        redirect_after=redirect_after,
    )
    save_oauth_ctx(server.services.settings_repo, state_id, ctx)
    return {"authorize_url": authorize_url, "state_id": state_id}


def _connector_service(server: Any) -> ConnectorService:
    return ConnectorService(
        repo=server.services.repos.connector_repo,
        secret_repo=server.services.secret_repo,
        settings_repo=server.services.settings_repo,
        config=server.services.config,
    )


def _instance_to_dict(inst: Any) -> dict[str, Any]:
    config = ConnectorRepo.parse_config_json(inst) if hasattr(inst, "config_json") else {}
    return {
        "instance_id": inst.instance_id,
        "kind": inst.kind,
        "display_name": inst.display_name,
        "status": inst.status,
        "mcp_server_name": inst.mcp_server_name,
        "has_credentials": inst.has_credentials,
        "default_open": read_default_open(config),
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
        if kind == "feishu-cli" and creds.get("app_id"):
            preview["app_id"] = str(creds["app_id"])
            if str(creds.get("app_secret") or "").strip():
                preview["app_secret_configured"] = True
            default_as = str(creds.get("default_as") or "bot").strip().lower()
            preview["default_as"] = "user" if default_as == "user" else "bot"
            if default_as == "user":
                preview["user_auth_configured"] = True
            if creds.get("cli_config_key"):
                preview["cli_config_key"] = str(creds["cli_config_key"])
        if kind == "wecom-cli" and creds.get("bot_id"):
            preview["bot_id"] = str(creds["bot_id"])
            if str(creds.get("bot_secret") or "").strip():
                preview["bot_secret_configured"] = True
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
    elif entry.auth_kind == "custom_fields":
        for field in entry.credential_fields:
            value = creds.get(field.key)
            if field.secret:
                if str(value or "").strip():
                    preview[f"{field.key}_configured"] = True
            elif value not in (None, "", []):
                preview[field.key] = value
    return preview


def _schedule_connector_reload(server: Any, user_id: int) -> None:
    assert server.app_runtime is not None

    async def _run() -> None:
        try:
            await server.app_runtime.agent_registry.reload_connectors_for_user(user_id)
        except Exception:
            logger.exception("background connector reload failed for user %s", user_id)

    asyncio.create_task(_run())


def _is_public_http_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}


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


@router.get("/connectors/weknora/detect-local", summary="Detect local WeKnora")
async def detect_weknora_on_octop_host(
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Check WeKnora's fixed default loopback health endpoint (no persistence)."""
    del user
    return await detect_local_weknora()


@router.get("/connector-instances", summary="List connector instances")
async def list_instances(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """List the current user's connected accounts (custom MCP expanded per server)."""
    return _connector_service(server).list_instances_for_api(user.id)


@router.get("/connectors/custom-mcp", summary="Get custom MCP servers")
async def get_custom_mcp(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the user's custom MCP server map (langchain-mcp-adapters shape)."""
    servers = _connector_service(server).get_custom_servers_for_api(user.id)
    return {"servers": servers}


@router.put("/connectors/custom-mcp", summary="Save custom MCP servers")
async def put_custom_mcp(
    body: CustomMcpPutBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Replace the user's custom MCP servers document and reload agents."""
    svc = _connector_service(server)
    try:
        servers = svc.put_custom_servers(user.id, body.servers)
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    server.services.audit_repo.write(
        actor=user.username,
        action="connector.custom_mcp.save",
        target=CUSTOM_MCP_KIND,
        payload=str(len(servers)),
    )
    _schedule_connector_reload(server, user.id)
    return {"servers": redact_servers_for_api(servers)}


@router.patch(
    "/connectors/custom-mcp/servers/{server_name}",
    summary="Patch one custom MCP server",
)
async def patch_custom_mcp_server(
    server_name: str,
    body: CustomMcpServerPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Update ``enabled`` and/or ``default_open`` for one custom MCP server."""
    svc = _connector_service(server)
    try:
        servers = svc.patch_custom_server(
            user.id,
            server_name,
            enabled=body.enabled,
            default_open=body.default_open,
        )
    except KeyError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_NOT_FOUND, f"custom MCP server {server_name!r} not found"
        ) from exc
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
    _schedule_connector_reload(server, user.id)
    return {"servers": redact_servers_for_api(servers)}


@router.post("/connectors/custom-mcp/test", summary="Probe a custom MCP server")
async def test_custom_mcp(
    body: CustomMcpTestBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe connectivity for one custom MCP server (saved name or inline spec)."""
    svc = _connector_service(server)
    spec: dict[str, Any] | None = None
    if body.server is not None:
        spec = dict(body.server)
    elif body.name:
        saved = svc.get_custom_servers(user.id)
        raw = saved.get(body.name)
        if not isinstance(raw, dict):
            raise OctopError(
                ErrorCode.CONNECTOR_NOT_FOUND, f"custom MCP server {body.name!r} not found"
            )
        spec = dict(raw)
    else:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            "provide name or server spec to probe",
        )
    result = await probe_custom_mcp_server(spec)
    if body.name:
        try:
            if result.get("oauth", {}).get("available") and not oauth_configured(spec):
                svc.note_custom_server_oauth_required(user.id, body.name, required=True)
            elif result.get("ok") or not result.get("oauth", {}).get("available"):
                svc.note_custom_server_oauth_required(user.id, body.name, required=False)
        except KeyError:
            pass
    return result


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
        if inst.kind == "feishu-cli" and data["credentials_preview"].get("user_auth_configured"):
            live = await asyncio.to_thread(live_user_auth_preview, creds)
            data["credentials_preview"].update(live)
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
    if is_custom_mcp_kind(body.kind):
        raise OctopError(
            ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
            "use PUT /connectors/custom-mcp for custom MCP servers",
        )
    entry = get_catalog_entry(body.kind)
    if entry is None:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"unknown kind {body.kind!r}")
    if entry.phase != "available":
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, f"{body.kind} not available")

    repo = server.services.repos.connector_repo
    svc = _connector_service(server)
    cred_input = dict(body.credentials)
    old_cli_creds: dict[str, Any] | None = None
    for old in repo.list_by_user(user.id):
        if old.kind == body.kind:
            if old.has_credentials:
                old_cli_creds = svc.decrypt(old.instance_id)
                cred_input = _merge_credentials(old_cli_creds, cred_input)
            repo.delete(old.instance_id)
            break

    try:
        cred_payload = await _prepare_credentials(
            body.kind, cred_input, server.services.settings_repo
        )
    except ValueError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc

    instance_id = new_ulid()
    if body.kind in ("feishu-cli", "wecom-cli") and old_cli_creds:
        keep = cleanup_keys_for_creds(body.kind, {**cred_payload, "instance_id": instance_id})
        cleanup_creds_cli_dirs(body.kind, old_cli_creds, keep=keep)
    repo.create(
        instance_id=instance_id,
        user_id=user.id,
        kind=body.kind,
        display_name=body.display_name.strip(),
        mcp_server_name=mcp_server_name(body.kind, instance_id),
        config_json=build_instance_config_json(
            kind=body.kind,
            default_open=bool(body.default_open),
            email=cred_payload.get("email"),
        ),
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
    """Enable/disable a connector or update default_open without deleting credentials."""
    synthetic_name = parse_synthetic_instance_id(instance_id)
    if synthetic_name is not None:
        svc = _connector_service(server)
        if body.status is None and body.default_open is None:
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                "status or default_open is required",
            )
        try:
            if body.status is not None:
                status = body.status.strip()
                if status not in ("active", "disabled"):
                    raise OctopError(
                        ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                        "status must be active or disabled",
                    )
                svc.patch_custom_server_enabled(
                    user.id, synthetic_name, enabled=(status == "active")
                )
            if body.default_open is not None:
                svc.patch_custom_server_default_open(
                    user.id, synthetic_name, default_open=bool(body.default_open)
                )
        except KeyError as exc:
            raise OctopError(
                ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found"
            ) from exc
        except ValueError as exc:
            raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
        _schedule_connector_reload(server, user.id)
        for item in svc.list_instances_for_api(user.id):
            if item["instance_id"] == instance_id:
                return item
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")

    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
    if is_custom_mcp_kind(inst.kind):
        raise OctopError(
            ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
            "use PATCH /connectors/custom-mcp/servers/{name} for custom MCP servers",
        )
    if body.status is None and body.default_open is None:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            "status or default_open is required",
        )
    if body.status is not None:
        status = body.status.strip()
        if status not in ("active", "disabled"):
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "status must be active or disabled"
            )
        repo.update_status(instance_id, status)
    if body.default_open is not None:
        config = dict(ConnectorRepo.parse_config_json(inst))
        if body.default_open:
            config["default_open"] = True
        else:
            config.pop("default_open", None)
        repo.update_config_json(
            instance_id, json.dumps(config, ensure_ascii=False) if config else None
        )
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
    synthetic_name = parse_synthetic_instance_id(instance_id)
    if synthetic_name is not None:
        svc = _connector_service(server)
        servers = dict(svc.get_custom_servers(user.id))
        if synthetic_name not in servers:
            raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
        del servers[synthetic_name]
        try:
            svc.put_custom_servers(user.id, servers)
        except ValueError as exc:
            raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, str(exc)) from exc
        server.services.audit_repo.write(
            actor=user.username,
            action="connector.custom_mcp.delete_server",
            target=synthetic_name,
            payload=CUSTOM_MCP_KIND,
        )
        _schedule_connector_reload(server, user.id)
        return

    repo = server.services.repos.connector_repo
    inst = repo.get(instance_id)
    if inst is None:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
    if inst.user_id != user.id:
        raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
    user_id = inst.user_id
    cli_creds: dict[str, Any] | None = None
    if inst.kind in ("feishu-cli", "wecom-cli") and inst.has_credentials:
        try:
            cli_creds = _connector_service(server).decrypt(instance_id)
        except Exception:
            cli_creds = {"instance_id": instance_id}
        else:
            cli_creds = {**cli_creds, "instance_id": instance_id}
    repo.delete(instance_id)
    if cli_creds is not None:
        cleanup_creds_cli_dirs(inst.kind, cli_creds)
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
    synthetic_name = parse_synthetic_instance_id(instance_id)
    if synthetic_name is not None:
        svc = _connector_service(server)
        saved = svc.get_custom_servers(user.id)
        raw = saved.get(synthetic_name)
        if not isinstance(raw, dict):
            raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
        return await probe_custom_mcp_server(dict(raw))

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
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc
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


@router.get(
    "/connectors/{kind}/cli-status",
    summary="Host CLI install status for Feishu/WeCom connectors",
)
async def connector_cli_status(
    kind: str,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Report whether the host binary is on PATH (no side effects)."""
    del user
    if get_cli_install_spec(kind) is None:
        raise OctopError(
            ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
            f"kind {kind!r} does not support CLI install",
        )
    try:
        return await asyncio.to_thread(cli_install_status, kind)
    except ValueError as exc:
        raise OctopError(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, str(exc)) from exc


@router.post(
    "/connectors/{kind}/install-cli",
    summary="Install host CLI for Feishu/WeCom connectors (admin)",
)
async def connector_install_cli(
    kind: str,
    _: Any = Depends(require_permission("connectors")),
) -> dict[str, Any]:
    """Run ``npm install -g`` for the connector CLI on the Octop host (admin only).

    Always returns a structured body (even on failure) including ``install_command``
    and documentation URLs so the UI can guide manual install.
    """
    if get_cli_install_spec(kind) is None:
        raise OctopError(
            ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
            f"kind {kind!r} does not support CLI install",
        )
    return await asyncio.to_thread(install_connector_cli, kind)


@router.post(
    "/connectors/feishu-cli/user-auth/start",
    summary="Start Feishu CLI user device-code login",
)
async def feishu_cli_user_auth_start(
    body: FeishuUserAuthStartBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Begin OAuth device-code login (no local HTTPS callback required)."""
    del user
    svc = _connector_service(server)
    try:
        return await svc.start_feishu_user_auth(
            app_id=body.app_id,
            app_secret=body.app_secret,
            cli_config_key=body.cli_config_key,
            domains=body.domains,
        )
    except ValueError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc


@router.post(
    "/connectors/feishu-cli/user-auth/complete",
    summary="Complete Feishu CLI user device-code login",
)
async def feishu_cli_user_auth_complete(
    body: FeishuUserAuthCompleteBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Finish device-code login and switch default identity to user."""
    del user
    svc = _connector_service(server)
    try:
        return await svc.complete_feishu_user_auth(
            app_id=body.app_id,
            app_secret=body.app_secret,
            device_code=body.device_code,
            cli_config_key=body.cli_config_key or "",
        )
    except ValueError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc


class FeishuUserAuthInstanceCompleteBody(BaseModel):
    device_code: str
    cli_config_key: str | None = None


@router.post(
    "/connector-instances/{instance_id}/feishu-user-auth/start",
    summary="Start Feishu user login for an existing connector instance",
)
async def feishu_cli_user_auth_start_instance(
    instance_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Same as start, but App Secret is read from the stored instance."""
    svc = _connector_service(server)
    try:
        return await svc.start_feishu_user_auth_for_instance(instance_id, user.id)
    except ValueError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc


@router.post(
    "/connector-instances/{instance_id}/feishu-user-auth/complete",
    summary="Complete Feishu user login for an existing connector instance",
)
async def feishu_cli_user_auth_complete_instance(
    instance_id: str,
    body: FeishuUserAuthInstanceCompleteBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    svc = _connector_service(server)
    try:
        result = await svc.complete_feishu_user_auth_for_instance(
            instance_id,
            user.id,
            device_code=body.device_code,
            cli_config_key=body.cli_config_key,
        )
    except ValueError as exc:
        raise OctopError(
            ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
            str(exc),
            details={"reason": str(exc)},
        ) from exc
    _schedule_connector_reload(server, user.id)
    return result


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


@router.post("/connectors/oauth/start", summary="Start OAuth flow (unified)")
async def oauth_start_unified(
    body: OAuthStartBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Begin browser OAuth for a catalog connector or custom MCP server."""
    if not body.target or not isinstance(body.target, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "oauth target is required")
    return await _begin_oauth_flow(
        request=request,
        user=user,
        server=server,
        target=body.target,
        redirect_after=body.redirect_after,
    )


@router.post("/connectors/oauth/{kind}/start", summary="Start OAuth flow (legacy)")
async def oauth_start_legacy(
    kind: str,
    body: OAuthStartLegacyBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Legacy catalog-only alias for :func:`oauth_start_unified`."""
    return await _begin_oauth_flow(
        request=request,
        user=user,
        server=server,
        target={"type": "catalog", "kind": kind},
        redirect_after=body.redirect_after,
    )


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

    base = resolve_public_base(request)
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

    pending_payload: dict[str, Any] = {
        "user_id": row.user_id,
        "kind": row.kind,
        "tokens": tokens,
    }
    if row.kind == CUSTOM_MCP_KIND:
        server_name = str(ctx.get("server_name") or "")
        issuer = str(ctx.get("issuer") or "")
        resource = str(ctx.get("resource") or "").strip() or None
        try:
            svc = _connector_service(server)
            svc.apply_custom_server_oauth(
                row.user_id,
                server_name,
                tokens,
                issuer=issuer,
                resource=resource,
            )
            _schedule_connector_reload(server, row.user_id)
            pending_payload["server_name"] = server_name
            pending_payload["applied"] = True
        except Exception as exc:
            logger.exception("custom MCP oauth apply failed for %s", server_name)
            return HTMLResponse(
                f"<html><body>保存授权失败: {exc}</body></html>",
                status_code=400,
            )

    # Store tokens in a short-lived settings key for frontend pickup, or auto-create instance.
    pending_key = f"connector.oauth.pending.{row.state_id}"
    server.services.settings_repo.set(
        pending_key,
        json.dumps(pending_payload),
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
    return {
        "kind": data.get("kind"),
        "tokens": data.get("tokens") or {},
        "server_name": data.get("server_name"),
        "applied": data.get("applied"),
    }


async def validate_chat_mcp_servers(
    server: Any,
    *,
    user_id: int,
    names: list[str] | None,
) -> list[str] | None:
    from octop.api.common.validators import validate_chat_mcp_servers as _validate

    return await _validate(server, user_id=user_id, names=names)
