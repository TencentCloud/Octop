"""Append packaged supplements onto an expert workspace ``AGENTS.md``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_AGENTS_PATH = "AGENTS.md"


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


def _marker(path: Path) -> str:
    return f"<!-- octop:supplement:{path.parent.name} -->"


def _block(path: Path) -> str:
    body = path.read_text(encoding="utf-8")
    if not body.endswith("\n"):
        body += "\n"
    return f"{_marker(path)}\n\n{body}"


def _merge(current: str, paths: list[Path]) -> str | None:
    missing = [path for path in paths if _marker(path) not in current]
    if not missing:
        return None
    addition = "\n\n".join(_block(path).rstrip() for path in missing) + "\n"
    base = current.rstrip()
    if not base:
        return addition
    return f"{base}\n\n{addition}"


async def append_supplements(workspace: Any) -> None:
    """Append every packaged supplement once. Present markers are left unchanged."""
    paths = supplement_paths()
    if not paths:
        return
    current = await workspace.aread_text(_AGENTS_PATH)
    merged = _merge(current or "", paths)
    if merged is None:
        return
    await workspace.awrite_text(_AGENTS_PATH, merged, force=True)
