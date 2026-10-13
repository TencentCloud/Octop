"""tests/unit/i18n/test_skills.py"""

from __future__ import annotations

import json
from pathlib import Path

from octop.i18n import all_skill_labels, skill_display_name


def test_skill_display_name_known_zh():
    assert skill_display_name("pdf", "zh") == "PDF 处理"


def test_skill_display_name_octop_assistant_slug_zh():
    assert skill_display_name("octop-assistant", "zh") == "Octop 助手"


def test_skill_display_name_octop_assistant_name_zh():
    assert skill_display_name("octop_assistant", "zh") == "Octop 助手"


def test_skill_display_name_unknown_passthrough():
    assert skill_display_name("my-custom-skill", "en") == "my-custom-skill"


def test_skill_display_name_empty_passthrough():
    assert skill_display_name(None, "en") == ""


def test_all_skill_labels_includes_pdf():
    labels = all_skill_labels("en")
    assert labels["docx"] == "Word"
    assert labels["octop-assistant"] == "Octop Assistant"


def test_dashboard_skill_labels_match_backend():
    repo = Path(__file__).resolve().parents[3]
    dash_en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    backend_en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    for slug, label in backend_en["skills"].items():
        assert dash_en["skills"][slug] == label
