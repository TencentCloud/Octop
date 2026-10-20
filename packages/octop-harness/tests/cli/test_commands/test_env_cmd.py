"""Tests for REPL /env command."""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path

from rich.console import Console

from octop_harness.cli.repl.commands import dispatch_command
from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.theme import get_theme


def _make_state() -> SessionState:
    return SessionState(
        session_id="test-session",
        model="test/model",
        agent_cfg={"providers": {}},
    )


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, highlight=False, markup=True)
    return console, buf


def test_env_set_writes_to_file_and_env(tmp_path: Path, monkeypatch: object) -> None:
    """/env set KEY val writes to ~/.octop-harness/.env and os.environ."""
    global_dir = tmp_path / "home" / ".octop-harness"
    global_dir.mkdir(parents=True)
    env_file = global_dir / ".env"

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.delenv("MY_KEY", raising=False)  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env set MY_KEY my_value", state, console, theme)

    assert os.environ.get("MY_KEY") == "my_value"
    assert env_file.exists()
    content = env_file.read_text()
    assert "MY_KEY" in content
    assert "my_value" in content
    assert "saved" in buf.getvalue().lower() or "MY_KEY" in buf.getvalue()


def test_env_get_existing_key(monkeypatch: object) -> None:
    """/env get KEY shows its value from os.environ."""
    monkeypatch.setenv("SHOW_KEY", "show_value")  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env get SHOW_KEY", state, console, theme)

    assert "show_value" in buf.getvalue()


def test_env_get_missing_key(monkeypatch: object) -> None:
    """/env get KEY when not set prints 'not set'."""
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env get MISSING_KEY_XYZ", state, console, theme)

    assert "not set" in buf.getvalue().lower()


def test_env_list_shows_file_contents(tmp_path: Path, monkeypatch: object) -> None:
    """/env list reads ~/.octop-harness/.env and shows keys."""
    global_dir = tmp_path / "home" / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / ".env").write_text("LIST_KEY_A=value_a\nLIST_KEY_B=sk-abcdef1234567890\n")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env list", state, console, theme)

    output = buf.getvalue()
    assert "LIST_KEY_A" in output
    assert "LIST_KEY_B" in output
    # value_a is short, should show in full
    assert "value_a" in output
    # sk-abcdef1234567890 is 20 chars with letters+digits — should be masked
    assert "••••" in output


def test_env_list_no_file(tmp_path: Path, monkeypatch: object) -> None:
    """/env list when no .env exists prints an informative message."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env list", state, console, theme)

    output = buf.getvalue().lower()
    assert "no" in output or "empty" in output or "not found" in output


def test_env_unset_removes_key(tmp_path: Path, monkeypatch: object) -> None:
    """/env unset KEY removes it from file and os.environ."""
    global_dir = tmp_path / "home" / ".octop-harness"
    global_dir.mkdir(parents=True)
    env_file = global_dir / ".env"
    env_file.write_text("DEL_KEY=to_be_deleted\n")

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))  # type: ignore[attr-defined]
    monkeypatch.setenv("DEL_KEY", "to_be_deleted")  # type: ignore[attr-defined]

    state = _make_state()
    console, _ = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env unset DEL_KEY", state, console, theme)

    assert os.environ.get("DEL_KEY") is None
    assert "DEL_KEY" not in env_file.read_text()


def test_env_reload(tmp_path: Path, monkeypatch: object) -> None:
    """/env reload calls load_dotenv_files with override=True."""
    from typing import Any

    calls: list[tuple[Any, ...]] = []

    def fake_load(project_dir: Path, *, override: bool = False) -> Path | None:
        calls.append((project_dir, override))
        return tmp_path / ".env"

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "octop_harness.cli.load_dotenv_files", fake_load
    )
    # Also patch Path.cwd() so we know what project_dir gets passed
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: tmp_path))  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env reload", state, console, theme)

    assert len(calls) == 1
    assert calls[0][1] is True  # override=True
    assert "reload" in buf.getvalue().lower()


def test_env_set_missing_args(monkeypatch: object) -> None:
    """/env set without KEY or value shows usage."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path("/tmp/fake_home_xyz")))  # type: ignore[attr-defined]

    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env set", state, console, theme)

    output = buf.getvalue().lower()
    assert "usage" in output or "key" in output


def test_env_unknown_subcmd() -> None:
    """/env unknown_subcmd shows usage."""
    state = _make_state()
    console, buf = _make_console()
    theme = get_theme("dark")

    dispatch_command("/env badcmd", state, console, theme)

    output = buf.getvalue().lower()
    assert "usage" in output
