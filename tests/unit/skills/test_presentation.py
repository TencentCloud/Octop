from __future__ import annotations

from octop.infra.skills.presentation import (
    apply_skill_presentation,
    localize_skill_summary,
)


def test_apply_skill_presentation_exposes_localized_copy_and_assets() -> None:
    summary = {"slug": "pdf-reader", "name": "pdf-reader", "description": "Agent trigger"}
    frontmatter = {
        "metadata": {
            "octop": {
                "label": {"zh": "PDF 阅读", "en": "PDF Reader"},
                "summary": {"zh": "读取 PDF", "en": "Read PDFs"},
                "emoji": "📄",
                "icon_url": "https://cdn.example.com/pdf.png",
            }
        }
    }

    raw = apply_skill_presentation(summary, frontmatter)
    localized = apply_skill_presentation(summary, frontmatter, locale="zh")

    assert raw["name"] == "pdf-reader"
    assert raw["description"] == "Agent trigger"
    assert raw["label"] == {"zh": "PDF 阅读", "en": "PDF Reader"}
    assert raw["summary"] == {"zh": "读取 PDF", "en": "Read PDFs"}
    assert raw["emoji"] == "📄"
    assert raw["icon_url"] == "https://cdn.example.com/pdf.png"
    assert localized["name"] == "PDF 阅读"
    assert localized["description"] == "读取 PDF"
    assert localized["slug"] == "pdf-reader"


def test_apply_skill_presentation_keeps_identity_without_locale() -> None:
    raw = apply_skill_presentation(
        {"name": "pdf-reader", "description": "Agent trigger"},
        {"metadata": {"octop": {"display_name": "PDF Reader"}}},
    )

    assert raw["name"] == "pdf-reader"
    assert raw["display_name"] == "PDF Reader"


def test_localize_skill_summary_uses_english_then_chinese_fallback() -> None:
    summary = {
        "name": "stable-name",
        "description": "Agent trigger",
        "label": {"zh": "中文名"},
        "summary": {"zh": "中文简介"},
    }

    localized = localize_skill_summary(summary, "en")

    assert localized["name"] == "中文名"
    assert localized["description"] == "中文简介"


def test_legacy_display_name_and_compatible_emoji_remain_supported() -> None:
    localized = apply_skill_presentation(
        {"name": "stable-name", "description": "Agent trigger"},
        {
            "metadata": {
                "octop": {"display_name": "Friendly Name"},
                "openclaw": {"emoji": "📦"},
            }
        },
        locale="en",
    )

    assert localized["name"] == "Friendly Name"
    assert localized["emoji"] == "📦"
