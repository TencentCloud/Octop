"""CaptchaProvider registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifyCall:
    """One outbound siteverify request."""

    method: str
    url: str
    data: dict[str, str] | None = None
    params: dict[str, str] | None = None


class CaptchaProvider(Protocol):
    slug: str
    requires_token: bool
    siteverify_url: str | None
    requires_score: bool
    aliases: tuple[str, ...]

    def verify_call(
        self, *, site_key: str, secret: str, token: str, client_ip: str
    ) -> VerifyCall: ...

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None: ...


def _failed() -> OctopError:
    return OctopError(
        ErrorCode.CAPTCHA_FAILED,
        "Captcha verification failed. Try again.",
    )


def _form_call(siteverify_url: str | None, secret: str, token: str) -> VerifyCall:
    return VerifyCall(
        method="POST",
        url=siteverify_url or "",
        data={"secret": secret, "response": token},
    )


@dataclass(frozen=True)
class _SliderProvider:
    slug: str = "slider"
    requires_token: bool = False
    siteverify_url: str | None = None
    requires_score: bool = False
    aliases: tuple[str, ...] = ()

    def verify_call(self, *, site_key: str, secret: str, token: str, client_ip: str) -> VerifyCall:
        raise AssertionError("slider never verifies remotely")

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del body, min_score


@dataclass(frozen=True)
class _SuccessProvider:
    slug: str
    siteverify_url: str | None
    requires_token: bool = True
    requires_score: bool = False
    aliases: tuple[str, ...] = ()

    def verify_call(self, *, site_key: str, secret: str, token: str, client_ip: str) -> VerifyCall:
        del site_key, client_ip
        return _form_call(self.siteverify_url, secret, token)

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del min_score
        if body.get("success") is not True:
            raise _failed()


@dataclass(frozen=True)
class _RecaptchaV3Provider:
    slug: str = "recaptcha-v3"
    requires_token: bool = True
    siteverify_url: str | None = "https://www.google.com/recaptcha/api/siteverify"
    requires_score: bool = True
    aliases: tuple[str, ...] = ("recaptcha_v3",)

    def verify_call(self, *, site_key: str, secret: str, token: str, client_ip: str) -> VerifyCall:
        del site_key, client_ip
        return _form_call(self.siteverify_url, secret, token)

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        if body.get("success") is not True:
            raise _failed()
        score = body.get("score")
        if not isinstance(score, (int, float)) or float(score) < min_score:
            raise _failed()
        if body.get("action") != "login":
            raise _failed()


@dataclass(frozen=True)
class _TencentProvider:
    """Tencent Cloud Captcha ticket check (ssl.captcha.qq.com/ticket/verify).

    The login token carries the frontend callback pair as ``ticket:randstr``;
    ``site_key`` is the CaptchaAppId and ``secret`` is the AppSecretKey.
    """

    slug: str = "tencent"
    requires_token: bool = True
    siteverify_url: str | None = "https://ssl.captcha.qq.com/ticket/verify"
    requires_score: bool = False
    aliases: tuple[str, ...] = ("tcaptcha",)

    def verify_call(self, *, site_key: str, secret: str, token: str, client_ip: str) -> VerifyCall:
        ticket, sep, randstr = token.partition(":")
        if not sep or not ticket or not randstr:
            raise _failed()
        return VerifyCall(
            method="GET",
            url=self.siteverify_url or "",
            params={
                "aid": site_key,
                "AppSecretKey": secret,
                "Ticket": ticket,
                "Randstr": randstr,
                "UserIP": client_ip,
            },
        )

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del min_score
        if str(body.get("response")) != "1":
            logger.warning(
                "tencent captcha rejected: response=%r err_msg=%r evil_level=%r",
                body.get("response"),
                body.get("err_msg"),
                body.get("evil_level"),
            )
            raise _failed()


_TURNSTILE = _SuccessProvider(
    slug="turnstile",
    siteverify_url="https://challenges.cloudflare.com/turnstile/v0/siteverify",
)
_HCAPTCHA = _SuccessProvider(
    slug="hcaptcha",
    siteverify_url="https://api.hcaptcha.com/siteverify",
)
_RECAPTCHA = _SuccessProvider(
    slug="recaptcha",
    siteverify_url="https://www.google.com/recaptcha/api/siteverify",
)
_RECAPTCHA_V3 = _RecaptchaV3Provider()
_TENCENT = _TencentProvider()
_SLIDER = _SliderProvider()

_REGISTRY: dict[str, CaptchaProvider] = {}
_ALIASES: dict[str, str] = {}


def _alias_targets() -> set[str]:
    return set(_REGISTRY) | set(_ALIASES)


def register(provider: CaptchaProvider) -> None:
    for alias in provider.aliases:
        key = alias.strip().lower()
        if not key:
            continue
        owner = _ALIASES.get(key) or (key if key in _REGISTRY else None)
        if owner is not None and owner != provider.slug:
            raise ValueError(f"captcha alias already registered: {key}")
    _REGISTRY[provider.slug] = provider
    for alias in provider.aliases:
        _ALIASES[alias.strip().lower()] = provider.slug


def get_provider(slug: str) -> CaptchaProvider | None:
    return _REGISTRY.get(slug)


def list_providers() -> list[str]:
    return list(_REGISTRY)


def parse_slug(raw: str) -> str:
    key = raw.strip().lower()
    if key in _REGISTRY:
        return key
    aliased = _ALIASES.get(key)
    if aliased is not None:
        return aliased
    raise ValueError(f"unknown captcha provider: {raw}")


def _register_builtins() -> None:
    for provider in (_SLIDER, _TURNSTILE, _HCAPTCHA, _RECAPTCHA, _RECAPTCHA_V3, _TENCENT):
        register(cast(CaptchaProvider, provider))


_register_builtins()
