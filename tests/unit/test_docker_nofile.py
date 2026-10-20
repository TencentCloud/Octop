"""Every shipped Compose entry point gives multi-agent servers enough fds."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    "relative_path",
    [
        "docker/docker-compose.yml",
        "docker/docker-compose.cn.yml",
        "docker/docker-compose.mobile.yml",
    ],
)
def test_octop_container_has_explicit_nofile_limit(relative_path):
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / relative_path).read_text(encoding="utf-8"))
    limit = compose["services"]["agentbuddy"]["ulimits"]["nofile"]
    assert limit["soft"] >= 65535
    assert limit["hard"] >= limit["soft"]
