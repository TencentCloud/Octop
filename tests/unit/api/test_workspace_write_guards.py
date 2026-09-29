"""Unit guards for workspace write endpoints: team memory (409) + builtin skills (403).

``B-19-A``: the new ``_assert_team_memory_writable`` guard rejects ``.octop/team/**``
writes with ``TEAM_ARTIFACT_OWNERSHIP_DENIED`` (HTTP 409), while the pre-existing
``_assert_workspace_mutable`` keeps its ``FORBIDDEN`` (403) semantics for
``_builtin_skills`` -- now with the ``SEC-10`` bypasses (``./`` / ``x/../`` / ``//``)
closed, because both guards judge the **normalized** path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.api.routers.workspace import (
    _assert_team_memory_writable,
    _assert_workspace_mutable,
    _normalize_rel_posix,
)
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SOUL.md", "SOUL.md"),
        ("/outbound/a.txt", "outbound/a.txt"),
        ("//.octop//team///LEARNINGS.md", ".octop/team/LEARNINGS.md"),
        ("/./.octop/team/LEARNINGS.md", ".octop/team/LEARNINGS.md"),
        ("x/../.octop/team/LEARNINGS.md", ".octop/team/LEARNINGS.md"),
        (".octop\\team\\LEARNINGS.md", ".octop/team/LEARNINGS.md"),
        ("..\\.octop\\team\\LEARNINGS.md", ".octop/team/LEARNINGS.md"),
        ("/", ""),
        ("./", ""),
        ("x/..", ""),
        (".octop/team/../../SOUL.md", "SOUL.md"),
    ],
)
def test_normalize_rel_posix_folds_all_spellings(raw: str, expected: str) -> None:
    assert _normalize_rel_posix(raw) == expected


def test_both_guards_share_one_normalizer() -> None:
    """Single source: both guards must resolve ``_normalize_rel_posix`` from the module."""
    for guard in (_assert_team_memory_writable, _assert_workspace_mutable):
        assert guard.__globals__["_normalize_rel_posix"] is _normalize_rel_posix


@pytest.mark.parametrize(
    "path",
    [
        ".octop/team/LEARNINGS.md",
        ".octop/team/projects/P1/LEARNINGS.md",
        "/.octop/team/LEARNINGS.md",
        ".octop/team",
    ],
)
def test_team_memory_paths_denied_409(path: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        _assert_team_memory_writable(path)
    assert excinfo.value.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert excinfo.value.status == 409


@pytest.mark.parametrize(
    "path",
    [
        "/./.octop/team/LEARNINGS.md",  # ./ bypass
        "/x/../.octop/team/LEARNINGS.md",  # x/../ bypass
        "//.octop/team/LEARNINGS.md",  # // bypass
        "/x/../.octop/team/projects/P1/LEARNINGS.md",
        ".octop\\team\\LEARNINGS.md",  # Windows form
        "..\\.octop\\team\\LEARNINGS.md",  # Windows form, leading ..
    ],
)
def test_team_memory_bypass_spellings_denied_409(path: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        _assert_team_memory_writable(path)
    assert excinfo.value.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert excinfo.value.status == 409


@pytest.mark.parametrize(
    ("path", "expected_io"),
    [
        ("SOUL.md", "SOUL.md"),
        ("outbound/a.txt", "outbound/a.txt"),
        # normalizes out of the protected surface; the target itself stays verbatim
        (".octop/team/../../SOUL.md", ".octop/team/../../SOUL.md"),
        (".octop/sessions/state.db", ".octop/sessions/state.db"),
        ("skills/demo/SKILL.md", "skills/demo/SKILL.md"),
    ],
)
def test_ordinary_paths_pass_team_guard(path: str, expected_io: str) -> None:
    """Positive control: allowed paths pass **and** yield the verbatim effective target."""
    assert _assert_team_memory_writable(path) == expected_io


@pytest.mark.parametrize("from_workspace", [False, True])
@pytest.mark.parametrize("shape", ["relative", "host_absolute", "file_url"])
def test_team_memory_effective_target_denied_409(
    tmp_path: Path, shape: str, from_workspace: bool
) -> None:
    """The guard judges the resolved I/O target, so all three spellings are one surface.

    ``host_absolute`` is the default-parameter hole (``from_workspace=false`` sends a
    leading ``/`` to the host filesystem); ``file_url`` always resolves host-absolute.
    """
    target = tmp_path / ".octop" / "team" / "LEARNINGS.md"
    path = {
        "relative": ".octop/team/LEARNINGS.md",
        "host_absolute": target.as_posix(),
        "file_url": target.as_uri(),
    }[shape]
    with pytest.raises(OctopError) as excinfo:
        _assert_team_memory_writable(path, from_workspace=from_workspace)
    assert excinfo.value.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert excinfo.value.status == 409


@pytest.mark.parametrize("from_workspace", [False, True])
@pytest.mark.parametrize("sys_rel", [".octop/sessions/state.db", ".octop/auth/token.json"])
def test_system_paths_outside_team_are_not_collateral(
    tmp_path: Path, sys_rel: str, from_workspace: bool
) -> None:
    """``.octop/**`` siblings that are not ``.octop/team`` must keep passing, all shapes."""
    host = (tmp_path / sys_rel).as_posix()
    assert _assert_team_memory_writable(sys_rel, from_workspace=from_workspace) == sys_rel
    # ``from_workspace=true`` re-anchors leading ``/`` inside the workspace, so compare
    # the folded components: both modes must keep the same segments (never ``.octop/team``).
    assert _normalize_rel_posix(
        _assert_team_memory_writable(host, from_workspace=from_workspace)
    ) == _normalize_rel_posix(host)
    # ``file://`` resolves host-absolute; compare after folding (Windows ``\`` vs ``/``).
    from_url = _assert_team_memory_writable(
        (tmp_path / sys_rel).as_uri(), from_workspace=from_workspace
    )
    assert _normalize_rel_posix(from_url) == _normalize_rel_posix(host)


@pytest.mark.parametrize(
    "path",
    [
        "_builtin_skills/foo/SKILL.md",  # direct
        ".octop/_builtin_skills/foo/SKILL.md",  # direct
        "/./_builtin_skills/foo/SKILL.md",  # ./ bypass (SEC-10)
        "/x/../_builtin_skills/foo/SKILL.md",  # x/../ bypass (SEC-10)
        "//.octop/_builtin_skills/foo/SKILL.md",  # // bypass (SEC-10)
        ".octop\\_builtin_skills\\foo\\SKILL.md",  # Windows form
    ],
)
def test_builtin_skills_still_forbidden_403(path: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        _assert_workspace_mutable(path)
    assert excinfo.value.code is ErrorCode.FORBIDDEN
    assert excinfo.value.status == 403


def test_workspace_mutable_returns_normalized_rel_and_allows_ordinary_paths() -> None:
    assert _assert_workspace_mutable("SOUL.md") == "SOUL.md"
    assert _assert_workspace_mutable("/outbound/a.txt") == "outbound/a.txt"
    assert _assert_workspace_mutable(".octop/team/LEARNINGS.md") == ".octop/team/LEARNINGS.md"
