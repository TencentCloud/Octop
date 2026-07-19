"""Build harness HTTP MCP connection specs from connector instances."""

from __future__ import annotations

import re
import secrets
from typing import Any
from urllib.parse import quote

from octop.config import OctopConfig
from octop.infra.connectors.catalog import ConnectorCatalogEntry, get_catalog_entry

_MAIL_PROVIDER_PRESETS: dict[str, tuple[str, int, str, int]] = {
    "qq": ("imap.qq.com", 993, "smtp.qq.com", 587),
    "netease": ("imap.163.com", 993, "smtp.163.com", 587),
    "gmail": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
}

# MCP Streamable HTTP transport (Notion, etc.) requires both content types.
_MCP_STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"


def _mcp_http_headers() -> dict[str, str]:
    return {"Accept": _MCP_STREAMABLE_HTTP_ACCEPT}


def normalize_weiyun_mcp_token(raw: str) -> str:
    """Extract MCP token from pasted env vars or WyHeader snippets."""
    text = raw.strip().strip('"').strip("'")
    if not text:
        return ""
    match = re.search(r"mcp_token=([^\s;,&\"']+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"WEIYUN_MCP_TOKEN\s*=\s*['\"]?([^'\"\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _resolve_mail_servers(credentials: dict[str, Any]) -> tuple[str, int, str, int]:
    provider = str(credentials.get("mail_provider") or "").strip().lower()
    if provider in _MAIL_PROVIDER_PRESETS:
        return _MAIL_PROVIDER_PRESETS[provider]

    email = str(credentials.get("email") or "").strip().lower()
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if domain in ("qq.com", "foxmail.com"):
        return _MAIL_PROVIDER_PRESETS["qq"]
    if domain in ("163.com", "126.com", "yeah.net"):
        return _MAIL_PROVIDER_PRESETS["netease"]
    if domain == "gmail.com":
        return _MAIL_PROVIDER_PRESETS["gmail"]

    return (
        str(credentials.get("imap_host") or "imap.qq.com"),
        int(credentials.get("imap_port") or 993),
        str(credentials.get("smtp_host") or "smtp.qq.com"),
        int(credentials.get("smtp_port") or 587),
    )


def mcp_server_name(kind: str, instance_id: str) -> str:
    return f"{kind}__{instance_id}"


def internal_mcp_url(
    *,
    config: OctopConfig,
    gateway_kind: str,
    instance_id: str,
    internal_token: str,
) -> str:
    host = config.bind_host if config.bind_host not in ("0.0.0.0", "::") else "127.0.0.1"
    token_q = quote(internal_token, safe="")
    return (
        f"http://{host}:{config.port}/api/internal/mcp/{gateway_kind}/{instance_id}?token={token_q}"
    )


def new_internal_token() -> str:
    return secrets.token_urlsafe(32)


def build_http_mcp_spec(
    *,
    entry: ConnectorCatalogEntry,
    instance_id: str,
    creds: dict[str, Any],
    config: OctopConfig,
) -> dict[str, Any]:
    if entry.mcp_mode == "remote":
        return _build_remote_spec(entry, creds)
    return _build_gateway_spec(entry, instance_id, creds, config)


def _build_remote_spec(entry: ConnectorCatalogEntry, creds: dict[str, Any]) -> dict[str, Any]:
    if entry.kind == "tencent-docs":
        token = str(creds.get("token") or "")
        spec: dict[str, Any] = {
            "transport": "http",
            "url": "https://docs.qq.com/openapi/mcp",
            "headers": {"Authorization": token},
        }
        if entry.allowed_tools is not None:
            spec["allowed_tools"] = list(entry.allowed_tools)
        spec["tool_arg_aliases"] = {
            "manage.search_file": {
                "query": "search_key",
                "keyword": "search_key",
                "keywords": "search_key",
            },
        }
        return spec
    if entry.kind == "tencent-weiyun":
        raw = str(creds.get("token") or creds.get("access_token") or "").strip()
        token = normalize_weiyun_mcp_token(raw)
        spec = {
            "transport": "http",
            "url": "https://www.weiyun.com/api/v3/mcpserver",
            "headers": {
                **_mcp_http_headers(),
                "WyHeader": f"mcp_token={token}",
            },
        }
        if entry.allowed_tools is not None:
            spec["allowed_tools"] = list(entry.allowed_tools)
        return spec
    if entry.kind == "tencent-meeting":
        token = str(creds.get("token") or "")
        return {
            "transport": "http",
            "url": "https://mcp.meeting.tencent.com/mcp/wemeet-open/v1",
            "headers": {
                "X-Tencent-Meeting-Token": token,
                "X-Skill-Version": "v1.0.1",
            },
        }
    if entry.kind == "tencent-lexiang":
        token = str(creds.get("api_key") or creds.get("token") or "").strip()
        company_from = str(creds.get("company_from") or creds.get("client_id") or "").strip()
        url = "https://mcp.lexiang-app.com/mcp"
        if company_from:
            url = f"{url}?company_from={quote(company_from, safe='')}"
        return {
            "transport": "http",
            "url": url,
            "headers": {
                **_mcp_http_headers(),
                "Authorization": f"Bearer {token}",
            },
        }
    if entry.kind == "youdao-note":
        api_key = str(
            creds.get("token") or creds.get("api_key") or creds.get("access_token") or ""
        ).strip()
        return {
            "transport": "sse",
            "url": "https://open.mail.163.com/api/ynote/mcp/sse",
            "headers": {
                "x-api-key": api_key,
            },
        }
    if entry.kind == "notion":
        access_token = str(creds.get("access_token") or "")
        return {
            "transport": "http",
            "url": "https://mcp.notion.com/mcp",
            "headers": {
                **_mcp_http_headers(),
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "octop-connector/0.1",
            },
        }
    raise ValueError(f"unsupported remote connector kind: {entry.kind}")


def _build_gateway_spec(
    entry: ConnectorCatalogEntry,
    instance_id: str,
    creds: dict[str, Any],
    config: OctopConfig,
) -> dict[str, Any]:
    internal_token = str(creds.get("internal_token") or "")
    if not internal_token:
        raise ValueError("gateway connector missing internal_token")
    gateway_kind = entry.kind
    url = internal_mcp_url(
        config=config,
        gateway_kind=gateway_kind,
        instance_id=instance_id,
        internal_token=internal_token,
    )
    return {"transport": "http", "url": url}


def validate_create_credentials(
    kind: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    entry = get_catalog_entry(kind)
    if entry is None:
        raise ValueError(f"unknown connector kind: {kind}")
    if entry.phase != "available":
        raise ValueError(f"connector {kind} is not available yet")

    out: dict[str, Any] = {}  # pre-declare to avoid mypy no-redef errors

    if entry.auth_kind == "personal_token":
        raw = str(credentials.get("token") or credentials.get("access_token") or "").strip()
        token = normalize_weiyun_mcp_token(raw) if entry.kind == "tencent-weiyun" else raw
        if not token:
            raise ValueError("token is required")
        return {"token": token}

    if entry.auth_kind == "oauth2":
        access_token = str(credentials.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("access_token is required")
        out = {"access_token": access_token}
        if credentials.get("refresh_token"):
            out["refresh_token"] = str(credentials["refresh_token"])
        if credentials.get("expires_at"):
            out["expires_at"] = int(credentials["expires_at"])
        if credentials.get("oauth_client_id"):
            out["oauth_client_id"] = str(credentials["oauth_client_id"])
        if credentials.get("oauth_client_secret"):
            out["oauth_client_secret"] = str(credentials["oauth_client_secret"])
        if credentials.get("openid"):
            out["openid"] = str(credentials["openid"])
        if entry.mcp_mode == "gateway":
            out["internal_token"] = new_internal_token()
        return out

    if entry.auth_kind == "auth_code":
        access_token = str(credentials.get("access_token") or "").strip()
        if access_token:
            out = {"access_token": access_token}
            if credentials.get("refresh_token"):
                out["refresh_token"] = str(credentials["refresh_token"])
            if credentials.get("expires_at"):
                out["expires_at"] = int(credentials["expires_at"])
            if credentials.get("openid"):
                out["openid"] = str(credentials["openid"])
            if entry.mcp_mode == "gateway":
                out["internal_token"] = new_internal_token()
            return out
        cookie = str(credentials.get("cookie") or "").strip()
        if cookie:
            internal_token = new_internal_token()
            out = {"cookie": cookie, "internal_token": internal_token}
            return out
        raise ValueError("authorization code exchange failed or credentials missing")

    if entry.auth_kind == "api_key":
        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key:
            raise ValueError("api_key is required")
        if entry.kind == "wechat-reading" and not api_key.startswith("wrk-"):
            raise ValueError(
                "微信读书需使用 wrk- 开头的 API Key，请登录 "
                "https://weread.qq.com/r/weread-skills 获取"
            )
        if entry.kind == "qq-music" and not api_key.startswith("qmk-"):
            raise ValueError(
                "QQ 音乐需使用 qmk- 开头的 API Key，请登录 "
                "https://y.qq.com/n/ryqq_v2/qqmusic_skills 获取"
            )
        if entry.kind == "yuandian" and not api_key.startswith("sk_"):
            raise ValueError(
                "元典需使用 sk_ 开头的 API Key，请登录 https://open.chineselaw.com/profile 获取"
            )
        internal_token = new_internal_token()
        out = {"api_key": api_key, "internal_token": internal_token}
        if entry.kind == "tencent-ima":
            client_id = str(credentials.get("client_id") or "").strip()
            if not client_id:
                raise ValueError("client_id is required for IMA")
            out["client_id"] = client_id
            return out
        if entry.kind == "tencent-lexiang":
            company_from = str(
                credentials.get("company_from") or credentials.get("client_id") or ""
            ).strip()
            if not company_from:
                raise ValueError("company_from is required for Lexiang")
            return {"api_key": api_key, "company_from": company_from}
        return out

    if entry.auth_kind == "imap_app_password":
        email = str(credentials.get("email") or "").strip()
        password = str(credentials.get("password") or "").strip()
        if not email or not password:
            raise ValueError("email and password (authorization code) are required")
        imap_host, imap_port, smtp_host, smtp_port = _resolve_mail_servers(credentials)
        internal_token = new_internal_token()
        out = {
            "email": email,
            "password": password,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "internal_token": internal_token,
        }
        provider = str(credentials.get("mail_provider") or "").strip().lower()
        if provider:
            out["mail_provider"] = provider
        return out

    if entry.auth_kind == "session_cookie":
        cookie = str(credentials.get("cookie") or credentials.get("ima_cookie") or "").strip()
        if not cookie:
            raise ValueError("cookie is required")
        internal_token = new_internal_token()
        out = {"cookie": cookie, "internal_token": internal_token}
        if entry.kind == "tencent-ima":
            bkn = str(credentials.get("bkn") or credentials.get("ima_bkn") or "").strip()
            if not bkn:
                raise ValueError("bkn is required for IMA")
            out["bkn"] = bkn
            kbase = str(credentials.get("knowledge_base_id") or "").strip()
            if kbase:
                out["knowledge_base_id"] = kbase
        return out

    if entry.auth_kind == "api_credentials":
        app_id = str(credentials.get("app_id") or "").strip()
        sdk_id = str(credentials.get("sdk_id") or "").strip()
        secret_key = str(credentials.get("secret_key") or "").strip()
        if not app_id or not sdk_id or not secret_key:
            raise ValueError("app_id, sdk_id and secret_key are required")
        internal_token = new_internal_token()
        return {
            "app_id": app_id,
            "sdk_id": sdk_id,
            "secret_key": secret_key,
            "internal_token": internal_token,
        }

    raise ValueError(f"unsupported auth_kind: {entry.auth_kind}")


def _redact_mcp_configs_for_log(configs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, spec in configs.items():
        if not isinstance(spec, dict):
            out[name] = spec
            continue
        entry = dict(spec)
        url = str(entry.get("url") or "")
        if "token=" in url:
            entry["url"] = url.split("token=", 1)[0] + "token=***"
        headers = entry.get("headers")
        if isinstance(headers, dict):
            redacted = dict(headers)
            for key in ("Authorization", "authorization"):
                if key in redacted:
                    redacted[key] = "***"
            entry["headers"] = redacted
        out[name] = entry
    return out


def _iter_active_connectors(
    svc: Any,
    connector_repo: Any,
    user_id: int,
) -> Any:
    for inst in connector_repo.list_by_user(user_id):
        if inst.status != "active":
            continue
        entry = get_catalog_entry(inst.kind)
        if entry is None:
            continue
        creds = svc.decrypt(inst.instance_id)
        if not creds:
            continue
        yield inst, entry, creds


def build_mcp_server_configs_for_user(
    *,
    svc: Any,
    connector_repo: Any,
    user_id: int,
    agent_id: str,
    agent_user_id: int | None,
    config: OctopConfig,
    log: bool = True,
) -> dict[str, Any]:
    """Build harness ``mcp_server_configs`` from a user's active connector instances."""
    import json
    import logging

    logger = logging.getLogger(__name__)
    configs: dict[str, Any] = {}
    if log:
        logger.info(
            "build_mcp_server_configs agent=%s agent.user_id=%s connector_user_id=%s "
            "connector_instances=%d",
            agent_id,
            agent_user_id,
            user_id,
            len(connector_repo.list_by_user(user_id)),
        )
    for inst, entry, creds in _iter_active_connectors(svc, connector_repo, user_id):
        try:
            if entry.mcp_mode == "gateway":
                # Name-only placeholder: harness skips specs without ``transport``;
                # tools are injected in-process in AgentManager._post_start_agent.
                configs[inst.mcp_server_name] = {}
                if log:
                    logger.info(
                        "  register %s (%s) mcp_mode=gateway (in-process, no HTTP preload)",
                        inst.mcp_server_name,
                        inst.kind,
                    )
                continue
            configs[inst.mcp_server_name] = build_http_mcp_spec(
                entry=entry,
                instance_id=inst.instance_id,
                creds=creds,
                config=config,
            )
            if log:
                logger.info(
                    "  include %s (%s) mcp_mode=%s transport=%s",
                    inst.mcp_server_name,
                    inst.kind,
                    entry.mcp_mode,
                    configs[inst.mcp_server_name].get("transport"),
                )
        except Exception:
            logger.exception("failed to build MCP spec for instance %s", inst.instance_id)
    if log:
        logger.info(
            "build_mcp_server_configs agent=%s result: %s",
            agent_id,
            json.dumps(_redact_mcp_configs_for_log(configs), ensure_ascii=False),
        )
    return configs


def inject_missing_gateway_tools(
    agent: Any,
    *,
    svc: Any,
    connector_repo: Any,
    user_id: int,
    agent_id: str,
    mcp_server_configs: dict[str, Any],
) -> None:
    """Register gateway tools in-process when HTTP MCP load did not produce them."""
    import logging

    from harness_agent.mcp import mcp_tool_names

    from octop.infra.connectors.gateway import build_gateway_langchain_tools

    logger = logging.getLogger(__name__)
    tool_set = mcp_tool_names(getattr(agent, "_mcp_tools", []))
    extra: list[Any] = []
    for inst, entry, creds in _iter_active_connectors(svc, connector_repo, user_id):
        if entry.mcp_mode != "gateway":
            continue
        if any(str(t).startswith(f"{inst.mcp_server_name}_") for t in tool_set):
            continue
        extra.extend(
            build_gateway_langchain_tools(
                entry=entry,
                instance_id=inst.instance_id,
                mcp_server_name=inst.mcp_server_name,
                creds=creds,
            )
        )
    if not extra:
        gateway_names = [
            inst.mcp_server_name
            for inst in connector_repo.list_by_user(user_id)
            if inst.status == "active"
            and (entry := get_catalog_entry(inst.kind)) is not None
            and entry.mcp_mode == "gateway"
        ]
        http_loaded = [
            n for n in gateway_names if any(str(t).startswith(f"{n}_") for t in tool_set)
        ]
        logger.info(
            "gateway MCP injection skipped for agent %s: gateway_servers=%s http_loaded=%s",
            agent_id,
            gateway_names,
            http_loaded,
        )
        return
    agent.inject_mcp_tools(extra)
    tool_set = mcp_tool_names(getattr(agent, "_mcp_tools", []))
    ima_names = sorted(n for n in tool_set if n.startswith("tencent-ima__") or "_ima__" in n)
    logger.info(
        "Injecting %d in-process gateway MCP tools for agent %s (HTTP load missed); ima_tools=%s",
        len(extra),
        agent_id,
        ima_names,
    )
