"""Bundled expert templates expose tasks-page ``task_examples``."""

from __future__ import annotations

import json
from pathlib import Path

from octop.infra.agents.experts.catalog import default_library_root, parse_task_examples

_LIBRARY = default_library_root()


def _iter_manifests() -> list[Path]:
    return sorted(path for path in _LIBRARY.glob("*/manifest.json") if path.is_file())


def test_every_bundled_expert_declares_task_examples() -> None:
    manifests = _iter_manifests()
    assert manifests, "expected bundled expert templates"
    for path in manifests:
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_task_examples(data)
        assert parsed is not None, f"{path.parent.name} missing task_examples"
        assert parsed["zh"], f"{path.parent.name} has empty zh task_examples"
        assert parsed["en"], f"{path.parent.name} has empty en task_examples"
        assert len(parsed["zh"]) == len(parsed["en"]), path.parent.name
        assert len(parsed["zh"]) in (3, 6), path.parent.name
        assert all(item.strip() for item in parsed["zh"] + parsed["en"])


def test_domain_experts_offer_six_task_examples() -> None:
    """Recurring-work templates keep a full two-column empty state."""
    richer = (
        "news-trend",
        "stock-assistant",
        "ops-engineer",
        "parenting-companion",
    )
    for expert_id in richer:
        data = json.loads((_LIBRARY / expert_id / "manifest.json").read_text(encoding="utf-8"))
        parsed = parse_task_examples(data)
        assert parsed is not None
        assert len(parsed["zh"]) == 6, expert_id


def test_general_templates_do_not_copy_dashboard_default_cards() -> None:
    """i18n defaults stay the no-field fallback; bundled templates keep their own copy."""
    dashboard_zh = "根据我的星座"
    for expert_id in ("general-assistant", "default"):
        data = json.loads((_LIBRARY / expert_id / "manifest.json").read_text(encoding="utf-8"))
        parsed = parse_task_examples(data)
        assert parsed is not None
        assert all(dashboard_zh not in item for item in parsed["zh"])
