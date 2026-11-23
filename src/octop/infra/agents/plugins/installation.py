"""Bounded plugin archive preparation; no process registry changes here."""

from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

from octop_harness.plugins import PluginManifest
from packaging.requirements import InvalidRequirement, Requirement

from octop.infra.utils.runtime_packages import install_packages

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT = 15
DOWNLOAD_BUDGET = 120
_COMMENT_RE = re.compile(r"(?:^|\s+)#.*$")


def download(url: str, archive: Path, *, max_bytes: int | None = None) -> None:
    deadline = time.monotonic() + DOWNLOAD_BUDGET
    limit = min(MAX_ARCHIVE_BYTES, max_bytes) if max_bytes is not None else MAX_ARCHIVE_BYTES
    with (
        urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response,  # noqa: S310
        archive.open("wb") as output,
    ):
        size = 0
        while chunk := response.read(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise ValueError(f"plugin download exceeds {limit} bytes")
            if time.monotonic() > deadline:
                raise TimeoutError("plugin download exceeded total time budget")
            output.write(chunk)


def _validate_requirement(raw: str) -> str:
    spec = raw.strip()
    if not spec or spec.startswith("-"):
        raise ValueError(f"invalid plugin requirement: {raw!r}")
    try:
        Requirement(spec)
    except InvalidRequirement as exc:
        raise ValueError(f"invalid plugin requirement: {raw!r}") from exc
    return spec


def _parse_requirements_file(path: Path) -> list[str]:
    specs: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        cleaned = _COMMENT_RE.sub("", raw_line).strip()
        if not cleaned:
            continue
        specs.append(_validate_requirement(cleaned))
    return specs


def install_dependencies(source: Path) -> None:
    manifest = PluginManifest.load(source / "plugin.yaml")
    specs: list[str] = []
    requirements = source / "requirements.txt"
    if requirements.is_file():
        specs.extend(_parse_requirements_file(requirements))
    if manifest.requires:
        for requirement in manifest.requires:
            specs.append(_validate_requirement(requirement))
    if not specs:
        return
    install_packages(specs, timeout=120)
