"""CaptchaProvider registry — slugs, aliases, plug-in seam."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.auth.captcha import get_provider, list_providers, parse_slug, register
from octop.infra.errors import ErrorCode, OctopError


def test_parse_slug_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        parse_slug("not-a-vendor")


def test_parse_slug_rejects_none() -> None:
    with pytest.raises(ValueError):
        parse_slug("none")


def test_parse_slug_accepts_slider() -> None:
    assert parse_slug("slider") == "slider"


def test_parse_slug_trims_and_lowercases() -> None:
    assert parse_slug("  Turnstile  ") == "turnstile"


def test_parse_slug_aliases_recaptcha_v3() -> None:
    assert parse_slug("recaptcha_v3") == "recaptcha-v3"


def test_parse_slug_aliases_tencent() -> None:
    assert parse_slug("tcaptcha") == "tencent"


def test_parse_slug_recaptcha_stays_v2() -> None:
    assert parse_slug("recaptcha") == "recaptcha"


def test_get_provider_slider_does_not_require_token() -> None:
    provider = get_provider("slider")
    assert provider is not None
    assert provider.requires_token is False


def test_list_providers_is_builtin_registration_order() -> None:
    assert list_providers() == [
        "slider",
        "tencent",
        "turnstile",
        "hcaptcha",
        "recaptcha-v3",
    ]


def test_unlisted_recaptcha_v2_still_resolvable() -> None:
    assert "recaptcha" not in list_providers()
    assert get_provider("recaptcha") is not None
    assert parse_slug("recaptcha") == "recaptcha"


class _FakeStrong:
    slug = "fake-strong"
    requires_token = True
    siteverify_url = "http://127.0.0.1/siteverify"
    requires_score = False
    aliases: tuple[str, ...] = ()

    def interpret(self, body: dict[str, Any], *, min_score: float) -> None:
        del body, min_score


def test_register_makes_test_double_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.auth.captcha import providers as captcha_providers

    monkeypatch.setattr(captcha_providers, "_REGISTRY", dict(captcha_providers._REGISTRY))
    register(_FakeStrong())
    assert get_provider("fake-strong") is not None
    assert parse_slug("fake-strong") == "fake-strong"


def _tencent() -> Any:
    provider = get_provider("tencent")
    assert provider is not None
    return provider


def test_tencent_verify_call_builds_tc3_signed_post() -> None:
    call = _tencent().verify_call(
        site_key="195642000",
        secret="app-secret",
        token="tr03ticket:@rand",
        client_ip="203.0.113.7",
        cam_id="AKIDcam",
        cam_key="camkey",
    )
    assert call.method == "POST"
    assert call.url == "https://captcha.tencentcloudapi.com/"
    assert call.headers is not None
    assert call.headers["Authorization"].startswith("TC3-HMAC-SHA256 Credential=AKIDcam/")
    assert call.headers["X-TC-Action"] == "DescribeCaptchaResult"
    assert call.headers["X-TC-Version"] == "2019-07-22"
    assert "Host" not in call.headers  # httpx sets it from the URL
    assert call.json_body == {
        "CaptchaType": 9,
        "Ticket": "tr03ticket",
        "Randstr": "@rand",
        "UserIp": "203.0.113.7",
        "CaptchaAppId": 195642000,
        "AppSecretKey": "app-secret",
    }


def test_tencent_verify_call_requires_cam_keys() -> None:
    with pytest.raises(OctopError) as exc:
        _tencent().verify_call(
            site_key="195642000",
            secret="app-secret",
            token="tr03ticket:@rand",
            client_ip="127.0.0.1",
        )
    assert exc.value.code == ErrorCode.CAPTCHA_FAILED


def test_tencent_verify_call_rejects_non_integer_appid() -> None:
    with pytest.raises(OctopError):
        _tencent().verify_call(
            site_key="not-an-int",
            secret="app-secret",
            token="t:@r",
            client_ip="127.0.0.1",
            cam_id="AKIDcam",
            cam_key="camkey",
        )


def test_tencent_interpret_accepts_code_one() -> None:
    _tencent().interpret({"Response": {"CaptchaCode": 1, "CaptchaMsg": "OK"}}, min_score=0.5)


def test_tencent_interpret_rejects_malicious_evil_level() -> None:
    with pytest.raises(OctopError):
        _tencent().interpret(
            {"Response": {"CaptchaCode": 1, "EvilLevel": 100}},
            min_score=0.5,
        )


@pytest.mark.parametrize("code", [7, 8, 9, 15, 16, 21, 100])
def test_tencent_interpret_rejects_failure_codes(code: int) -> None:
    with pytest.raises(OctopError):
        _tencent().interpret(
            {"Response": {"CaptchaCode": code, "CaptchaMsg": "nope"}},
            min_score=0.5,
        )


def test_tencent_interpret_rejects_api_error_envelope() -> None:
    with pytest.raises(OctopError):
        _tencent().interpret(
            {"Response": {"Error": {"Code": "UnauthorizedOperation", "Message": "nope"}}},
            min_score=0.5,
        )
