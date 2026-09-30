"""Unit coverage for the host-path branch of ``normalize_workspace_root_dir()``.

``assert_safe_host_path()`` reports a rejected host path with a bare
``ValueError``. Every other call site of that helper maps it to an
``OctopError`` (``api/routers/filesystem.py`` and
``raise_if_backend_outside_user_root()`` in this module); the workspace-root
policy branch must do the same, or the request dies as HTTP 500.
"""

from __future__ import annotations

import os

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.resource_policy import normalize_workspace_root_dir

posix_only = pytest.mark.skipif(os.name != "posix", reason="denylist is POSIX-only by design")


def test_control_character_in_root_is_rejected_with_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    with pytest.raises(OctopError) as exc:
        normalize_workspace_root_dir("a\x00b")
    assert exc.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED
    assert exc.value.status == 400
    assert exc.value.message == "invalid path"


@posix_only
def test_denied_system_prefix_is_rejected_with_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    with pytest.raises(OctopError) as exc:
        normalize_workspace_root_dir("/etc")
    assert exc.value.code is ErrorCode.WORKSPACE_ROOT_RESTRICTED
    assert exc.value.status == 400
    assert exc.value.message == "path not allowed"


def test_valid_directory_still_normalizes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    root = tmp_path / "jail"
    root.mkdir()
    assert normalize_workspace_root_dir(str(root)) == root.resolve().as_posix()
