"""Both Docker sync layers must retain local knowledge dependencies."""

from __future__ import annotations

import shlex
from pathlib import Path


def test_docker_syncs_retain_knowledge_extras() -> None:
    """A later exact uv sync must not prune extras installed in an earlier layer."""
    repo = Path(__file__).resolve().parents[2]
    dockerfile = (repo / "docker" / "Dockerfile").read_text(encoding="utf-8")
    commands = dockerfile.replace("\\\n", " ").splitlines()
    syncs = [shlex.split(line.strip()) for line in commands if "uv sync " in line]
    assert len(syncs) == 2
    for command in syncs:
        extras = {
            command[index + 1]
            for index, argument in enumerate(command[:-1])
            if argument == "--extra"
        }
        assert {"browser", "desktop", "local-embedding", "knowledge-ocr"} <= extras
        assert "--frozen" in command
        assert "--no-dev" in command


def test_fnos_source_dockerfile_installs_knowledge_extras() -> None:
    """The manual FnOS source image must bake the same knowledge runtimes.

    Published FnOS Docker packages pull the image built from docker/Dockerfile
    and do not build this file.
    """
    repo = Path(__file__).resolve().parents[2]
    dockerfile = (repo / "fnos" / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert ".[desktop,local-embedding,knowledge-ocr]" in dockerfile
    assert (
        "import cv2, fastembed, huggingface_hub, mss, pynput, rapidocr, onnxruntime, pymupdf"
        in dockerfile
    )
    assert "bake-desktop.sh" in dockerfile


def test_images_bake_desktop_without_starting_or_downloading_laya() -> None:
    """Both images install the desktop stack and leave Xvnc stopped."""
    repo = Path(__file__).resolve().parents[2]
    bake = (repo / "docker" / "bake-desktop.sh").read_text(encoding="utf-8")
    install = (repo / "src/octop/infra/control/desktop/scripts/linux/v1.0/install.sh").read_text(
        encoding="utf-8"
    )
    assert "--no-start" in bake
    assert "playwright install" not in bake
    assert '"laya": false' in bake
    assert "browser_flag" in bake
    assert "firefox-esr" in bake
    assert "chromium-browser" in install
    assert 'if [ "$NO_START" = 1 ]' in install
    for rel in ("docker/Dockerfile", "fnos/docker/Dockerfile"):
        text = (repo / rel).read_text(encoding="utf-8")
        assert "bake-desktop.sh" in text
        assert "playwright install" not in text
