"""Packaged template helpers (read packaged ``builtin/`` resources).

The init/bootstrap *orchestration* lives on :meth:`HarnessAgent.init_workspace()`;
this module is the pure resource-reading layer it depends on.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib import resources
from importlib.resources.abc import Traversable

logger = logging.getLogger(__name__)

MD_FILES_PACKAGE = "octop_harness.builtin.md_files"
BUILTIN_SKILLS_PACKAGE = "octop_harness.builtin.skills"
BUILTIN_AGENTS_PACKAGE = "octop_harness.builtin.agents"


def iter_md_template_files(language: str) -> list[tuple[str, bytes]]:
    """Read packaged markdown templates for the given language.

    Reads from ``builtin/md_files/{language}/*.md``. Skips dunder and
    dot-prefixed files. Returns sorted ``(filename, content_bytes)`` pairs.

    Raises:
        FileNotFoundError: If the language subdirectory does not exist.
    """
    package_root: Traversable = resources.files(MD_FILES_PACKAGE)
    lang_dir = package_root.joinpath(language)

    # Traversable doesn't have a simple .exists() — try iterating.
    try:
        entries = list(lang_dir.iterdir())
    except (FileNotFoundError, TypeError, OSError) as exc:
        raise FileNotFoundError(
            f"No template directory for language {language!r} in {MD_FILES_PACKAGE}",
        ) from exc

    out: list[tuple[str, bytes]] = []
    for entry in entries:
        if entry.name.startswith((".", "__")):
            continue
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        out.append((entry.name, entry.read_bytes()))
    out.sort(key=lambda pair: pair[0])
    return out


def iter_builtin_skills(language: str) -> list[tuple[str, str, bytes, bool]]:
    """Read packaged built-in skills for the given language.

    Reads from ``builtin/skills/{language}/<skill>/...``.  Returns
    ``(actual_lang, rel_path, content_bytes, is_fallback)`` tuples for
    every file under each skill directory.

    ``actual_lang`` is the language actually served (``language`` or
    ``"en"`` when a fallback occurred).

    ``is_fallback`` is ``True`` when *language* was missing and we served
    ``"en"``.

    When *language* is not ``"en"``, implements **file-level fallback**:
    files present in *language* are served from there; missing files are
    filled in from ``"en"``.  This allows ``zh/`` to contain only
    translated ``SKILL.md`` files while inheriting supplemental files
    (``templates/``, ``references/``, ``.sh`` scripts, etc.) from
    ``en/``.
    """
    if language == "en":
        return _iter_language_tree(BUILTIN_SKILLS_PACKAGE, "en", _is_skill_dir)

    package_root: Traversable = resources.files(BUILTIN_SKILLS_PACKAGE)
    lang_dir = package_root.joinpath(language)

    # Check if language directory exists.
    try:
        list(lang_dir.iterdir())
    except (FileNotFoundError, TypeError, OSError):
        # No language directory -> full fallback to "en".
        return _iter_language_tree(BUILTIN_SKILLS_PACKAGE, "en", _is_skill_dir)

    # File-level merge: collect "en" files, then overlay "language" files.
    merged: dict[str, tuple[str, bytes, bool]] = {}

    # Pass 1: all "en" files (marked as fallback).
    en_dir = package_root.joinpath("en")
    for entry in en_dir.iterdir():
        if entry.name.startswith((".", "__")) or not _is_skill_dir(entry):
            continue
        _collect_files_merged(entry, f"{entry.name}/", "en", True, merged)

    # Pass 2: overlay "language" files (is_fallback=False).
    for entry in lang_dir.iterdir():
        if entry.name.startswith((".", "__")) or not _is_skill_dir(entry):
            continue
        _collect_files_merged(entry, f"{entry.name}/", language, False, merged)

    # Sort by relative path and convert to list.
    return [
        (actual_lang, path, content, is_fallback)
        for path, (actual_lang, content, is_fallback) in sorted(merged.items())
    ]


def iter_builtin_agents(language: str) -> list[tuple[str, str, bytes, bool]]:
    """Read packaged built-in agent markdown for the given language.

    Reads from ``builtin/agents/{language}/*.md``.  Excludes
    ``README.md``.  Returns ``(actual_lang, filename, content_bytes,
    is_fallback)`` tuples.
    """
    return _iter_language_tree(BUILTIN_AGENTS_PACKAGE, language, _is_agent_md)


def _iter_language_tree(
    package: str,
    language: str,
    entry_filter: Callable[[Traversable], bool],
) -> list[tuple[str, str, bytes, bool]]:
    """Generic helper: enumerate a language subdirectory inside *package*.

    ``entry_filter(entry) -> True`` keeps the entry (and its subtree).
    """
    package_root: Traversable = resources.files(package)
    lang_dir = package_root.joinpath(language)

    try:
        list(lang_dir.iterdir())
        is_fallback = False
    except (FileNotFoundError, TypeError, OSError):
        logger.warning(
            "Built-in resources language %r not found in %s; falling back to 'en'",
            language,
            package,
        )
        lang_dir = package_root.joinpath("en")
        is_fallback = True

    out: list[tuple[str, str, bytes, bool]] = []
    actual_lang = language if not is_fallback else "en"

    for entry in lang_dir.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        if not entry_filter(entry):
            continue
        if entry.is_dir():
            _collect_files(entry, f"{entry.name}/", actual_lang, is_fallback, out)
        else:
            out.append((actual_lang, entry.name, entry.read_bytes(), is_fallback))

    out.sort(key=lambda t: t[1])
    return out


def _collect_files(
    directory: Traversable,
    prefix: str,
    actual_lang: str,
    is_fallback: bool,
    out: list[tuple[str, str, bytes, bool]],
) -> None:
    """Recursively collect all files under *directory* into *out*."""
    for entry in directory.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        if entry.is_dir():
            _collect_files(entry, f"{prefix}{entry.name}/", actual_lang, is_fallback, out)
        else:
            out.append((actual_lang, f"{prefix}{entry.name}", entry.read_bytes(), is_fallback))


def _collect_files_merged(
    directory: Traversable,
    prefix: str,
    actual_lang: str,
    is_fallback: bool,
    merged: dict[str, tuple[str, bytes, bool]],
) -> None:
    """Recursively collect files into *merged* dict keyed by relative path.

    Relative path is like ``"skill-name/SKILL.md"`` or
    ``"skill-name/references/foo.md"``.

    When *is_fallback* is ``True``, the entry is recorded only if the
    relative path has not already been set by a non-fallback pass (i.e.,
    language-specific files always win over fallback files).
    """
    for entry in directory.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        if entry.is_dir():
            _collect_files_merged(entry, f"{prefix}{entry.name}/", actual_lang, is_fallback, merged)
        else:
            rel_path = f"{prefix}{entry.name}"
            if is_fallback:
                # Language file wins: only insert if no language-specific entry exists yet.
                merged.setdefault(rel_path, (actual_lang, entry.read_bytes(), True))
            else:
                # Language file: always takes precedence.
                merged[rel_path] = (actual_lang, entry.read_bytes(), False)


def _is_skill_dir(entry: Traversable) -> bool:
    """Return True when *entry* looks like a skill directory."""
    if not entry.is_dir():
        return False
    return entry.joinpath("SKILL.md").is_file()


def _is_agent_md(entry: Traversable) -> bool:
    """Return True when *entry* is an agent markdown file."""
    if entry.name == "README.md":
        return False
    return entry.is_file() and entry.name.endswith(".md")


__all__ = [
    "BUILTIN_AGENTS_PACKAGE",
    "BUILTIN_SKILLS_PACKAGE",
    "MD_FILES_PACKAGE",
    "iter_builtin_agents",
    "iter_builtin_skills",
    "iter_md_template_files",
]
