"""The provider PATCH must not drop the dashboard's default-model choice."""

from __future__ import annotations

from octop.api.routers.providers import ProviderPatchBody, _with_default_model_first


def test_patch_body_keeps_the_default_model_field() -> None:
    """It used to be absent from the schema, so pydantic silently dropped it.

    The dashboard sends {"model": ...} when the default-model dropdown changes;
    the handler then reported success while models_json kept the old order.
    """
    body = ProviderPatchBody.model_validate({"model": "gemma-4-pro", "note": "x"})

    assert body.model == "gemma-4-pro"


def test_default_model_is_moved_to_the_front() -> None:
    models = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

    assert _with_default_model_first(models, "c") == [{"id": "c"}, {"id": "a"}, {"id": "b"}]
    assert _with_default_model_first(models, "a") == models


def test_unknown_default_model_leaves_the_list_alone() -> None:
    models = [{"id": "a"}, {"id": "b"}]

    assert _with_default_model_first(models, "missing") == models
