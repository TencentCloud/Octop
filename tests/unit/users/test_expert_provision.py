"""Expert push backend safety without requiring a Docker daemon."""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.expert_provision import _assert_safe_backend


def test_agent_scoped_docker_backend_is_safe_to_copy(tmp_path):
    backend = {
        "type": "docker",
        "image": "python:3.12",
        "sandbox_scope": "agent",
        "sandbox_prefix": "expert",
        "memory": "512m",
        "cpus": 1,
    }

    _assert_safe_backend(backend, backend, tmp_path / "source-workspace")


@pytest.mark.parametrize(
    "backend",
    [
        "docker",
        {"type": "composite", "default": {"type": "filesystem"}, "routes": {"/sandbox/": "docker"}},
    ],
)
def test_docker_without_top_level_agent_scope_is_rejected(tmp_path, backend):
    with pytest.raises(OctopError) as exc_info:
        _assert_safe_backend(backend, backend, tmp_path / "source-workspace")
    assert exc_info.value.code == ErrorCode.EXPERT_PUSH_UNSAFE
