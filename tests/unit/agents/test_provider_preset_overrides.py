"""Unit tests for publisher preset overrides (``~/.octop/provider_presets.json``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.providers.presets import (
    apply_preset_overrides,
    load_preset_overrides,
    preset_overrides_path,
)
from octop.infra.errors import ErrorCode, OctopError


def _preset(preset_id: str, name: str, group: str = "", group_name: str = "") -> dict[str, Any]:
    preset: dict[str, Any] = {"id": preset_id, "name": name}
    if group:
        preset["provider_group"] = group
        preset["provider_group_name"] = group_name or group.title()
    return preset


@pytest.fixture
def shipped() -> list[dict[str, Any]]:
    """Template order on purpose: groups interleaved with loose presets."""
    return [
        _preset("zhipu", "Zhipu", "zhipu"),
        _preset("openai", "OpenAI"),
        _preset("hunyuan", "Hunyuan", "tencent"),
        _preset("tokenhub", "TokenHub", "tencent"),
        _preset("kimi", "Kimi", "kimi"),
        _preset("moonshot", "Moonshot"),
    ]


def test_no_overrides_keeps_default_group_order(shipped: list[dict[str, Any]]) -> None:
    ordered = apply_preset_overrides(shipped, {})
    assert [p["id"] for p in ordered] == [
        "hunyuan",
        "tokenhub",
        "kimi",
        "zhipu",
        "moonshot",
        "openai",
    ]


def test_hidden_matches_preset_id_and_group(shipped: list[dict[str, Any]]) -> None:
    ordered = apply_preset_overrides(shipped, {"hidden": ["openai", "tencent"]})
    assert [p["id"] for p in ordered] == ["kimi", "zhipu", "moonshot"]


def test_order_promotes_groups_and_presets(shipped: list[dict[str, Any]]) -> None:
    ordered = apply_preset_overrides(shipped, {"order": ["kimi", "moonshot", "tencent"]})
    assert [p["id"] for p in ordered] == [
        "kimi",
        "hunyuan",
        "tokenhub",
        "zhipu",
        "moonshot",
        "openai",
    ]


def test_group_names_renames_brand_cards(shipped: list[dict[str, Any]]) -> None:
    ordered = apply_preset_overrides(shipped, {"group_names": {"tencent": "TokenHub"}})
    renamed = [p for p in ordered if p.get("provider_group") == "tencent"]
    assert {p["provider_group_name"] for p in renamed} == {"TokenHub"}
    assert next(p for p in ordered if p["id"] == "kimi")["provider_group_name"] == "Kimi"


def test_unknown_group_sorts_after_known_ones() -> None:
    presets = [_preset("acme", "Acme", "acme"), _preset("kimi", "Kimi", "kimi")]
    ordered = apply_preset_overrides(presets, {"order": ["acme"]})
    assert [p["provider_group"] for p in ordered] == ["acme", "kimi"]


def test_overrides_path_follows_octop_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    assert preset_overrides_path() == tmp_path / "provider_presets.json"


def test_missing_file_means_no_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    assert load_preset_overrides() == {}


def test_corrupt_file_raises_without_touching_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    preset_overrides_path().write_text("{", encoding="utf-8")
    with pytest.raises(OctopError) as excinfo:
        load_preset_overrides()
    assert excinfo.value.code is ErrorCode.CONFIG_FILE_CORRUPT
