"""Unit tests for the YuanBao bot creator state file."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from octop.infra.gateway.bot_creators import yuanbao_bot_creator as creator


@pytest.fixture()
def state_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "yuanbao-bot-creator-state.json"
    monkeypatch.setattr(creator, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(creator, "STATE_FILE", str(path))
    return path


def _staging_files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


def test_save_state_writes_the_created_bot(state_path: Path) -> None:
    creator._save_state({"phase": "done", "app_key": "key_1", "app_secret": "secret_1"})
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "phase": "done",
        "app_key": "key_1",
        "app_secret": "secret_1",
    }
    assert _staging_files(state_path.parent) == []


def test_failed_save_keeps_the_previous_state(
    state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creator._save_state({"phase": "poll", "scan_code": "code_1"})
    before = state_path.read_text(encoding="utf-8")

    unserializable: dict[str, Any] = {"phase": "done", "result": object()}
    with pytest.raises(TypeError):
        creator._save_state(unserializable)

    assert state_path.read_text(encoding="utf-8") == before
    assert json.loads(before)["scan_code"] == "code_1"
    assert _staging_files(state_path.parent) == []


def test_save_state_does_not_follow_a_planted_symlink(state_path: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("important data", encoding="utf-8")
    try:
        os.symlink(victim, state_path)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlink not available: {exc}")

    creator._save_state({"phase": "done", "app_key": "key_1"})

    assert victim.read_text(encoding="utf-8") == "important data"
    assert not state_path.is_symlink()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "phase": "done",
        "app_key": "key_1",
    }


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
def test_state_file_is_not_world_readable(state_path: Path) -> None:
    creator._save_state({"phase": "done", "app_key": "key_1", "app_secret": "secret_1"})
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
