"""Unit tests for ui/completer.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from prompt_toolkit.document import Document

from octop_harness.cli.ui.completer import (
    FileRefCompleter,
    MergedCompleter,
    SlashCompleter,
    _basename,
    _file_type_hint,
)


class TestSlashCompleter:
    def test_help_completion(self):
        completer = SlashCompleter()
        doc = Document("/he", cursor_position=3)
        results = list(completer.get_completions(doc, None))
        assert any(r.text == "/help" for r in results)

    def test_no_completion_without_slash(self):
        completer = SlashCompleter()
        doc = Document("hello", cursor_position=5)
        results = list(completer.get_completions(doc, None))
        assert len(results) == 0

    def test_exit_variants(self):
        completer = SlashCompleter()
        doc = Document("/ex", cursor_position=3)
        results = list(completer.get_completions(doc, None))
        assert any(r.text == "/exit" for r in results)


class TestFileRefCompleter:
    def test_basic_completion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            (cwd / "main.py").write_text("x")
            (cwd / "test.py").write_text("y")

            completer = FileRefCompleter(cwd)
            doc = Document("look at @mai", cursor_position=12)
            results = list(completer.get_completions(doc, None))
            assert any("main.py" in r.text for r in results)

    def test_no_completion_without_at(self):
        completer = FileRefCompleter(Path("."))
        doc = Document("hello world", cursor_position=11)
        results = list(completer.get_completions(doc, None))
        assert len(results) == 0

    def test_at_must_follow_space(self):
        """@ in middle of word should not trigger."""
        completer = FileRefCompleter(Path("."))
        doc = Document("email@gmai", cursor_position=10)
        results = list(completer.get_completions(doc, None))
        assert len(results) == 0


class TestMergedCompleter:
    def test_slash_mode(self):
        completer = MergedCompleter(Path("."))
        doc = Document("/mo", cursor_position=3)
        results = list(completer.get_completions(doc, None))
        assert any(r.text == "/model" for r in results)

    def test_at_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            (cwd / "hello.txt").write_text("hi")

            completer = MergedCompleter(cwd)
            doc = Document("read @hel", cursor_position=9)
            results = list(completer.get_completions(doc, None))
            assert any("hello.txt" in r.text for r in results)

    def test_no_mode(self):
        completer = MergedCompleter(Path("."))
        doc = Document("just text", cursor_position=9)
        results = list(completer.get_completions(doc, None))
        assert len(results) == 0


class TestHelpers:
    def test_basename(self):
        assert _basename("src/main.py") == "main.py"
        assert _basename("file.txt") == "file.txt"
        assert _basename("a/b/c.ts") == "c.ts"

    def test_file_type_hint(self):
        assert _file_type_hint("main.py") == "Python"
        assert _file_type_hint("app.ts") == "TypeScript"
        assert _file_type_hint("logo.png") == "Image"
        assert _file_type_hint("data.csv") == "csv"


class TestSlashCommandsSync:
    """Tests that verify the dynamic slash command list matches the registry."""

    def _get_commands(self) -> list[str]:
        """Get the dynamic command list via _build_slash_commands()."""
        from octop_harness.cli.ui.completer import _build_slash_commands

        return _build_slash_commands()

    def test_contains_all_registered_commands(self) -> None:
        """Slash command list includes host COMMANDS and runtime slash names."""
        from octop_harness.cli.repl.commands import COMMANDS
        from octop_harness.cli.repl.slash_router import runtime_command_names

        cmds = self._get_commands()
        for name in COMMANDS:
            assert f"/{name}" in cmds, f"/{name} missing from slash commands"
        for name in runtime_command_names():
            assert f"/{name}" in cmds, f"/{name} missing from slash commands"

    def test_contains_registered_aliases(self) -> None:
        """Slash command list includes aliases like /quit, /q."""
        cmds = self._get_commands()
        assert "/quit" in cmds
        assert "/q" in cmds

    def test_does_not_contain_phantom_commands(self) -> None:
        """Slash command list must not contain unregistered host or runtime names."""
        from octop_harness.cli.repl.commands import _ALIASES, COMMANDS
        from octop_harness.cli.repl.slash_router import runtime_command_names

        cmds = self._get_commands()
        valid = (
            {f"/{name}" for name in COMMANDS}
            | {f"/{alias}" for alias in _ALIASES}
            | {f"/{name}" for name in runtime_command_names()}
        )
        for cmd in cmds:
            assert cmd in valid, f"{cmd} in slash commands but not registered"

    def test_contains_env_command(self) -> None:
        """Slash command list includes /env (added recently)."""
        assert "/env" in self._get_commands()

    def test_does_not_contain_resume_or_compact(self) -> None:
        """Slash command list must not contain /resume or /compact (never registered)."""
        cmds = self._get_commands()
        assert "/resume" not in cmds
        assert "/compact" not in cmds
        assert "/undo" not in cmds
        assert "/model" in cmds
        assert "/skills" in cmds
