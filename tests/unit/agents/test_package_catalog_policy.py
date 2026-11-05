"""Package identity must win over shared endpoints and historical imports."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from octop.infra.agents.providers.catalog import package_preset, provider_models
from octop.infra.agents.providers.resolved import list_resolved_models
from octop.infra.agents.providers.store import ProviderStore
from octop.infra.db.repos.providers import ProviderRow


def _row(name: str = "Tencent Cloud Hy Token Plan", **kwargs: object) -> ProviderRow:
    data = {
        "id": 7,
        "name": name,
        "kind": "openai",
        "base_url": "https://api.lkeap.cloud.tencent.com/plan/v3",
        "api_key": "test-key",
        "extra_json": None,
        "models_json": json.dumps(
            [
                {"id": "hy3", "name": "My Hy3", "enabled": False},
                {"id": "glm-5", "name": "Foreign model", "enabled": True},
                {"id": "hy4", "name": "Hy4", "enabled": True},
            ]
        ),
        "note": None,
        "enabled": 1,
        "created_at": 1,
        "updated_at": 1,
    }
    data.update(kwargs)
    return ProviderRow.from_row(data)


def test_packages_on_same_url_have_independent_catalogs() -> None:
    hy = package_preset("Tencent Cloud Hy Token Plan")
    token = package_preset("Tencent Cloud Token Plan")
    assert hy is not None and token is not None
    assert hy["base_url"] == token["base_url"]
    assert [m["id"] for m in hy["models"]] == ["hy4", "hy3", "hy3-preview"]
    assert "glm-5" in {m["id"] for m in token["models"]}
    assert "hy3" not in {m["id"] for m in token["models"]}


def test_legacy_models_are_scoped_without_changing_stored_default_or_metadata() -> None:
    row = _row()
    assert [m["id"] for m in provider_models(row)] == ["hy3", "hy4"]
    assert [m["id"] for m in provider_models(row, display_order=True)] == ["hy4", "hy3"]
    assert provider_models(row)[0] == {"id": "hy3", "name": "My Hy3", "enabled": False}
    assert len(row.get_models()) == 3  # Reads do not rewrite historical data.


def test_runtime_and_resolved_pool_cannot_select_a_foreign_enabled_model() -> None:
    repo = MagicMock()
    repo.list_all.return_value = [_row()]
    store = ProviderStore(repo)
    configs = store.build_harness_configs()
    assert [m.id for m in configs[0].models] == ["hy4"]
    assert [m["model"] for m in list_resolved_models([_row()])] == ["hy4"]


def test_preset_identity_survives_custom_names_and_does_not_match_by_url() -> None:
    extra = json.dumps({"preset_id": "tencent-hy-token-plan"})
    assert [m["id"] for m in provider_models(_row("My package", extra_json=extra))] == [
        "hy3",
        "hy4",
    ]
    custom = _row("My custom provider")
    assert provider_models(custom) == custom.get_models()
    assert package_preset("My package", preset_id="tencent-token-plan")["id"] == (
        "tencent-token-plan"
    )


def test_custom_provider_without_models_is_unchanged() -> None:
    row = SimpleNamespace(name="Custom", extra_json=None, get_models=lambda: [])
    assert provider_models(row) == []
