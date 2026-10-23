"""Bundled expert templates expose exactly six welcome quick-prompt cards."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.experts.skillhub_market import _SCENE_ORDER

_LIBRARY = default_library_root()


def _manifests() -> list[Path]:
    return sorted(path for path in _LIBRARY.glob("*/manifest.json") if path.is_file())


def test_every_bundled_expert_has_six_quick_prompts() -> None:
    manifests = _manifests()
    assert manifests, "expected bundled expert templates"
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        prompts = data.get("quick_prompts")
        expert_id = path.parent.name
        assert isinstance(prompts, list), expert_id
        assert len(prompts) == 6, expert_id
        titles: list[str] = []
        for card in prompts:
            for field in ("title", "description", "prompt"):
                value = card[field]
                assert isinstance(value, dict), f"{expert_id} {field}"
                assert str(value.get("zh") or "").strip(), f"{expert_id} {field}.zh"
                assert str(value.get("en") or "").strip(), f"{expert_id} {field}.en"
            assert str(card.get("icon_name") or "").strip(), expert_id
            assert str(card.get("color") or "").strip(), expert_id
            titles.append(card["title"]["zh"])
        assert len(set(titles)) == 6, expert_id


def test_bundled_experts_use_market_scenes() -> None:
    allowed = set(_SCENE_ORDER)
    catalog = ExpertCatalog(_LIBRARY)
    catalog.refresh()
    for path in _manifests():
        data = json.loads(path.read_text(encoding="utf-8"))
        expert_id = path.parent.name
        scene = str(data.get("scene") or "").strip()
        if expert_id in {"default", "general-assistant"}:
            assert scene == "", expert_id
            continue
        assert scene in allowed, expert_id
        expert = catalog.get(expert_id)
        assert expert is not None
        assert expert.summary.scene == scene
