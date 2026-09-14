"""CaptchaProvider registry — slugs, aliases, plug-in seam."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.auth.captcha import get_provider, list_providers, parse_slug, register


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
        "turnstile",
        "hcaptcha",
        "recaptcha",
        "recaptcha-v3",
        "tencent",
    ]


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
