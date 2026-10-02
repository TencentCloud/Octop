"""Unit tests for provider name validation."""

from __future__ import annotations

import pytest

from octop.infra.agents.providers.names import validate_provider_name
from octop.infra.errors import ErrorCode, OctopError


def test_accepts_plain_name() -> None:
    assert validate_provider_name("shared-gpt") == "shared-gpt"


def test_strips_surrounding_whitespace() -> None:
    assert validate_provider_name("  lite-api  ") == "lite-api"


@pytest.mark.parametrize(
    "name",
    [
        "https://api.openai.com/",
        "a/b",
        "/",
    ],
)
def test_rejects_slash(name: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_provider_name(name)
    assert excinfo.value.code == ErrorCode.PROVIDER_NAME_INVALID


@pytest.mark.parametrize("name", ["", "   "])
def test_rejects_empty(name: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_provider_name(name)
    assert excinfo.value.code == ErrorCode.PROVIDER_NAME_INVALID
