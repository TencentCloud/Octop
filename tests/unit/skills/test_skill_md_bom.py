"""Skills API reads SKILL.md through the shared frontmatter helper (#2215)."""

from __future__ import annotations

from octop.api.routers import skills as skills_router
from octop.infra.utils.frontmatter import parse_frontmatter


def test_skills_router_uses_shared_parse_frontmatter() -> None:
    assert skills_router.parse_frontmatter is parse_frontmatter


def test_bom_prefixed_skill_md_keeps_its_frontmatter() -> None:
    text = "\ufeff---\nname: demo\ndescription: Demo skill\n---\n# Body\n"

    meta, body = skills_router.parse_frontmatter(text)

    assert meta == {"name": "demo", "description": "Demo skill"}
    assert body.startswith("# Body")
    assert "\ufeff" not in body


def test_plain_skill_md_is_unaffected() -> None:
    meta, body = skills_router.parse_frontmatter("---\nname: demo\n---\n# Body\n")
    assert meta == {"name": "demo"}
    assert body.startswith("# Body")
