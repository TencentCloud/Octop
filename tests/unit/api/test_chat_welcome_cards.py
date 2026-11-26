"""Quick cards of an expert's chat welcome screen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from octop.api.routers.chat.routes import workspace_welcome_payload
from octop.infra.agents.experts.catalog import (
    ExpertCatalog,
    default_welcome_payload,
)

CARDS = [{"title": {"zh": "查资质"}, "description": {"zh": ""}, "prompt": {"zh": "查"}}]


@pytest.fixture
def catalog(tmp_path: Path) -> ExpertCatalog:
    # An empty library: the default is the small built-in card set.
    expert_catalog = ExpertCatalog(tmp_path / "library")
    expert_catalog.refresh()
    return expert_catalog


def _prompts(payload: dict[str, Any]) -> list[Any]:
    return payload["quick_prompts"]


def test_manifest_without_cards_gets_the_defaults(catalog: ExpertCatalog) -> None:
    assert _prompts(workspace_welcome_payload({"id": "x"}, catalog)) == _prompts(
        default_welcome_payload(catalog)
    )
    assert _prompts(workspace_welcome_payload(None, catalog)) == _prompts(
        default_welcome_payload(catalog)
    )


def test_manifest_with_cards_keeps_them(catalog: ExpertCatalog) -> None:
    payload = workspace_welcome_payload({"id": "x", "quick_prompts": CARDS}, catalog)
    assert [card["title"] for card in _prompts(payload)] == [{"zh": "查资质", "en": "查资质"}]


def test_explicitly_empty_card_list_shows_no_cards(catalog: ExpertCatalog) -> None:
    """An expert set up with no cards must not fall back to the defaults."""
    payload = workspace_welcome_payload({"id": "x", "quick_prompts": []}, catalog)
    assert _prompts(payload) == []
    assert payload["welcome_message"] == {"zh": "", "en": ""}


def test_non_list_card_value_still_gets_the_defaults(catalog: ExpertCatalog) -> None:
    """Only a list is the author's decision; ``null``/text is malformed, not empty."""
    assert _prompts(workspace_welcome_payload({"quick_prompts": None}, catalog)) == _prompts(
        default_welcome_payload(catalog)
    )
    assert _prompts(workspace_welcome_payload({"quick_prompts": "none"}, catalog)) == _prompts(
        default_welcome_payload(catalog)
    )
