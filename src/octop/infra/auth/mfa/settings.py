"""Admin KV settings for WebAuthn RP ID and allowed origins."""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any
from urllib.parse import urlparse

from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

SETTINGS_KEY = "webauthn.settings"
# Browsers reject IP literals as WebAuthn RP IDs ("This is an invalid domain").
# Only the hostname ``localhost`` is usable for local HTTP development.
_LOOPBACK_RP_HOSTS = frozenset({"localhost"})


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _reject_ip_rp_id(rp_id: str) -> None:
    if _is_ip_literal(rp_id):
        raise OctopError(
            ErrorCode.WEBAUTHN_INVALID_DOMAIN,
            "WebAuthn RP ID cannot be an IP address; use localhost or a DNS hostname",
        )


def _read_blob(settings_repo: SettingsRepo) -> dict[str, Any] | None:
    raw = settings_repo.get(SETTINGS_KEY)
    if raw is None or raw == "":
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("webauthn settings blob is not valid JSON; ignoring")
        return None
    if not isinstance(data, dict):
        logger.warning("webauthn settings blob is not an object; ignoring")
        return None
    return data


def load_webauthn_config(settings_repo: SettingsRepo) -> tuple[str, list[str]]:
    """Return ``(rp_id, origins)``. Raises ``WEBAUTHN_CONFIG_INVALID`` when unset."""
    blob = _read_blob(settings_repo)
    if blob is None:
        raise OctopError(
            ErrorCode.WEBAUTHN_CONFIG_INVALID,
            "webauthn is not configured",
        )
    rp_id = str(blob.get("rp_id") or "").strip()
    origins_raw = blob.get("origins")
    origins: list[str] = []
    if isinstance(origins_raw, list):
        origins = [str(o).strip() for o in origins_raw if str(o).strip()]
    elif isinstance(origins_raw, str) and origins_raw.strip():
        origins = [p.strip() for p in origins_raw.split(",") if p.strip()]
    if not rp_id or not origins:
        raise OctopError(
            ErrorCode.WEBAUTHN_CONFIG_INVALID,
            "webauthn rp_id and origins are required",
        )
    _reject_ip_rp_id(rp_id)
    return rp_id, origins


def load_view(settings_repo: SettingsRepo) -> dict[str, Any]:
    blob = _read_blob(settings_repo) or {}
    rp_id = str(blob.get("rp_id") or "").strip()
    origins_raw = blob.get("origins")
    origins: list[str] = []
    if isinstance(origins_raw, list):
        origins = [str(o).strip() for o in origins_raw if str(o).strip()]
    elif isinstance(origins_raw, str) and origins_raw.strip():
        origins = [p.strip() for p in origins_raw.split(",") if p.strip()]
    return {"rp_id": rp_id or None, "origins": origins}


def save_settings(settings_repo: SettingsRepo, body: dict[str, Any]) -> dict[str, Any]:
    blob = _read_blob(settings_repo) or {}
    if "rp_id" in body:
        rp_id = str(body["rp_id"] or "").strip()
        if rp_id:
            _reject_ip_rp_id(rp_id)
        blob["rp_id"] = rp_id
    if "origins" in body:
        raw = body["origins"]
        if isinstance(raw, list):
            blob["origins"] = [str(o).strip() for o in raw if str(o).strip()]
        elif isinstance(raw, str):
            blob["origins"] = [p.strip() for p in raw.split(",") if p.strip()]
        elif raw is None:
            blob["origins"] = []
    settings_repo.set(SETTINGS_KEY, json.dumps(blob, ensure_ascii=False))
    return load_view(settings_repo)


def _loopback_rp(origin: str) -> tuple[str, list[str]] | None:
    """When admin settings are unset, allow ``http(s)://localhost`` only.

    Chromium rejects IP literals (including ``127.0.0.1`` / ``::1``) as
    WebAuthn RP IDs with "This is an invalid domain". Production hosts still
    require explicit ``webauthn.settings``.
    """
    try:
        parsed = urlparse(origin)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return None
    if _is_ip_literal(host):
        raise OctopError(
            ErrorCode.WEBAUTHN_INVALID_DOMAIN,
            "WebAuthn cannot use an IP address; open the app via http://localhost",
        )
    if host not in _LOOPBACK_RP_HOSTS:
        return None
    # RP ID is the host without port (WebAuthn requirement).
    return host, [origin]


def assert_origin_allowed(settings_repo: SettingsRepo, origin: str) -> tuple[str, list[str]]:
    try:
        rp_id, origins = load_webauthn_config(settings_repo)
    except OctopError as exc:
        if exc.code == ErrorCode.WEBAUTHN_CONFIG_INVALID:
            fallback = _loopback_rp(origin)
            if fallback is not None:
                return fallback
        raise
    if origin not in origins:
        raise OctopError(
            ErrorCode.WEBAUTHN_CONFIG_INVALID,
            "request origin is not in the webauthn allow-list",
        )
    return rp_id, origins
