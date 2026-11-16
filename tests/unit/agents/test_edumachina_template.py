"""Contract tests for bundled EduMachina expert template."""

from __future__ import annotations

import json
import re

from octop.infra.agents.experts.catalog import (
    bundled_avatars_dir,
    default_library_root,
    discover_bundled_avatar_ids,
    parse_task_examples,
)

EXPERT_DIR = default_library_root() / "edumachina"


def _manifest() -> dict:
    return json.loads((EXPERT_DIR / "manifest.json").read_text(encoding="utf-8"))


def _soul_body() -> str:
    raw = (EXPERT_DIR / "SOUL.md").read_text(encoding="utf-8")
    assert raw.startswith("---\n"), "SOUL.md must keep its front matter"
    return raw.split("---", 2)[2]


def test_edumachina_manifest_contract() -> None:
    manifest = _manifest()
    assert manifest["id"] == "edumachina"
    assert manifest["icon_name"] == "factory"
    assert manifest["color"] == "#0E7C66"
    assert manifest["prompt_files"] == ["SOUL.md"]
    assert len(manifest["quick_prompts"]) == 6
    assert all(
        q["title"]["zh"] and q["title"]["en"] and q["prompt"]["zh"] and q["prompt"]["en"]
        for q in manifest["quick_prompts"]
    )
    welcome = manifest["welcome_message"]
    assert welcome["zh"].strip() and welcome["en"].strip()


def test_edumachina_task_examples() -> None:
    parsed = parse_task_examples(_manifest())
    assert parsed is not None, "edumachina must declare task_examples"
    assert len(parsed["zh"]) == len(parsed["en"]) == 6
    assert all(item.strip() for item in parsed["zh"] + parsed["en"])
    # Bundled templates keep their own copy instead of the dashboard fallback.
    assert all("根据我的星座" not in item for item in parsed["zh"])


def test_edumachina_avatar_follows_library_convention() -> None:
    # Library experts ship an <expert_id>.svg under dashboard/public/experts/avatars.
    assert "edumachina" in discover_bundled_avatar_ids()
    avatars = bundled_avatars_dir()
    assert avatars is not None
    svg = avatars / "edumachina.svg"
    assert svg.is_file()
    content = svg.read_text(encoding="utf-8").lstrip()
    assert content.startswith("<svg")
    assert 'viewBox="0 0 128 128"' in content


def test_edumachina_soul_front_matter_and_rules() -> None:
    raw = (EXPERT_DIR / "SOUL.md").read_text(encoding="utf-8")
    front_matter = raw.split("---", 2)[1]
    assert "summary:" in front_matter
    assert "read_when:" in front_matter

    body = _soul_body()
    section = re.search(r"## 行为铁律\n(.*?)(?=\n## )", body, re.S)
    assert section is not None, "SOUL.md must keep the 行为铁律 section"
    rules = re.findall(r"^\d+\.\s\*\*", section.group(1), re.M)
    assert len(rules) == 11, "EduMachina ships exactly 11 行为铁律"

    # Rule 1: the compliance table is the single source of truth.
    assert "口径表是唯一事实源" in body
    # Rule 2: every conclusion carries a jurisdiction tag.
    assert "[CN]" in body and "[MY]" in body
    # Rule 10: streaming keepalive for long tasks (platform chunk timeout is
    # 120s by default) — skeleton-first, segmented output, ETA up front.
    assert "流式保活输出" in body
    assert "先骨架后填充" in body
    assert "120 秒" in body
    # Rule 11: idempotent selection/confirmation prompts.
    assert "选型/确认幂等" in body
    # Fixed compliance disclaimer footer.
    assert "〔本审查为 AI 初审，正式合规结论请由 DPO/法务复核〕" in body


def test_edumachina_kb_compliance_table() -> None:
    kb = (EXPERT_DIR / "kb_compliance.md").read_text(encoding="utf-8")
    assert "[CN]" in kb and "[MY]" in kb
    assert "跨境" in kb
    assert "变更记录" in kb
    # Unknown items must be marked, never invented from memory.
    assert "[待核实]" in kb
    assert "禁止凭记忆" in kb
