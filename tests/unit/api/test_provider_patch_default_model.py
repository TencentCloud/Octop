"""The provider PATCH must not drop the dashboard's default-model choice."""

from __future__ import annotations

import json

import pytest

from octop.api.routers.providers import (
    ProviderPatchBody,
    _patch_requires_provider_rehydrate,
    _provider_patch_updates,
    _resolved_default_model,
    _with_default_model_first,
)

_CATALOG = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
_EXTRA = '{"headers": {"X-A": "1"}}'


def test_patch_body_keeps_the_default_model_field() -> None:
    """It used to be absent from the schema, so pydantic silently dropped it.

    The dashboard sends {"model": ...} when the default-model dropdown changes;
    the handler then reported success while models_json kept the old order.
    """
    body = ProviderPatchBody.model_validate({"model": "gemma-4-pro", "note": "x"})

    assert body.model == "gemma-4-pro"
    assert "model" in body.model_fields_set


def test_default_model_is_moved_to_the_front() -> None:
    models = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

    assert _with_default_model_first(models, "c") == [{"id": "c"}, {"id": "a"}, {"id": "b"}]
    assert _with_default_model_first(models, "a") == models


def test_unknown_default_model_leaves_the_list_alone() -> None:
    models = [{"id": "a"}, {"id": "b"}]

    assert _with_default_model_first(models, "missing") == models


def test_setting_a_model_moves_it_to_the_front() -> None:
    body = ProviderPatchBody.model_validate({"model": "c"})

    updates = _provider_patch_updates(body, current_extra_json=_EXTRA, current_models=_CATALOG)

    assert json.loads(updates["models_json"]) == [{"id": "c"}, {"id": "a"}, {"id": "b"}]
    assert json.loads(updates["extra_json"]) == {
        "headers": {"X-A": "1"},
        "default_model": "c",
    }
    assert _patch_requires_provider_rehydrate(body) is True


def test_omitting_model_leaves_the_default_unchanged() -> None:
    body = ProviderPatchBody.model_validate({"note": "ops memo"})

    updates = _provider_patch_updates(body, current_extra_json=_EXTRA, current_models=_CATALOG)

    assert updates == {"note": "ops memo"}
    assert _patch_requires_provider_rehydrate(body) is False


@pytest.mark.parametrize("model", ["", None, "   "])
def test_empty_model_clears_the_default(model: str | None) -> None:
    """Blank and JSON null both clear. The dashboard sends null for an empty field."""
    body = ProviderPatchBody.model_validate({"model": model})

    updates = _provider_patch_updates(body, current_extra_json=_EXTRA, current_models=_CATALOG)

    assert "models_json" not in updates
    assert json.loads(updates["extra_json"]) == {
        "headers": {"X-A": "1"},
        "default_model": None,
    }


def test_setting_the_first_model_after_a_clear_records_it_again() -> None:
    body = ProviderPatchBody.model_validate({"model": "a"})

    updates = _provider_patch_updates(
        body,
        current_extra_json='{"default_model": null}',
        current_models=[{"id": "a"}, {"id": "b"}],
    )

    assert "models_json" not in updates
    assert json.loads(updates["extra_json"])["default_model"] == "a"


def test_unknown_model_does_not_clear_or_reorder() -> None:
    body = ProviderPatchBody.model_validate({"model": "missing"})

    updates = _provider_patch_updates(body, current_extra_json=_EXTRA, current_models=_CATALOG)

    assert updates == {}


def test_model_sent_with_a_new_catalog_reorders_that_catalog() -> None:
    body = ProviderPatchBody.model_validate({"models": [{"id": "a"}, {"id": "b"}], "model": "b"})

    updates = _provider_patch_updates(
        body,
        current_extra_json=None,
        current_models=[{"id": "z"}],
    )

    assert json.loads(updates["models_json"]) == [{"id": "b"}, {"id": "a"}]
    assert json.loads(updates["extra_json"])["default_model"] == "b"


def test_resolved_default_falls_back_until_explicitly_cleared() -> None:
    assert _resolved_default_model({}, [{"id": "a"}, {"id": "b"}]) == "a"
    assert _resolved_default_model({"default_model": "b"}, [{"id": "a"}, {"id": "b"}]) == "b"
    assert _resolved_default_model({"default_model": None}, [{"id": "a"}]) is None
