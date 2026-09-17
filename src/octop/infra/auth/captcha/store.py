"""Settings blob + env snapshot → effective captcha config."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from cryptography.fernet import InvalidToken

from octop.infra.auth.captcha.config import CaptchaEnv
from octop.infra.auth.captcha.providers import get_provider, list_providers, parse_slug
from octop.infra.auth.sso.crypto import decrypt_secret, encrypt_secret
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.errors import ErrorCode, OctopError

SETTINGS_KEY = "captcha.settings"
logger = logging.getLogger(__name__)

Source = Literal["settings", "env"]


@dataclass(frozen=True)
class EffectiveCaptcha:
    slug: str
    site_key: str
    secret: str
    source: Source
    stored_active: str | None
    v3_min_score: float
    cam_id: str = ""
    cam_key: str = ""


_CACHE_KEY: tuple[str | None, str, str, str, float] | None = None
_CACHE_VAL: EffectiveCaptcha | None = None


def public_config(effective: EffectiveCaptcha) -> dict[str, str]:
    provider = get_provider(effective.slug)
    if provider is None or not provider.requires_token:
        return {"provider": "slider"}
    return {"provider": effective.slug, "site_key": effective.site_key}


def _decode_secret(secret_repo: SecretRepo, secret_enc: str) -> str | None:
    if not secret_enc:
        return None
    try:
        return decrypt_secret(secret_repo, secret_enc.encode("ascii"))
    except (InvalidToken, ValueError):
        return None


def _read_blob(settings_repo: SettingsRepo, secret_repo: SecretRepo) -> dict[str, Any] | None:
    raw = settings_repo.get(SETTINGS_KEY)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("captcha settings blob is not valid JSON; ignoring")
        return None
    if not isinstance(data, dict):
        logger.warning("captcha settings blob is not an object; ignoring")
        return None
    providers = data.get("providers")
    if isinstance(providers, dict):
        for pair in providers.values():
            if not isinstance(pair, dict):
                continue
            enc = pair.get("secret_enc")
            if isinstance(enc, str) and enc and _decode_secret(secret_repo, enc) is None:
                logger.warning("captcha settings blob secret cannot be decrypted; ignoring")
                return None
            cam_enc = pair.get("cam_secret_enc")
            if (
                isinstance(cam_enc, str)
                and cam_enc
                and _decode_secret(secret_repo, cam_enc) is None
            ):
                logger.warning("captcha settings blob cam secret cannot be decrypted; ignoring")
                return None
    return data


def _pair_from_blob(
    blob: dict[str, Any], secret_repo: SecretRepo, slug: str
) -> tuple[str, str, str, str] | None:
    providers = blob.get("providers")
    if not isinstance(providers, dict):
        return None
    row = providers.get(slug)
    if not isinstance(row, dict):
        return None
    site_key = str(row.get("site_key") or "").strip()
    enc = row.get("secret_enc")
    secret = _decode_secret(secret_repo, enc) if isinstance(enc, str) else None
    if site_key and secret:
        cam_id = str(row.get("cam_secret_id") or "").strip()
        cam_enc = row.get("cam_secret_enc")
        cam_key = _decode_secret(secret_repo, cam_enc) if isinstance(cam_enc, str) else None
        return site_key, secret, cam_id, cam_key or ""
    return None


def _slider(source: Source, stored_active: str | None, env: CaptchaEnv) -> EffectiveCaptcha:
    return EffectiveCaptcha(
        slug="slider",
        site_key="",
        secret="",
        source=source,
        stored_active=stored_active,
        v3_min_score=env.v3_min_score,
    )


def invalidate_cache() -> None:
    global _CACHE_KEY, _CACHE_VAL
    _CACHE_KEY = None
    _CACHE_VAL = None


def has_readable_blob(settings_repo: SettingsRepo, secret_repo: SecretRepo) -> bool:
    return _read_blob(settings_repo, secret_repo) is not None


def load_effective(
    settings_repo: SettingsRepo,
    secret_repo: SecretRepo,
    env: CaptchaEnv,
) -> EffectiveCaptcha:
    global _CACHE_KEY, _CACHE_VAL
    raw = settings_repo.get(SETTINGS_KEY)
    cache_key = (raw, env.provider, env.site_key, env.secret, env.v3_min_score)
    if cache_key == _CACHE_KEY and _CACHE_VAL is not None:
        return _CACHE_VAL
    resolved = _resolve_effective(settings_repo, secret_repo, env)
    _CACHE_KEY = cache_key
    _CACHE_VAL = resolved
    return resolved


def _resolve_effective(
    settings_repo: SettingsRepo,
    secret_repo: SecretRepo,
    env: CaptchaEnv,
) -> EffectiveCaptcha:
    blob = _read_blob(settings_repo, secret_repo)
    if blob is None:
        provider = get_provider(env.provider)
        if provider is None or not provider.requires_token:
            return _slider("env", None, env)
        return EffectiveCaptcha(
            slug=env.provider,
            site_key=env.site_key,
            secret=env.secret,
            source="env",
            stored_active=None,
            v3_min_score=env.v3_min_score,
            cam_id=env.cam_secret_id,
            cam_key=env.cam_secret_key,
        )

    raw_active = str(blob.get("active") or "").strip()
    try:
        active = parse_slug(raw_active) if raw_active else "slider"
    except ValueError:
        logger.warning("captcha settings active %r is not registered; using slider", raw_active)
        return _slider("settings", raw_active or None, env)

    if active == "slider":
        return _slider("settings", active, env)

    provider = get_provider(active)
    if provider is None or not provider.requires_token:
        logger.warning("captcha settings active %r is not registered; using slider", raw_active)
        return _slider("settings", raw_active or active, env)

    stored = _pair_from_blob(blob, secret_repo, active)
    if stored is not None:
        site_key, secret, cam_id, cam_key = stored
        return EffectiveCaptcha(
            slug=active,
            site_key=site_key,
            secret=secret,
            source="settings",
            stored_active=active,
            v3_min_score=env.v3_min_score,
            cam_id=cam_id or env.cam_secret_id,
            cam_key=cam_key or env.cam_secret_key,
        )

    if env.provider == active and env.pair_complete:
        return EffectiveCaptcha(
            slug=active,
            site_key=env.site_key,
            secret=env.secret,
            source="settings",
            stored_active=active,
            v3_min_score=env.v3_min_score,
            cam_id=env.cam_secret_id,
            cam_key=env.cam_secret_key,
        )

    logger.warning("captcha settings pair for %s is incomplete; using slider", active)
    return _slider("settings", active, env)


def _pair_view(
    site_key: str,
    has_secret: bool,
    cam_secret_id: str = "",
    has_cam_secret: bool = False,
) -> dict[str, str | bool]:
    return {
        "site_key": site_key,
        "has_secret": has_secret,
        "cam_secret_id": cam_secret_id,
        "has_cam_secret": has_cam_secret,
    }


def load_view(
    settings_repo: SettingsRepo,
    secret_repo: SecretRepo,
    env: CaptchaEnv,
) -> dict[str, Any]:
    blob = _read_blob(settings_repo, secret_repo)
    available = list_providers()
    if blob is None:
        providers: dict[str, dict[str, str | bool]] = {}
        provider = get_provider(env.provider)
        if provider is not None and provider.requires_token and env.pair_complete:
            providers[env.provider] = _pair_view(
                env.site_key, True, env.cam_secret_id, bool(env.cam_secret_key)
            )
        return {
            "active": env.provider or "slider",
            "available": available,
            "providers": providers,
            "source": "env",
            "v3_min_score": env.v3_min_score,
        }

    raw_active = str(blob.get("active") or "").strip() or "slider"
    providers = {}
    stored = blob.get("providers")
    if isinstance(stored, dict):
        for slug, pair in stored.items():
            if not isinstance(pair, dict):
                continue
            site_key = str(pair.get("site_key") or "").strip()
            enc = pair.get("secret_enc")
            has_secret = isinstance(enc, str) and bool(enc)
            if isinstance(enc, str) and enc:
                has_secret = _decode_secret(secret_repo, enc) is not None
            cam_id = str(pair.get("cam_secret_id") or "").strip()
            cam_enc = pair.get("cam_secret_enc")
            has_cam = isinstance(cam_enc, str) and bool(cam_enc)
            if isinstance(cam_enc, str) and cam_enc:
                has_cam = _decode_secret(secret_repo, cam_enc) is not None
            if site_key or has_secret:
                providers[str(slug)] = _pair_view(site_key, has_secret, cam_id, has_cam)

    try:
        canonical = parse_slug(raw_active)
    except ValueError:
        canonical = None
    if (
        canonical is not None
        and canonical != "slider"
        and _pair_from_blob(blob, secret_repo, canonical) is None
        and env.provider == canonical
        and env.pair_complete
    ):
        providers[canonical] = _pair_view(env.site_key, True)

    return {
        "active": raw_active,
        "available": available,
        "providers": providers,
        "source": "settings",
        "v3_min_score": env.v3_min_score,
    }


def save_settings(
    settings_repo: SettingsRepo,
    secret_repo: SecretRepo,
    env: CaptchaEnv,
    patch: dict[str, Any],
) -> dict[str, Any]:
    blob = _read_blob(settings_repo, secret_repo)
    if blob is None:
        blob = {"active": "slider", "providers": {}}
    raw_providers = blob.get("providers")
    providers = dict(raw_providers) if isinstance(raw_providers, dict) else {}

    if "active" in patch:
        raw_active = str(patch.get("active") or "").strip()
        try:
            blob["active"] = parse_slug(raw_active) if raw_active else "slider"
        except ValueError as exc:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc

    incoming = patch.get("providers")
    if incoming is not None:
        if not isinstance(incoming, dict):
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "providers must be an object")
        for raw_slug, pair in incoming.items():
            try:
                slug = parse_slug(str(raw_slug))
            except ValueError as exc:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
            if pair is None:
                providers.pop(slug, None)
                continue
            if not isinstance(pair, dict):
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "provider pair must be an object")
            existing = providers.get(slug)
            row = dict(existing) if isinstance(existing, dict) else {}
            if "site_key" in pair and pair["site_key"] is not None:
                row["site_key"] = str(pair["site_key"]).strip()
            secret = pair.get("secret")
            if isinstance(secret, str) and secret.strip():
                row["secret_enc"] = encrypt_secret(secret_repo, secret.strip()).decode("ascii")
            if "cam_secret_id" in pair and pair["cam_secret_id"] is not None:
                row["cam_secret_id"] = str(pair["cam_secret_id"]).strip()
            cam_secret = pair.get("cam_secret")
            if isinstance(cam_secret, str) and cam_secret.strip():
                row["cam_secret_enc"] = encrypt_secret(secret_repo, cam_secret.strip()).decode(
                    "ascii"
                )
            providers[slug] = row

    blob["providers"] = providers
    raw_active = str(blob.get("active") or "").strip()
    try:
        active = parse_slug(raw_active) if raw_active else "slider"
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
    blob["active"] = active
    provider = get_provider(active)
    if provider is not None and provider.requires_token:
        stored = _pair_from_blob(blob, secret_repo, active)
        if stored is None and not (env.provider == active and env.pair_complete):
            raise OctopError(
                ErrorCode.SLASH_BAD_ARGS,
                "strong captcha provider needs a complete site key and secret",
            )

    settings_repo.set(SETTINGS_KEY, json.dumps(blob, ensure_ascii=False))
    invalidate_cache()
    return load_view(settings_repo, secret_repo, env)
