"""Bounded plugin archive preparation; no process registry changes here."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from octop_harness.plugins import PluginManifest

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT = 15
DOWNLOAD_BUDGET = 120


def download(url: str, archive: Path) -> None:
    deadline = time.monotonic() + DOWNLOAD_BUDGET
    with (
        urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response,  # noqa: S310
        archive.open("wb") as output,
    ):
        size = 0
        while chunk := response.read1(64 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("plugin archive exceeds 64 MiB")
            if time.monotonic() > deadline:
                raise TimeoutError("plugin download exceeded total time budget")
            output.write(chunk)


def install_dependencies(source: Path) -> None:
    manifest = PluginManifest.load(source / "plugin.yaml")
    commands: list[list[str]] = []
    requirements = source / "requirements.txt"
    if requirements.is_file():
        commands.append(["-r", str(requirements)])
    if manifest.requires:
        commands.append(list(manifest.requires))
    uv = shutil.which("uv")
    installer = (
        [uv, "pip", "install", "--python", sys.executable]
        if uv
        else [sys.executable, "-m", "pip", "install"]
    )
    for args in commands:
        subprocess.run(
            [*installer, *args],
            check=True,
            capture_output=True,
            timeout=120,
        )
