"""Passkey availability for the account-security screen."""

from __future__ import annotations

import json

from octop.infra.auth.mfa.settings import SETTINGS_KEY, passkey_block_reason


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


def test_different_origin_is_rejected() -> None:
    assert (
        passkey_block_reason(
            _configured("https://octop.example.com"),
            "http://octop.example.com",
        )
        == "origin"
    )
