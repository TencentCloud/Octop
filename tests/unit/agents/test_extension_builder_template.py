"""Bundled Octop Plugin and Skill Creator expert checks."""

from __future__ import annotations

import json

from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root


def test_extension_builder_template_contains_creator_skill() -> None:
    root = default_library_root() / "octop-extension-builder"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    skill = root / "skills" / "octop-extension-creator" / "SKILL.md"

    assert manifest["id"] == "octop-extension-builder"
    assert manifest["label"] == {
        "zh": "Octop 插件和 Skill 创建专家",
        "en": "Octop Plugin and Skill Creator",
    }
    assert manifest["prompt_files"] == ["SOUL.md", "AGENTS.md"]
    assert skill.is_file()
    assert "name: octop-extension-creator" in skill.read_text(encoding="utf-8")


def test_extension_builder_is_discoverable_in_catalog() -> None:
    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()

    expert = catalog.get("octop-extension-builder")

    assert expert is not None
    assert "skills/octop-extension-creator/SKILL.md" in expert.files
    assert any(row.id == "octop-extension-builder" for row in catalog.list_summaries())
