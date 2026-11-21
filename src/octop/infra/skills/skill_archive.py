"""Pack skills into a ZIP the dashboard importer already accepts."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence

from octop.infra.skills.skill_packages import (
    SkillPackageError,
    normalize_skill_files,
    validate_skill_slug,
)


def build_skills_zip(
    skills: Sequence[tuple[str, Sequence[tuple[str, bytes]]]],
) -> bytes:
    """Return one ZIP with each skill as a top-level folder.

    The dashboard importer treats every top-level folder that contains
    ``SKILL.md`` as one skill, so this archive can be imported onto an agent
    or into a skill package in a single step.
    """
    if not skills:
        raise SkillPackageError("at least one skill is required")
    buffer = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for slug, files in skills:
            safe_slug = validate_skill_slug(slug)
            if safe_slug in seen:
                raise SkillPackageError(f"duplicate skill slug: {safe_slug}")
            seen.add(safe_slug)
            for relative_path, content in normalize_skill_files(list(files)):
                arcname = f"{safe_slug}/{relative_path}"
                if relative_path.endswith("/"):
                    info = zipfile.ZipInfo(arcname if arcname.endswith("/") else f"{arcname}/")
                    info.external_attr = 0o40755 << 16
                    archive.writestr(info, b"")
                    continue
                archive.writestr(arcname, content)
    return buffer.getvalue()


def build_skill_zip(slug: str, files: Sequence[tuple[str, bytes]]) -> bytes:
    """Return a ZIP whose only top-level folder is *slug*."""
    return build_skills_zip([(slug, files)])
