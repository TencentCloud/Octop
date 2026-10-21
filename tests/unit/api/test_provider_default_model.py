"""Unit tests: the provider payload carries the saved default model only."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from octop.api.routers.providers import _row_to_dict


def _row(extra_json: str | None) -> Any:
    models = [{"id": "first", "name": "First"}, {"id": "second", "name": "Second"}]
    return SimpleNamespace(
        id=1,
        name="custom",
        kind="openai",
        base_url=None,
        api_key=None,
        note=None,
        enabled=True,
        extra_json=extra_json,
        get_models=lambda: models,
    )


def test_no_saved_default_is_null_not_the_first_model() -> None:
    """The dashboard must not see a default the user never picked (#2031)."""
    assert _row_to_dict(_row(None))["default_model"] is None


def test_saved_default_is_returned() -> None:
    row = _row(json.dumps({"default_model": "second"}))

    assert _row_to_dict(row)["default_model"] == "second"


def test_cleared_default_stays_null() -> None:
    row = _row(json.dumps({"default_model": None}))

    assert _row_to_dict(row)["default_model"] is None
