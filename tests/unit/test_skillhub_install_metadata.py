from __future__ import annotations

from octop.api.routers.skills import (
    _summary_dict,
    _valid_skillhub_icon_url,
    _with_skillhub_presentation_metadata,
)


def test_summary_prefers_octop_display_metadata_and_supports_openclaw_emoji() -> None:
    summary = _summary_dict(
        "stable-slug",
        {
            "name": "english-name",
            "metadata": {
                "octop": {
                    "display_name": "中文名称",
                    "icon_url": "https://cdn.example.com/icon.png",
                },
                "openclaw": {"emoji": "📦"},
            },
        },
        enabled=True,
        kind="workspace",
    )

    assert summary["slug"] == "stable-slug"
    assert summary["name"] == "中文名称"
    assert summary["icon_url"] == "https://cdn.example.com/icon.png"
    assert summary["emoji"] == "📦"


def test_with_skillhub_metadata_preserves_skill_identity_and_body() -> None:
    original = (
        "---\nname: english-name\nmetadata:\n  openclaw:\n    emoji: '📦'\n---\n\n# Original body\n"
    )

    rendered = _with_skillhub_presentation_metadata(
        original,
        display_name="中文名称",
        icon_url="https://cdn.example.com/icon.png",
    )

    assert "name: english-name" in rendered
    assert "display_name: 中文名称" in rendered
    assert "icon_url: https://cdn.example.com/icon.png" in rendered
    assert "emoji: 📦" in rendered
    assert rendered.endswith("# Original body\n")


def test_skillhub_icon_url_allows_only_http_urls() -> None:
    assert _valid_skillhub_icon_url("https://cdn.example.com/icon.png")
    assert _valid_skillhub_icon_url("http://cdn.example.com/icon.png")
    assert not _valid_skillhub_icon_url("javascript:alert(1)")
    assert not _valid_skillhub_icon_url("/relative/icon.png")
