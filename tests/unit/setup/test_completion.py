"""Wizard completion is a persisted flag, not a user-count guess."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.setup.completion import (
    SETUP_WIZARD_COMPLETED_KEY,
    seal_setup_wizard_if_installed,
)


class _Settings:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class _Tokens:
    def __init__(self) -> None:
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1


def _server(*, users: int, settings: _Settings, tokens: _Tokens) -> SimpleNamespace:
    return SimpleNamespace(
        user_manager=SimpleNamespace(count=lambda: users),
        services=SimpleNamespace(settings_repo=settings),
        wizard_tokens=tokens,
    )


def test_seal_closes_wizard_when_users_already_exist() -> None:
    settings = _Settings()
    tokens = _Tokens()
    seal_setup_wizard_if_installed(_server(users=1, settings=settings, tokens=tokens))
    assert settings.get(SETUP_WIZARD_COMPLETED_KEY) == "1"
    assert tokens.cleared == 1

    seal_setup_wizard_if_installed(_server(users=1, settings=settings, tokens=tokens))
    assert tokens.cleared == 1


def test_seal_leaves_empty_install_open() -> None:
    settings = _Settings()
    tokens = _Tokens()
    seal_setup_wizard_if_installed(_server(users=0, settings=settings, tokens=tokens))
    assert settings.get(SETUP_WIZARD_COMPLETED_KEY) is None
    assert tokens.cleared == 0
