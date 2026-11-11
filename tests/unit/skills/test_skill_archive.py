from __future__ import annotations

import io
import zipfile

import pytest

from octop.infra.skills.skill_archive import build_skill_zip, build_skills_zip
from octop.infra.skills.skill_packages import SkillPackageError


def test_build_skill_zip_uses_slug_folder() -> None:
    payload = build_skill_zip(
        "pack-demo",
        [
            ("SKILL.md", b"---\nname: pack-demo\n---\n# Pack\n"),
            ("refs/note.md", b"keep me"),
            ("empty/", b""),
        ],
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "pack-demo/SKILL.md" in names
        assert archive.read("pack-demo/SKILL.md").startswith(b"---")
        assert archive.read("pack-demo/refs/note.md") == b"keep me"
        assert any(name.rstrip("/") == "pack-demo/empty" for name in names)


def test_build_skills_zip_packs_each_skill_as_a_top_level_folder() -> None:
    payload = build_skills_zip(
        [
            ("alpha", [("SKILL.md", b"# Alpha\n")]),
            ("beta", [("SKILL.md", b"# Beta\n"), ("notes.txt", b"n")]),
        ]
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.read("alpha/SKILL.md") == b"# Alpha\n"
        assert archive.read("beta/SKILL.md") == b"# Beta\n"
        assert archive.read("beta/notes.txt") == b"n"


def test_build_skill_zip_rejects_missing_manifest() -> None:
    with pytest.raises(SkillPackageError):
        build_skill_zip("pack-demo", [("notes.txt", b"no manifest")])
