"""T97-2 unit matrix: the ``_builtin_skills`` write guard on its single entry point.

Contract: ``PLAN.md`` §2.2/§2.4 + §7.2 · ``SPEC.md`` A1-A3/A13 · ``TASKS.json`` ``T97-2``
(``FIND-3``). The guard judges the **effective backend target** (``_workspace_io_path``)
with an ASCII-folded segment scan and **exactly two** shapes -- first segment
``_builtin_skills``, or the adjacent segment pair ``(".octop", "_builtin_skills")``. So the
relative / host-absolute / ``file://`` spellings collapse onto one surface while the
mid-path sibling ``notes/_builtin_skills/x.md`` must keep passing (FIND-3).

Every case drives ``_assert_workspace_write_allowed(path, *, from_workspace, workspace_dir)``
with ``workspace_dir=tmp_path``, i.e. the same shape as the real call site
(``ws.workspace_dir``). Observations are **local-only**: pure function, no HTTP, no I/O,
no network, no database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.api.routers.workspace import (
    _assert_workspace_write_allowed,
    _builtin_skills_hit,
    _workspace_io_path,
)
from octop.infra.errors import ErrorCode, OctopError


def _deny(
    path: str, *, from_workspace: bool = False, workspace_dir: str | Path | None = None
) -> OctopError:
    """Drive the single entry point and return the ``OctopError`` it must raise."""
    with pytest.raises(OctopError) as excinfo:
        _assert_workspace_write_allowed(
            path, from_workspace=from_workspace, workspace_dir=workspace_dir
        )
    return excinfo.value


def _deny_403(path: str, *, from_workspace: bool = False, workspace_dir: Path) -> OctopError:
    error = _deny(path, from_workspace=from_workspace, workspace_dir=workspace_dir)
    assert error.code is ErrorCode.FORBIDDEN
    assert error.status == 403
    assert "_builtin_skills" in error.message
    return error


# --------------------------------------------------------------------------- cell 1
@pytest.mark.parametrize(
    ("shape", "template"),
    [
        ("relative", "_builtin_skills/x"),
        ("host_absolute", "{ws}/_builtin_skills/x"),
        ("file_url", "{ws_uri}/_builtin_skills/x"),
    ],
)
def test_cell1_three_spellings_default_from_workspace_403(
    tmp_path: Path, shape: str, template: str
) -> None:
    """★ Cell 1: three spellings x default ``from_workspace=False`` ⇒ 403 ``FORBIDDEN``."""
    path = template.format(ws=tmp_path.as_posix(), ws_uri=tmp_path.as_uri())
    _deny_403(path, from_workspace=False, workspace_dir=tmp_path)


# --------------------------------------------------------------------------- cell 2
@pytest.mark.parametrize(
    "path",
    [
        "_BUILTIN_SKILLS/x",
        "_Builtin_Skills/x",
        ".OCTOP/_BUILTIN_SKILLS/x",
    ],
)
def test_cell2_ascii_case_folding_403(tmp_path: Path, path: str) -> None:
    """★ Cell 2: ASCII case folding is a tightening, not a bypass ⇒ 403 ``FORBIDDEN``."""
    _deny_403(path, from_workspace=False, workspace_dir=tmp_path)


# --------------------------------------------------------------------------- cell 3
@pytest.mark.parametrize(
    "path",
    [
        "./_builtin_skills/x",
        "x/../_builtin_skills/x",
        "//_builtin_skills/x",
        "..\\_builtin_skills\\x",
    ],
)
def test_cell3_bypass_spellings_403(tmp_path: Path, path: str) -> None:
    """★ Cell 3: ``./`` / ``x/../`` / ``//`` / Windows ``\\`` folds ⇒ 403 ``FORBIDDEN``."""
    _deny_403(path, from_workspace=False, workspace_dir=tmp_path)


