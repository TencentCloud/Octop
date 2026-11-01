"""Passkey availability for the account-security screen."""

from __future__ import annotations

import json

import pytest

from octop.infra.auth.mfa.service import MfaService
from octop.infra.auth.mfa.settings import (
    SETTINGS_KEY,
    load_view,
    passkey_block_reason,
    passwordless_login_enabled,
    save_settings,
)
from octop.infra.errors import ErrorCode, OctopError


class _Settings:
    def __init__(self, raw: str | None) -> None:
        self.raw = raw

    def get(self, key: str) -> str | None:
        if key != SETTINGS_KEY:
            return None
        return self.raw


def _configured(origin: str, rp_id: str = "octop.example.com") -> _Settings:
    return _Settings(json.dumps({"rp_id": rp_id, "origins": [origin]}))


def test_unset_public_host_is_unconfigured() -> None:
    assert passkey_block_reason(_Settings(None), "https://octop.example.com") == "unconfigured"


def test_localhost_works_without_settings() -> None:
    assert passkey_block_reason(_Settings(None), "http://localhost:8080") is None


def test_ip_host_is_blocked() -> None:
    assert passkey_block_reason(_Settings(None), "http://127.0.0.1:8080") == "ip"


def test_matching_origin_is_ready() -> None:
    origin = "https://octop.example.com"
    assert passkey_block_reason(_configured(origin), origin) is None


class _Memory:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value


def test_passwordless_login_defaults_off_and_round_trips() -> None:
    store = _Memory()
    assert load_view(store)["passwordless_login"] is False
    assert passwordless_login_enabled(store) is False

    saved = save_settings(
        store,
        {
            "passwordless_login": True,
            "rp_id": "octop.example.com",
            "origins": ["https://octop.example.com"],
        },
    )
    assert saved["passwordless_login"] is True
    assert passwordless_login_enabled(store) is True

    again = save_settings(store, {"rp_id": "octop.example.com"})
    assert again["passwordless_login"] is True

    off = save_settings(store, {"passwordless_login": False})
    assert off["passwordless_login"] is False
    assert passwordless_login_enabled(store) is False


def test_passwordless_login_ignores_non_boolean() -> None:
    store = _Memory()
    store.set(SETTINGS_KEY, json.dumps({"passwordless_login": "yes"}))
    assert passwordless_login_enabled(store) is False


def test_passwordless_login_is_rejected_until_enabled() -> None:
    class _Services:
        settings_repo = _Settings(None)

    svc = MfaService(_Services())  # type: ignore[arg-type]
    with pytest.raises(OctopError) as options_exc:
        svc.passkey_login_options(origin="http://localhost:8080")
    assert options_exc.value.code is ErrorCode.WEBAUTHN_LOGIN_DISABLED
    with pytest.raises(OctopError) as verify_exc:
        svc.passkey_login_verify(
            credential={},
            origin="http://localhost:8080",
            user_manager=None,
        )
    assert verify_exc.value.code is ErrorCode.WEBAUTHN_LOGIN_DISABLED


def test_different_origin_is_rejected() -> None:
    assert (
        passkey_block_reason(
            _configured("https://octop.example.com"),
            "http://octop.example.com",
        )
        == "origin"
    )
