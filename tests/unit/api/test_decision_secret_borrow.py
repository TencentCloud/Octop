"""Borrowing a provider key for the decision model is gated on use and host."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.api.routers.decision import _decision_api_key
from octop.infra.errors import OctopError


class _Repo:
    def get(self, provider_id: int) -> Any:
        assert provider_id == 7
        return SimpleNamespace(
            name="openrouter",
            kind="openai",
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-borrowed",
        )


def _server() -> Any:
    return SimpleNamespace(services=SimpleNamespace(provider_repo=_Repo()))


def _user(*permissions: str) -> Any:
    return SimpleNamespace(is_admin=False, permissions=list(permissions))


def test_borrow_requires_providers_permission() -> None:
    with pytest.raises(OctopError) as exc:
        _decision_api_key(
            _server(),
            _user("model_decision"),
            typed=None,
            source_provider_id=7,
            endpoint="https://openrouter.ai/api/alpha/decisions",
        )
    assert exc.value.code == "FORBIDDEN"


def test_borrow_rejects_a_foreign_endpoint() -> None:
    with pytest.raises(OctopError) as exc:
        _decision_api_key(
            _server(),
            _user("model_decision", "providers"),
            typed=None,
            source_provider_id=7,
            endpoint="https://evil.example/decisions",
        )
    assert exc.value.code == "FORBIDDEN"


def test_borrow_rejects_a_missing_endpoint() -> None:
    with pytest.raises(OctopError):
        _decision_api_key(
            _server(),
            _user("providers"),
            typed=None,
            source_provider_id=7,
            endpoint=None,
        )


def test_borrow_allows_the_source_provider_host() -> None:
    key = _decision_api_key(
        _server(),
        _user("providers"),
        typed=None,
        source_provider_id=7,
        endpoint="https://openrouter.ai/api/alpha/decisions",
    )
    assert key == "sk-borrowed"


def test_typed_key_does_not_borrow() -> None:
    key = _decision_api_key(
        _server(),
        _user("model_decision"),
        typed="sk-typed",
        source_provider_id=7,
        endpoint="https://evil.example/decisions",
    )
    assert key == "sk-typed"
