"""Compose must forward OCTOP_DATABASE_* into the container (issue #152)."""

from __future__ import annotations

from pathlib import Path

from octop.config import _DATABASE_ENV_KEYS


def _compose_environment_entries(compose_text: str) -> str:
    """Return list-item lines under the octop service ``environment:`` key."""
    marker = "\n    environment:\n"
    env_idx = compose_text.index(marker) + len(marker)
    lines: list[str] = []
    for line in compose_text[env_idx:].splitlines():
        if line.startswith("      - "):
            lines.append(line)
            continue
        break
    return "\n".join(lines)


def test_docker_compose_forwards_database_env_keys() -> None:
    """docker/.env alone does not inject vars — they must be listed under environment."""
    repo = Path(__file__).resolve().parents[2]
    text = (repo / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    env_text = _compose_environment_entries(text)
    missing = [k for k in _DATABASE_ENV_KEYS if f"{k}=" not in env_text]
    assert not missing, f"docker-compose.yml environment missing: {missing}"
