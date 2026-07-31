"""Feishu CLI user identity via OAuth device-code (lark-cli auth login)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.cli_runner import run_cli
from octop.infra.connectors.gateway.feishu_creds import prepare_feishu_cli_env
from octop.infra.utils.paths import PathLayout

# ``docs +search`` requires user identity + ``search:docs:read``.
# Official guidance for full domain scopes: ``auth login --domain all``
# (without ``--recommend``, which only requests auto-approve scopes).
_DEFAULT_DOMAINS = ("all",)
_DEFAULT_SCOPES = ("search:docs:read",)


def start_user_device_login(
    *,
    config_dir: Path,
    app_id: str,
    app_secret: str,
    domains: list[str] | None = None,
    scopes: list[str] | None = None,
    recommend: bool = False,
) -> dict[str, Any]:
    """Begin device-code login; return verification_url + device_code (non-blocking)."""
    binary, env = _prepare(config_dir, app_id=app_id, app_secret=app_secret, default_as="bot")
    argv = [binary, "auth", "login", "--no-wait", "--json"]
    if recommend:
        argv.append("--recommend")
    for domain in domains if domains is not None else list(_DEFAULT_DOMAINS):
        d = str(domain).strip()
        if d:
            argv.extend(["--domain", d])
    scope_parts = [
        str(s).strip()
        for s in (scopes if scopes is not None else list(_DEFAULT_SCOPES))
        if str(s).strip()
    ]
    if scope_parts:
        # Additive with --domain; ensures docs +search even when domains are narrowed.
        argv.extend(["--scope", " ".join(scope_parts)])
    raw = run_cli(argv, env=env, timeout_s=60.0)
    payload = _parse_json_object(raw)
    device_code = str(payload.get("device_code") or "").strip()
    verification_url = str(
        payload.get("verification_url")
        or payload.get("verification_uri_complete")
        or payload.get("verification_uri")
        or ""
    ).strip()
    if not device_code or not verification_url:
        raise ValueError(f"lark-cli auth login --no-wait 返回不完整: {raw[:500]}")
    expires_in = payload.get("expires_in")
    return {
        "device_code": device_code,
        "verification_url": verification_url,
        "expires_in": int(expires_in) if expires_in is not None else None,
        "user_code": _extract_user_code(verification_url, payload),
        "hint": str(payload.get("hint") or "").strip() or None,
    }


def complete_user_device_login(
    *,
    config_dir: Path,
    app_id: str,
    app_secret: str,
    device_code: str,
) -> dict[str, Any]:
    """Finish device-code login and switch default identity to user."""
    code = str(device_code or "").strip()
    if not code:
        raise ValueError("device_code is required")
    binary, env = _prepare(config_dir, app_id=app_id, app_secret=app_secret, default_as="bot")
    run_cli(
        [binary, "auth", "login", "--device-code", code, "--json"],
        env=env,
        timeout_s=120.0,
    )
    run_cli([binary, "config", "default-as", "user"], env=env, timeout_s=30.0)
    status = read_auth_status(binary=binary, env=env)
    user = (
        status.get("identities", {}).get("user")
        if isinstance(status.get("identities"), dict)
        else None
    )
    user_available = isinstance(user, dict) and bool(user.get("available"))
    identity = str(status.get("identity") or status.get("defaultAs") or "").strip()
    if not user_available:
        raise ValueError("用户授权未完成或 token 无效。请重新点击「登录授权」并打开链接完成授权。")
    missing_search = not _auth_has_scope(binary=binary, env=env, scope="search:docs:read")
    return {
        "ok": True,
        "identity": identity or "user",
        "default_as": "user",
        "user_available": True,
        "bot_available": bool(
            isinstance(status.get("identities"), dict)
            and isinstance(status["identities"].get("bot"), dict)
            and status["identities"]["bot"].get("available")
        ),
        "search_docs_scope": not missing_search,
        "auth_status": status,
        "warning": (
            "已登录，但缺少 search:docs:read。"
            "请在飞书开放平台为应用开通该权限后，再点一次「登录授权」。"
            if missing_search
            else None
        ),
    }


def read_auth_status(*, binary: str, env: dict[str, str]) -> dict[str, Any]:
    raw = run_cli([binary, "auth", "status", "--json"], env=env, timeout_s=60.0)
    return _parse_json_object(raw)


def live_user_auth_preview(creds: dict[str, Any]) -> dict[str, Any]:
    """Best-effort live status for dashboard preview (never raises)."""
    try:
        app_id = str(creds.get("app_id") or "").strip()
        app_secret = str(creds.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            return {"user_auth_valid": False, "user_auth_needs_reauth": True}
        cli_key = resolve_cli_config_key(creds)
        config_dir = PathLayout.from_env().ensure_connector_cli_instance_dir("feishu-cli", cli_key)
        binary, env = prepare_feishu_cli_env(
            config_dir, app_id=app_id, app_secret=app_secret, default_as="user"
        )
        status = read_auth_status(binary=binary, env=env)
        user = (
            status.get("identities", {}).get("user")
            if isinstance(status.get("identities"), dict)
            else None
        )
        available = isinstance(user, dict) and bool(user.get("available"))
        token_status = str((user or {}).get("tokenStatus") or "").strip().lower()
        expires_at = (user or {}).get("expiresAt")
        refresh_expires_at = (user or {}).get("refreshExpiresAt")
        needs_reauth = (not available) or token_status in {
            "expired",
            "invalid",
            "missing",
            "revoked",
        }
        search_ok = False
        if available and not needs_reauth:
            search_ok = _auth_has_scope(binary=binary, env=env, scope="search:docs:read")
        return {
            "user_auth_valid": available and not needs_reauth,
            "user_auth_needs_reauth": needs_reauth,
            "user_token_status": token_status or None,
            "user_token_expires_at": expires_at,
            "user_refresh_expires_at": refresh_expires_at,
            "search_docs_scope": search_ok,
        }
    except Exception:
        return {
            "user_auth_valid": False,
            "user_auth_needs_reauth": True,
        }


def _auth_has_scope(*, binary: str, env: dict[str, str], scope: str) -> bool:
    try:
        run_cli(
            [binary, "auth", "check", "--scope", scope],
            env=env,
            timeout_s=30.0,
        )
        return True
    except ValueError:
        return False


def _prepare(
    config_dir: Path,
    *,
    app_id: str,
    app_secret: str,
    default_as: str,
) -> tuple[str, dict[str, str]]:
    return prepare_feishu_cli_env(
        config_dir,
        app_id=app_id,
        app_secret=app_secret,
        default_as=default_as,
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text.startswith("{"):
        # Some CLI versions print OK lines before JSON.
        idx = text.find("{")
        if idx < 0:
            raise ValueError(f"expected JSON from lark-cli, got: {text[:300]}")
        text = text[idx:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from lark-cli: {text[:300]}") from exc
    if not isinstance(data, dict):
        raise ValueError("lark-cli JSON root must be an object")
    return data


def _extract_user_code(verification_url: str, payload: dict[str, Any]) -> str | None:
    code = str(payload.get("user_code") or "").strip()
    if code:
        return code
    try:
        qs = parse_qs(urlparse(verification_url).query)
        vals = qs.get("user_code") or []
        return str(vals[0]) if vals else None
    except Exception:
        return None
