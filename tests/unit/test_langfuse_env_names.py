"""Every Langfuse variable shipped to the container must have a reader.

`.env.example` and `docker/docker-compose.yml` advertise the observability
knobs to self-hosters. Octop itself keeps the enable switch in the settings
table (`observability_langfuse_enabled`), while the credentials fall back to
the Langfuse SDK's own environment variables — so a name neither side reads
is a knob that silently does nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE = REPO_ROOT / "docker" / "docker-compose.yml"


def _shipped_langfuse_names() -> set[str]:
    """Variable names actually set by the shipped config, prose comments excluded."""
    names: set[str] = set()
    for path in (ENV_EXAMPLE, COMPOSE):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            names.update(re.findall(r"\b(LANGFUSE_[A-Z0-9_]+|OCTOP_LANGFUSE_[A-Z0-9_]+)\b", line))
    return names


def _names_read_by_octop() -> set[str]:
    names: set[str] = set()
    for path in (REPO_ROOT / "src/octop").rglob("*.py"):
        names.update(
            re.findall(
                r"\b(?:getenv|environ\.get|environ\[)\(?\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']",
                path.read_text(encoding="utf-8", errors="ignore"),
            )
        )
    return names


def _sdk_env_names() -> set[str]:
    module = pytest.importorskip("langfuse._client.environment_variables")
    return {v for k, v in vars(module).items() if k.startswith("LANGFUSE_") and isinstance(v, str)}


def test_octop_reads_no_langfuse_env_var() -> None:
    """Guard the premise: Octop's switch lives in the settings table, not env."""
    source = (REPO_ROOT / "src/octop/infra/agents/settings/langfuse.py").read_text(encoding="utf-8")
    assert '"observability_langfuse_enabled"' in source
    assert not re.search(r"(?:getenv|environ(?:\.get)?)\(\s*[\"']OCTOP_LANGFUSE", source)


def test_shipped_langfuse_names_have_a_reader() -> None:
    shipped = _shipped_langfuse_names()
    assert shipped, "no Langfuse variables found in the shipped config"
    unread = sorted(n for n in shipped if n not in _sdk_env_names() | _names_read_by_octop())
    assert not unread, f"{unread} is passed to the container but no code reads it"
