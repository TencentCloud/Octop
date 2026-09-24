"""Boot-time captcha env snapshot."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from octop.infra.auth.captcha.providers import get_provider, parse_slug

_DEFAULT_V3_MIN_SCORE = 0.5

_INSTALLED: CaptchaEnv | None = None


@dataclass(frozen=True)
class CaptchaEnv:
    provider: str
    site_key: str
    secret: str
    v3_min_score: float = _DEFAULT_V3_MIN_SCORE
    cam_secret_id: str = ""
    cam_secret_key: str = ""

    @property
    def pair_complete(self) -> bool:
        return bool(self.site_key) and bool(self.secret)


def snapshot_env(environ: Mapping[str, str] | None = None) -> CaptchaEnv:
    src = os.environ if environ is None else environ
    raw = (src.get("OCTOP_CAPTCHA_PROVIDER") or "").strip()
    if not raw:
        provider = "slider"
    else:
        try:
            provider = parse_slug(raw)
        except ValueError:
            provider = raw.strip().lower()
    score_raw = (src.get("OCTOP_CAPTCHA_V3_MIN_SCORE") or "").strip()
    try:
        v3_min_score = float(score_raw) if score_raw else _DEFAULT_V3_MIN_SCORE
    except ValueError:
        v3_min_score = _DEFAULT_V3_MIN_SCORE
    return CaptchaEnv(
        provider=provider,
        site_key=(src.get("OCTOP_CAPTCHA_SITE_KEY") or "").strip(),
        secret=(src.get("OCTOP_CAPTCHA_SECRET") or "").strip(),
        v3_min_score=v3_min_score,
        cam_secret_id=(src.get("OCTOP_CAPTCHA_CAM_SECRET_ID") or "").strip(),
        cam_secret_key=(src.get("OCTOP_CAPTCHA_CAM_SECRET_KEY") or "").strip(),
    )


def install_env(env: CaptchaEnv) -> None:
    global _INSTALLED
    _INSTALLED = env


def current_env() -> CaptchaEnv:
    if _INSTALLED is None:
        return snapshot_env({})
    return _INSTALLED


def validate_boot(env: CaptchaEnv, *, has_readable_blob: bool) -> None:
    if has_readable_blob:
        return
    if env.provider == "slider":
        return
    provider = get_provider(env.provider)
    if provider is None or not provider.requires_token:
        raise ValueError(f"unknown or incomplete OCTOP_CAPTCHA_PROVIDER={env.provider!r}")
    missing: list[str] = []
    if not env.site_key:
        missing.append("OCTOP_CAPTCHA_SITE_KEY")
    if not env.secret:
        missing.append("OCTOP_CAPTCHA_SECRET")
    if env.provider == "tencent":
        if not env.cam_secret_id:
            missing.append("OCTOP_CAPTCHA_CAM_SECRET_ID")
        if not env.cam_secret_key:
            missing.append("OCTOP_CAPTCHA_CAM_SECRET_KEY")
    if missing:
        raise ValueError("incomplete captcha env (no settings blob): " + ", ".join(missing))