# ----------------------------------------------------------------- cells 4 + 6
@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("notes/_builtin_skills/x.md", "notes/_builtin_skills/x.md"),
        ("{ws}/notes/_builtin_skills/x.md", "{ws}/notes/_builtin_skills/x.md"),
        (".octop/sessions/x.json", ".octop/sessions/x.json"),
        (".octop/auth/token.json", ".octop/auth/token.json"),
        ("SOUL.md", "SOUL.md"),
    ],
)
def test_cell4_positive_controls_pass_with_usable_target(
    tmp_path: Path, template: str, expected: str
) -> None:
    """★★ Cell 4 + cell 6: mid-path ``_builtin_skills`` siblings are **not** collateral.

    ``FIND-3`` core: a coarse "any segment equals ``_builtin_skills``" criterion would turn
    ``notes/_builtin_skills/x.md`` into 403. The guard must keep passing it, and cell 6
    requires the return value to be the **verbatim effective target** the caller writes to
    (relative stays relative, host-absolute stays host-absolute) -- reusable downstream.
    """
    ws = tmp_path.as_posix()
    path = template.format(ws=ws)
    returned = _assert_workspace_write_allowed(path, from_workspace=False, workspace_dir=tmp_path)
    assert returned == expected.format(ws=ws)
    assert _workspace_io_path(returned, from_workspace=False) == returned


def test_cell6_from_workspace_true_returns_workspace_relative_target(tmp_path: Path) -> None:
    """★ Cell 6: the workspace-UI spelling (``from_workspace=True``) returns a relative target."""
    returned = _assert_workspace_write_allowed(
        "/notes/_builtin_skills/x.md", from_workspace=True, workspace_dir=tmp_path
    )
    assert returned == "notes/_builtin_skills/x.md"
    assert _workspace_io_path(returned, from_workspace=True) == returned


# --------------------------------------------------------------------------- cell 5
@pytest.mark.parametrize("path", [".", "", "./"])
def test_cell5_workspace_root_403_with_root_copy(tmp_path: Path, path: str) -> None:
    """★ Cell 5: root spellings ⇒ 403 ``FORBIDDEN`` and the frozen root copy."""
    error = _deny(path, from_workspace=False, workspace_dir=tmp_path)
    assert error.code is ErrorCode.FORBIDDEN
    assert error.status == 403
    assert error.message == "cannot modify workspace root"


# --------------------------------------------------------------------------- cell 7
def test_cell7_team_surface_and_builtin_surface_keep_their_own_codes(tmp_path: Path) -> None:
    """★ Cell 7: ``.octop/team`` ⇒ 409, ``_builtin_skills`` ⇒ 403, judged independently."""
    team = _deny(".octop/team/LEARNINGS.md", workspace_dir=tmp_path)
    assert team.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert team.status == 409

    builtin = _deny(".octop/_builtin_skills/x", workspace_dir=tmp_path)
    assert builtin.code is ErrorCode.FORBIDDEN
    assert builtin.status == 403

    # Frozen order (PLAN §2.3): root ⇒ team ⇒ builtin, so the pair wins when both hit.
    both = _deny(".octop/team/_builtin_skills/x", workspace_dir=tmp_path)
    assert both.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert both.status == 409


# ------------------------------------------------------- predicate, exactly two shapes
@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        (["_builtin_skills", "x"], True),  # shape (1): first segment
        (["_builtin_skills"], True),
        ([".octop", "_builtin_skills", "x"], True),  # shape (2): adjacent pair
        (["notes", ".octop", "_builtin_skills", "x"], True),
        (["notes", "_builtin_skills", "x.md"], False),  # FIND-3: mid-path is not protected
        (["notes", "_builtin_skills"], False),
        (["x", "_builtin_skills", "y"], False),
        (["_octop", "_builtin_skills", "x"], False),  # pair prefix must be exactly ".octop"
        ([], False),
    ],
)
def test_builtin_skills_hit_is_exactly_two_shapes(segments: list[str], expected: bool) -> None:
    """The criterion itself: two shapes only -- never "any segment equals" (would be 403)."""
    assert _builtin_skills_hit(segments) is expected
