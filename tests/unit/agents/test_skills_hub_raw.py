"""Unit tests for skills.sh / GitHub raw bundle resolution."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from octop.infra.skills import skills_hub
from octop.infra.skills.skills_hub import (
    is_supported_skill_url,
    resolve_bundle_from_url,
)

FIND_SKILLS_MD = """---
name: find-skills
description: Discover and install skills
---

# Find Skills
"""


def test_resolve_skills_sh_url_uses_raw_github_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    requested_urls: list[str] = []

    def _fake_http_text_get(url: str, params: dict | None = None) -> str:
        del params
        requested_urls.append(url)
        if url.endswith("/skills/find-skills/SKILL.md"):
            return FIND_SKILLS_MD
        raise AssertionError(f"unexpected raw fetch: {url}")

    with patch(
        "octop.infra.skills.skills_hub._http_text_get",
        side_effect=_fake_http_text_get,
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://skills.sh/vercel-labs/skills/find-skills",
        )

    assert resolved.name == "find-skills"
    assert resolved.uploads[0][0] == "skills/find-skills/SKILL.md"
    assert b"Find Skills" in resolved.uploads[0][1]
    assert requested_urls == [
        "https://raw.githubusercontent.com/vercel-labs/skills/main/skills/find-skills/SKILL.md",
    ]


def test_resolve_skills_sh_url_falls_back_to_second_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def _fake_http_text_get(url: str, params: dict | None = None) -> str:
        del params
        if "/main/" in url:
            raise HTTPError(url, 404, "Not Found", None, None)
        if url.endswith("/skills/find-skills/SKILL.md"):
            return FIND_SKILLS_MD
        raise AssertionError(f"unexpected raw fetch: {url}")

    with patch(
        "octop.infra.skills.skills_hub._http_text_get",
        side_effect=_fake_http_text_get,
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://skills.sh/vercel-labs/skills/find-skills",
        )

    assert resolved.name == "find-skills"


def test_resolve_github_url_accepts_none_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callers may pass version=None; must not crash on .strip()."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def _fake_http_text_get(url: str, params: dict | None = None) -> str:
        del params
        if url.endswith("/skills/find-skills/SKILL.md"):
            return FIND_SKILLS_MD
        raise HTTPError(url, 404, "Not Found", None, None)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("skills-repo-main/skills/find-skills/SKILL.md", FIND_SKILLS_MD)

    with (
        patch("octop.infra.skills.skills_hub._http_text_get", side_effect=_fake_http_text_get),
        patch("octop.infra.skills.skills_hub._http_bytes_get", return_value=archive.getvalue()),
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://github.com/example/skills-repo/tree/main/skills/find-skills",
            version=None,  # type: ignore[arg-type]
        )

    assert resolved.name == "find-skills"


def test_resolve_github_url_imports_all_files_from_skill_directory_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def _fake_http_text_get(url: str, params: dict | None = None) -> str:
        del params
        if url.endswith("/skills/find-skills/SKILL.md"):
            return FIND_SKILLS_MD
        raise HTTPError(url, 404, "Not Found", None, None)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("skills-repo-main/README.md", "repo root")
        zf.writestr("skills-repo-main/skills/find-skills/SKILL.md", FIND_SKILLS_MD)
        zf.writestr("skills-repo-main/skills/find-skills/references/doc.md", "# ref")
        zf.writestr("skills-repo-main/skills/find-skills/scripts/run.sh", "echo ok")
        zf.writestr("skills-repo-main/skills/find-skills/meta/config.json", "{}")

    with (
        patch("octop.infra.skills.skills_hub._http_text_get", side_effect=_fake_http_text_get),
        patch("octop.infra.skills.skills_hub._http_bytes_get", return_value=archive.getvalue()),
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://github.com/example/skills-repo/tree/main/skills/find-skills",
        )

    uploads = dict(resolved.uploads)
    assert resolved.name == "find-skills"
    assert "skills/find-skills/SKILL.md" in uploads
    assert uploads["skills/find-skills/references/doc.md"] == b"# ref"
    assert uploads["skills/find-skills/scripts/run.sh"] == b"echo ok"
    assert uploads["skills/find-skills/meta/config.json"] == b"{}"


def test_resolve_github_url_with_slash_branch_uses_encoded_archive_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    seen_archive_url: list[str] = []

    def _fake_http_text_get(url: str, params: dict | None = None) -> str:
        del params
        if "/feature/x/" in url and url.endswith("/skills/find-skills/SKILL.md"):
            return FIND_SKILLS_MD
        raise HTTPError(url, 404, "Not Found", None, None)

    def _fake_http_bytes_get(url: str, *args: object, **kwargs: object) -> bytes:
        del args, kwargs
        seen_archive_url.append(url)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("skills-repo-feature-x/skills/find-skills/SKILL.md", FIND_SKILLS_MD)
        return archive.getvalue()

    with (
        patch("octop.infra.skills.skills_hub._http_text_get", side_effect=_fake_http_text_get),
        patch("octop.infra.skills.skills_hub._http_bytes_get", side_effect=_fake_http_bytes_get),
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://github.com/example/skills-repo/tree/feature/x/skills/find-skills",
        )

    assert resolved.name == "find-skills"
    assert seen_archive_url == ["https://github.com/example/skills-repo/archive/feature%2Fx.zip"]


def test_github_archive_rejects_too_many_files(monkeypatch: pytest.MonkeyPatch) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("skills-repo-main/skills/find-skills/SKILL.md", FIND_SKILLS_MD)
        zf.writestr("skills-repo-main/skills/find-skills/a.txt", "a")

    monkeypatch.setattr(skills_hub, "_http_bytes_get", lambda *_a, **_k: archive.getvalue())

    with pytest.raises(ValueError, match="too many files"):
        skills_hub._github_collect_archive_files(
            "example",
            "skills-repo",
            "main",
            "skills/find-skills",
            max_files=1,
        )


def test_custom_import_source_can_be_enabled_without_frontend_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OCTOP_SKILLS_IMPORT_URL_PREFIXES",
        "https://market.example/skills/",
    )

    assert is_supported_skill_url("https://market.example/skills/demo")
    assert not is_supported_skill_url("https://market.example/other/demo")
    assert not is_supported_skill_url("https://market.example.evil/skills/demo")


def test_custom_json_source_resolves_through_generic_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OCTOP_SKILLS_IMPORT_URL_PREFIXES",
        "https://market.example/skills/",
    )
    payload = {
        "name": "custom-source-skill",
        "content": "---\nname: custom-source-skill\n---\n\n# Custom\n",
        "files": {"references/doc.md": "# doc"},
    }

    with patch(
        "octop.infra.skills.skills_hub._http_json_get",
        return_value=payload,
    ):
        resolved = resolve_bundle_from_url(
            bundle_url="https://market.example/skills/custom-source-skill",
        )

    assert resolved.name == "custom-source-skill"
    assert dict(resolved.uploads) == {
        "skills/custom-source-skill/SKILL.md": (
            b"---\nname: custom-source-skill\n---\n\n# Custom\n"
        ),
        "skills/custom-source-skill/references/doc.md": b"# doc",
    }
