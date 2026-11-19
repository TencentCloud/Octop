"""Tests for per-turn file checkpoint storage / diff / rewind classification."""

from __future__ import annotations

from pathlib import Path

from octop.infra.agents.file_checkpoints import (
    apply_rewind,
    classify_rewind,
    load_checkpoints,
    save_checkpoints,
    turn_diff,
)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    changes = [{"path": "a.md", "before": "old", "after": "new"}]
    save_checkpoints(tmp_path, "ag", "th", "msg", changes)
    assert load_checkpoints(tmp_path, "ag", "th", "msg") == changes
    assert load_checkpoints(tmp_path, "ag", "th", "missing") == []


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


class _WS:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def exists(self, p: str) -> bool:
        return p in self.files

    def read_text(self, p: str) -> str | None:
        return self.files.get(p)

    def write_text(self, p: str, c: str, *, force: bool = False) -> None:
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
