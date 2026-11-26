"""Parser and path-safety unit tests for octop.infra.git.repo (no git needed)."""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.git.repo import (
    _normalize_repo_path,
    _parse_numstat,
    _parse_status_porcelain,
)


def test_parse_status_branch_headers() -> None:
    raw = (
        b"# branch.oid eb8152a057ce63cedf63112915c573355b9dcc4d\0"
        b"# branch.head main\0"
        b"# branch.upstream origin/main\0"
        b"# branch.ab +2 -3\0"
        b"1 .M N... 100644 100644 100644 abc def README.md\0"
    )
    info = _parse_status_porcelain(raw)
    assert info.branch == "main"
    assert info.head_short == "eb8152a0"
    assert info.upstream == "origin/main"
    assert (info.ahead, info.behind) == (2, 3)
    assert len(info.entries) == 1
    entry = info.entries[0]
    assert entry.xy == ".M"
    assert entry.path == "README.md"


def test_parse_status_detached_head() -> None:
    raw = b"# branch.head (detached)\0# branch.oid abcdef0123\0"
    info = _parse_status_porcelain(raw)
    assert info.branch is None
    assert info.head_short == "abcdef01"


def test_parse_status_rename_uses_next_token_as_orig() -> None:
    raw = b"2 R. N... 100 100 100 abc def R100 new/path.txt\0old/path.txt\0"
    info = _parse_status_porcelain(raw)
    assert len(info.entries) == 1
    entry = info.entries[0]
    assert entry.xy == "R."
    assert entry.path == "new/path.txt"
    assert entry.orig == "old/path.txt"


def test_parse_status_unmerged_and_untracked_and_ignored() -> None:
    raw = b"u AA N... 1 2 3 100 200 300 400 file with space.txt\0? untracked dir/\0! ignored.txt\0"
    info = _parse_status_porcelain(raw)
    assert len(info.entries) == 2
    unmerged = info.entries[0]
    assert unmerged.unmerged
    assert unmerged.path == "file with space.txt"
    untracked = info.entries[1]
    assert untracked.untracked
    assert untracked.path == "untracked dir/"


def test_parse_numstat_plain_and_binary() -> None:
    raw = b"5\t1\tREADME.md\0-\t-\timage.png\0"
    stats = _parse_numstat(raw)
    assert stats["README.md"] == (5, 1)
    assert stats["image.png"] == (None, None)


def test_parse_numstat_rename_two_token_shape() -> None:
    raw = b"3\t0\0old.txt\0new.txt\0"
    stats = _parse_numstat(raw)
    assert stats["new.txt"] == (3, 0)
    assert "old.txt" not in stats


def test_parse_numstat_rename_trailing_tab_shape() -> None:
    raw = b"3\t0\t\0old.txt\0new.txt\0"
    stats = _parse_numstat(raw)
    assert stats["new.txt"] == (3, 0)


@pytest.mark.parametrize(
    "raw",
    ["", "..", "a/../b", "\\..\\x", "."],
)
def test_normalize_repo_path_rejects_unsafe(raw: str) -> None:
    with pytest.raises(OctopError) as excinfo:
        _normalize_repo_path(raw)
    assert excinfo.value.code is ErrorCode.SLASH_BAD_ARGS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/src/a.ts", "src/a.ts"),
        ("src//a.ts", "src/a.ts"),
        ("./x.txt", "x.txt"),
        ("a\\b.txt", "a/b.txt"),
    ],
)
def test_normalize_repo_path_accepts_and_normalizes(raw: str, expected: str) -> None:
    assert _normalize_repo_path(raw) == expected
