"""``_assert_workspace_mutable`` — the guard every mutating workspace route runs.

Both invariants are checked on the *folded* fragment, because that is what the
backend opens: ``/keep/..`` addresses the workspace root and
``/sub/../_builtin_skills/x`` addresses the Octop-owned skill root (#1126).
"""

from __future__ import annotations

import pytest

from octop.api.routers.workspace import _assert_workspace_mutable
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.parametrize(
    "path",
    ["/", "/.", "/keep/..", "keep/../", "/a/b/../..", "\\"],
)
def test_workspace_root_is_read_only_in_every_spelling(path: str) -> None:
    with pytest.raises(OctopError) as ei:
        _assert_workspace_mutable(path)
    assert ei.value.code is ErrorCode.FORBIDDEN
    assert "workspace root" in ei.value.message


@pytest.mark.parametrize(
    "path",
    [
        "/_builtin_skills/foo/SKILL.md",
        "/sub/../_builtin_skills/foo/SKILL.md",
        "/.octop/sub/../_builtin_skills/foo/SKILL.md",
        "docs\\..\\_builtin_skills\\foo\\SKILL.md",
    ],
)
def test_dotdot_cannot_fold_back_into_builtin_skills(path: str) -> None:
    with pytest.raises(OctopError) as ei:
        _assert_workspace_mutable(path)
    assert ei.value.code is ErrorCode.FORBIDDEN
    assert "_builtin_skills" in ei.value.message


@pytest.mark.parametrize(
    ("path", "rel"),
    [
        ("sub/notes.md", "sub/notes.md"),
        ("/logo.png", "logo.png"),
        ("docs/../skills/x.md", "docs/../skills/x.md"),
        # folds back out of the protected root, so it is an ordinary write
        ("a/_builtin_skills/../../b.md", "a/_builtin_skills/../../b.md"),
        ("_builtin_skills_notes.md", "_builtin_skills_notes.md"),
    ],
)
def test_user_writes_are_untouched(path: str, rel: str) -> None:
    """The guard rejects by folded path but hands the backend the original fragment."""
    assert _assert_workspace_mutable(path) == rel
