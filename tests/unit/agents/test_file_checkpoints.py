"""Tests for per-turn file checkpoint storage / diff / rewind classification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.agents.file_checkpoints import (
    apply_rewind,
    classify_rewind,
    line_change_stat,
    load_checkpoints,
    load_turn_state,
    mark_turn_reverted,
    save_checkpoints,
    turn_diff,
    turn_summary,
)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    changes = [{"path": "a.md", "before": "old", "after": "new"}]
    save_checkpoints(tmp_path, "ag", "th", "msg", changes)
    assert load_checkpoints(tmp_path, "ag", "th", "msg") == changes
    assert load_checkpoints(tmp_path, "ag", "th", "missing") == []


def test_load_accepts_legacy_bare_list(tmp_path: Path) -> None:
    path = tmp_path / "file_checkpoints" / "ag" / "th" / "msg.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"path": "a.md", "before": None, "after": "x"}]))
    assert load_turn_state(tmp_path, "ag", "th", "msg") == {
        "reverted": False,
        "changes": [{"path": "a.md", "before": None, "after": "x"}],
    }


def test_revert_marker_roundtrip(tmp_path: Path) -> None:
    changes = [{"path": "a.md", "before": "old", "after": "new"}]
    save_checkpoints(tmp_path, "ag", "th", "msg", changes)
    assert load_turn_state(tmp_path, "ag", "th", "msg")["reverted"] is False
    mark_turn_reverted(tmp_path, "ag", "th", "msg")
    state = load_turn_state(tmp_path, "ag", "th", "msg")
    assert state["reverted"] is True
    assert state["changes"] == changes
    assert load_checkpoints(tmp_path, "ag", "th", "msg") == changes


def test_save_checkpoints_skips_empty(tmp_path: Path) -> None:
    save_checkpoints(tmp_path, "ag", "th", "msg", [])
    assert load_turn_state(tmp_path, "ag", "th", "msg") == {"reverted": False, "changes": []}


def test_line_change_stat_counts_real_changed_lines() -> None:
    before = "a\nb\nc\n"
    after = "a\nX\nc\n"
    assert line_change_stat(before, after) == (1, 1)
    # Trailing newline is not a line; identical content is a no-op.
    assert line_change_stat("same\n", "same") == (0, 0)
    assert line_change_stat(None, "x\ny\n") == (2, 0)
    assert line_change_stat("x\ny\n", None) == (0, 2)
    # Shared middle content is not double counted.
    assert line_change_stat("b\n", "b") == (0, 0)


def test_line_change_stat_falls_back_on_huge_files() -> None:
    big = "\n".join(str(i) for i in range(700)) + "\n"
    shifted = "\n".join(f"{i}!" for i in range(700)) + "\n"
    # 700x700 cells would fit; use two 700-line blocks => 490_000 > 400_000.
    assert line_change_stat(big, shifted) == (700, 700)


def test_turn_summary_sorts_and_aggregates() -> None:
    changes = [
        {"path": "b.md", "before": "1\n2\n", "after": "1\n2\n3\n", "write_count": 2},
        {"path": "a.md", "before": None, "after": "x\n", "tool_names": ["write_file"]},
        {"path": "gone.md", "before": "p\nq\n", "after": None},
    ]
    summary = turn_summary(changes)
    assert [f["path"] for f in summary["files"]] == ["a.md", "b.md", "gone.md"]
    assert summary["additions"] == 1 + 1 + 0
    assert summary["deletions"] == 0 + 0 + 2
    assert summary["files"][0]["tool_names"] == ["write_file"]
    assert summary["files"][1]["write_count"] == 2


class _WS:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.fail_read = False
        self.fail_write_paths: set[str] = set()

    def exists(self, p: str) -> bool:
        return p in self.files

    def read_text(self, p: str) -> str | None:
        if self.fail_read:
            raise OSError("read failed")
        return self.files.get(p)

    def write_text(self, p: str, c: str, *, force: bool = False) -> None:
        if p in self.fail_write_paths:
            raise OSError("write failed")
        self.files[p] = c

    def delete(self, p: str) -> None:
        self.files.pop(p, None)


def test_apply_rewind_restores_and_deletes() -> None:
    ws = _WS()
    ws.files["edit.md"] = "new"
    ws.files["created.md"] = "x"
    safe = [
        {"path": "edit.md", "before": "old", "after": "new"},
        {"path": "created.md", "before": None, "after": "x"},
    ]
    applied = apply_rewind(ws, safe)
    assert set(applied) == {"edit.md", "created.md"}
    assert ws.files["edit.md"] == "old"
    assert "created.md" not in ws.files


def test_apply_rewind_compensates_on_failure() -> None:
    ws = _WS()
    ws.files["first.md"] = "new1"
    ws.files["second.md"] = "new2"
    safe = [
        {"path": "first.md", "before": "old1", "after": "new1"},
        {"path": "second.md", "before": "old2", "after": "new2"},
    ]
    ws.fail_write_paths = {"second.md"}
    with pytest.raises(Exception, match="second.md"):
        apply_rewind(ws, safe)
    # The first file was restored before the failure; compensation must
    # return it to its pre-rewind content instead of leaving a half rewind.
    assert ws.files["first.md"] == "new1"
    assert ws.files["second.md"] == "new2"


def test_apply_rewind_aborts_when_prior_state_unreadable() -> None:
    ws = _WS()
    ws.files["a.md"] = "new"
    ws.fail_read = True
    safe = [{"path": "a.md", "before": "old", "after": "new"}]
    with pytest.raises(Exception, match="a.md"):
        apply_rewind(ws, safe)
    assert ws.files["a.md"] == "new"


def test_turn_diff_created_and_modified() -> None:
    created = turn_diff(None, "x\n", "n.md")
    assert "+x" in created
    modified = turn_diff("a\n", "a\nb\n", "m.md")
    assert "+b" in modified
    assert "-a" not in modified


def test_classify_rewind_safe_unsafe_ignored() -> None:
    changes = [
        {"path": "safe.md", "before": "o", "after": "n"},
        {"path": "unsafe.md", "before": "o", "after": "n"},
        {"path": "same.md", "before": "s", "after": "s"},
    ]
    current = {"safe.md": "n", "unsafe.md": "external", "same.md": "s"}
    groups = classify_rewind(changes, current)
    assert [g["path"] for g in groups["safe"]] == ["safe.md"]
    assert [g["path"] for g in groups["unsafe"]] == ["unsafe.md"]
    assert groups["unsafe"][0]["reason"] == "external_modified"
    assert [g["path"] for g in groups["ignored"]] == ["same.md"]
