"""Install packaged supplements as workspace skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def supplements_dir() -> Path:
    """Directory of packaged skill supplements (``<slug>/SKILL.md``)."""
    return Path(__file__).resolve().parent


def supplement_paths() -> list[Path]:
    """Packaged ``SKILL.md`` files, in skill-slug order."""
    skills: list[Path] = []
    for path in sorted(supplements_dir().iterdir()):
        if path.name.startswith((".", "__")) or not path.is_dir():
            continue
        skill = path / "SKILL.md"
        if skill.is_file():
            skills.append(skill)
    return skills


def _skill_files(skill_md: Path) -> list[tuple[str, bytes]]:
    root = skill_md.parent
    slug = root.name
    pairs: list[tuple[str, bytes]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith((".", "__")) for part in rel.parts):
            continue
        pairs.append((f"skills/{slug}/{rel.as_posix()}", path.read_bytes()))
    return pairs


async def install_supplements(workspace: Any) -> None:
    """Copy each packaged skill into ``skills/<slug>/`` once.

    BackendWorkspace remaps that path under ``.octop/skills/`` for new agents.
    An existing ``SKILL.md`` is left unchanged.
    """
    pairs: list[tuple[str, bytes]] = []
    for skill in supplement_paths():
        dest = f"skills/{skill.parent.name}/SKILL.md"
        if await workspace.aexists(dest):
            continue
        pairs.extend(_skill_files(skill))
    if pairs:
        await workspace.aupload_many(pairs)
