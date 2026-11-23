"""Resolve the host git binary across self-hosted platform layouts.

A server process started by launchd/systemd/a Windows service often has a
minimal PATH, so ``shutil.which("git")`` alone misses Homebrew, Git for
Windows or NixOS installs. Resolution order:

1. explicit ``git_binary`` (config.json) / ``OCTOP_GIT_BINARY``
2. the process PATH
3. well-known platform locations

Every candidate is validated by running ``git --version`` and must be at least
``MIN_GIT_VERSION`` (``git restore`` is used by unstage/discard).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

MIN_GIT_VERSION = (2, 23, 0)
_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True)
class GitBinary:
    path: str
    version: tuple[int, int, int]
    source: str  # env | config | path | fallback

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)


def _probe(path: str) -> tuple[int, int, int] | None:
    if not path or not os.path.isfile(path) or not os.access(path, os.X_OK):
        return None
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = _VERSION_RE.search(result.stdout or "")
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def _platform_candidates() -> list[str]:
    if sys.platform == "darwin":
        return [
            "/opt/homebrew/bin/git",
            "/usr/local/bin/git",
            "/opt/local/bin/git",
            "/usr/bin/git",
        ]
    if sys.platform == "win32":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        paths: list[str] = []
        for root in roots:
            if root:
                paths.append(os.path.join(root, "Git", "cmd", "git.exe"))
                paths.append(os.path.join(root, "Git", "bin", "git.exe"))
                paths.append(os.path.join(root, "Programs", "Git", "cmd", "git.exe"))
        user = os.environ.get("USERPROFILE")
        if user:
            paths.append(os.path.join(user, "scoop", "shims", "git.exe"))
        paths.append(os.path.join("C:\\", "ProgramData", "chocolatey", "bin", "git.exe"))
        return paths
    return [
        "/usr/bin/git",
        "/usr/local/bin/git",
        "/snap/bin/git",
        "/home/linuxbrew/.linuxbrew/bin/git",
        "/nix/var/nix/profiles/default/bin/git",
    ]


_cache: dict[str, GitBinary | None] = {}


def resolve_git_binary(preferred: str | None = None) -> GitBinary | None:
    """Return the first usable git without mutating PATH."""
    configured = (preferred or "").strip()
    key = configured
    if key in _cache:
        return _cache[key]

    ordered: list[tuple[str, str]] = []
    if configured:
        ordered.append(("config", configured))
    env_bin = (os.environ.get("OCTOP_GIT_BINARY") or "").strip()
    if env_bin and env_bin != configured:
        ordered.append(("env", env_bin))

    found = shutil.which("git")
    if found:
        ordered.append(("path", found))

    ordered.extend(("fallback", path) for path in _platform_candidates())

    seen: set[str] = set()
    for source, path in ordered:
        if path in seen:
            continue
        seen.add(path)
        version = _probe(path)
        if version is None or version < MIN_GIT_VERSION:
            continue
        resolved = GitBinary(path=path, version=version, source=source)
        _cache[key] = resolved
        return resolved

    _cache[key] = None
    return None


def clear_git_binary_cache() -> None:
    _cache.clear()


__all__ = [
    "GitBinary",
    "MIN_GIT_VERSION",
    "clear_git_binary_cache",
    "resolve_git_binary",
]
