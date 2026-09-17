"""Login captcha providers: contract, default implementation, registry.

Four layers (execution lives in ``octop.infra.auth.captcha.verify``):

1. Contract — ``CaptchaProvider`` (Protocol): metadata plus
   ``verify_call()`` (token + credentials -> outbound request spec) and
   ``interpret()`` (vendor response body -> pass/fail). Structural typing
   lets plugins register providers without importing a base class.
2. Default implementation — ``_FormPostProvider``: form-POST plus
   ``success == true`` verdict, shared by turnstile/hcaptcha/recaptcha-v2;
   those vendors differ only by ``siteverify_url``.
3. Execution — ``verify.ensure_captcha``: the only layer with outbound I/O
   (timeout, error -> ``OctopError`` mapping, ``set_test_siteverify_url``
   test seam). Providers stay pure.
4. Registry — ``register`` / ``get_provider`` / ``list_providers`` /
   ``parse_slug`` with aliases and the ``listed`` flag: unlisted providers
   stay resolvable for existing configs but are not offered in settings.

Settled design decisions (re-litigate only with new data):

- The slider is a pseudo-provider (``requires_token=False``): the local
  unverified fallback kept inside one unified config/UI list.
- Verification failures surface as one blunt ``CAPTCHA_FAILED`` message;
  vendor nuance belongs in server logs, not user-facing strings.
- No automatic siteverify retry: user retry covers vendor blips; an
  in-request retry would add login-path latency for marginal gain.
- Dashboard widget metadata (script URLs, modes) stays hardcoded in the
  frontend bundle (auditable, CSP-friendly), not served by the API.

Adding a vendor: one provider dataclass here + one ``register()`` call in
``_register_builtins`` + one widget adapter in
``dashboard/src/pages/Login/captchaAdapters.ts``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.tencent_sign import tc3_headers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifyCall:
    """One outbound siteverify request."""

    method: str
    url: str
    data: dict[str, str] | None = None
    params: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    json_body: dict[str, Any] | None = None


class CaptchaProvider(Protocol):
    """Read-only metadata so frozen-dataclass providers satisfy the contract."""

    @property
    def slug(self) -> str: ...
    @property
    def requires_token(self) -> bool: ...
    @property
    def siteverify_url(self) -> str | None: ...
    @property
    def requires_score(self) -> bool: ...
    @property
    def aliases(self) -> tuple[str, ...]: ...
    @property
    def listed(self) -> bool: ...

    def verify_call(
        self,
        *,
        site_key: str,
        secret: str,
        token: str,
        client_ip: str,
        cam_id: str = "",
        cam_key: str = "",
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
    listed: bool = True

    def verify_call(
        self,
        *,
        site_key: str,
        secret: str,
        token: str,
        client_ip: str,
        cam_id: str = "",
        cam_key: str = "",
    ) -> VerifyCall:
        raise AssertionError("slider never verifies remotely")

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del body, min_score


@dataclass(frozen=True)
class _FormPostProvider:
    """Default implementation: form-POST siteverify, ``success == true``."""

    slug: str
    siteverify_url: str | None
    requires_token: bool = True
    requires_score: bool = False
    aliases: tuple[str, ...] = ()
    listed: bool = True

    def verify_call(
        self,
        *,
        site_key: str,
        secret: str,
        token: str,
        client_ip: str,
        cam_id: str = "",
        cam_key: str = "",
    ) -> VerifyCall:
        del site_key, client_ip, cam_id, cam_key
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
    listed: bool = True

    def verify_call(
        self,
        *,
        site_key: str,
        secret: str,
        token: str,
        client_ip: str,
        cam_id: str = "",
        cam_key: str = "",
    ) -> VerifyCall:
        del site_key, client_ip, cam_id, cam_key
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
    """Tencent Cloud Captcha ticket check (DescribeCaptchaResult, API 3.0).

    The login token carries the frontend callback pair as ``ticket:randstr``;
    ``site_key`` is the CaptchaAppId and ``secret`` is the AppSecretKey.
    Ticket verification is signed with CAM API keys (``cam_id``/``cam_key``),
    see https://cloud.tencent.com/document/product/1110/36926.
    """

    slug: str = "tencent"
    requires_token: bool = True
    siteverify_url: str | None = "https://captcha.tencentcloudapi.com/"
    requires_score: bool = False
    aliases: tuple[str, ...] = ("tcaptcha",)
    listed: bool = True

    def verify_call(
        self,
        *,
        site_key: str,
        secret: str,
        token: str,
        client_ip: str,
        cam_id: str = "",
        cam_key: str = "",
    ) -> VerifyCall:
        ticket, sep, randstr = token.partition(":")
        if not sep or not ticket or not randstr:
            raise _failed()
        if not cam_id or not cam_key:
            logger.warning(
                "tencent captcha ticket verification needs CAM API keys "
                "(captcha settings cam_secret_id/cam_secret or OCTOP_CAPTCHA_CAM_SECRET_*)"
            )
            raise _failed()
        try:
            app_id = int(site_key)
        except ValueError:
            logger.warning("tencent captcha site_key %r is not an integer CaptchaAppId", site_key)
            raise _failed() from None
        payload: dict[str, Any] = {
            "CaptchaType": 9,
            "Ticket": ticket,
            "Randstr": randstr,
            "UserIp": client_ip,
            "CaptchaAppId": app_id,
            "AppSecretKey": secret,
        }
        headers, _body = tc3_headers(
            secret_id=cam_id,
            secret_key=cam_key,
            service="captcha",
            host="captcha.tencentcloudapi.com",
            action="DescribeCaptchaResult",
            version="2019-07-22",
            payload=payload,
        )
        # httpx sets Host from the request URL (same value the signature
        # covers); sending it explicitly would let host-routing proxies
        # intercept test/mock calls.
        headers.pop("Host", None)
        return VerifyCall(
            method="POST",
            url=self.siteverify_url or "",
            headers=headers,
            json_body=payload,
        )

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del min_score
        response = body.get("Response")
        if not isinstance(response, dict):
            logger.warning("tencent captcha response has no Response object")
            raise _failed()
        if response.get("Error"):
            err = response["Error"]
            logger.warning(
                "tencent captcha api error: code=%r message=%r",
                err.get("Code"),
                err.get("Message"),
            )
            raise _failed()
        code = response.get("CaptchaCode")
        evil = response.get("EvilLevel")
        if code == 1 and evil != 100:
            return
        logger.warning(
            "tencent captcha rejected: code=%r msg=%r evil_level=%r",
            code,
            response.get("CaptchaMsg"),
            evil,
        )
        raise _failed()


_TURNSTILE = _FormPostProvider(
    slug="turnstile",
    siteverify_url="https://challenges.cloudflare.com/turnstile/v0/siteverify",
)
_HCAPTCHA = _FormPostProvider(
    slug="hcaptcha",
    siteverify_url="https://api.hcaptcha.com/siteverify",
)
_RECAPTCHA = _FormPostProvider(
    slug="recaptcha",
    siteverify_url="https://www.google.com/recaptcha/api/siteverify",
    # Unlisted: no verified deployment key yet; stays resolvable for
    # existing configs but is not offered in the settings catalog.
    listed=False,
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
    return [slug for slug, provider in _REGISTRY.items() if provider.listed]


def parse_slug(raw: str) -> str:
    key = raw.strip().lower()
    if key in _REGISTRY:
        return key
    aliased = _ALIASES.get(key)
    if aliased is not None:
        return aliased
    raise ValueError(f"unknown captcha provider: {raw}")


def _register_builtins() -> None:
    for provider in (_SLIDER, _TENCENT, _TURNSTILE, _HCAPTCHA, _RECAPTCHA, _RECAPTCHA_V3):
        register(provider)


_register_builtins()
_check_c: CaptchaProvider = _TURNSTILE
_check_d: CaptchaProvider = _HCAPTCHA
_check_e: CaptchaProvider = _RECAPTCHA
_check_f: CaptchaProvider = _RECAPTCHA_V3
