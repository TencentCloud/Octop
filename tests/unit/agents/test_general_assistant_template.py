"""Sanity checks for the bundled general-assistant template."""

from __future__ import annotations

import json

from octop.infra.agents.experts.catalog import default_library_root

_DIR = default_library_root() / "general-assistant"


def test_all_required_files_present() -> None:
    for name in ("SOUL.md", "manifest.json", "skills/agentbuddy-assistant/SKILL.md"):
        assert (_DIR / name).is_file(), f"missing {name}"


def test_meta_yaml_has_id_and_display_name() -> None:
    meta = json.loads((_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert meta["id"] == "general-assistant"
    label = meta.get("label")
    assert isinstance(label, dict) and isinstance(label.get("en"), str) and label["en"]


def test_skills_json_is_a_list() -> None:
    meta = json.loads((_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(meta.get("prompt_files", []), list)
