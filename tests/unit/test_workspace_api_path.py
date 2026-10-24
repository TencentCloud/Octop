"""workspace_api_path must reject traversal segments (2026-09-07 hardening)."""

from __future__ import annotations

import pytest

from octop.api.common.workspace import workspace_api_path
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.parametrize(
    "raw",
    [
        "..",
        "../etc/passwd",
        "/../etc/passwd",
        "foo/../../bar",
        "a/../b",
        r"..\windows\system32",
    ],
)
def test_workspace_api_path_rejects_traversal(raw: str) -> None:
    """`..` segments used to pass through to the backend as 500 noise."""
    with pytest.raises(OctopError) as excinfo:
        workspace_api_path(raw)
    assert excinfo.value.code is ErrorCode.FORBIDDEN


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "."),
        ("/", "."),
        ("/foo", "foo"),
        ("/foo/bar", "foo/bar"),
        ("foo/bar", "foo/bar"),
        # A dotfile is not a traversal segment.
        ("/foo/.hidden", "foo/.hidden"),
    ],
)
def test_workspace_api_path_maps_normal_paths(raw: str, expected: str) -> None:
    assert workspace_api_path(raw) == expected
