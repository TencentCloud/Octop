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
        assert {"browser", "local-embedding", "knowledge-ocr"} <= extras
        assert "--frozen" in command
        assert "--no-dev" in command
