"""Unit tests for ui/file_ref.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from octop_harness.cli.ui.file_ref import (
    _walk_files,
    list_project_files,
    parse_at_references,
    resolve_references,
)


class TestParseAtReferences:
    def test_single_reference(self):
        refs = parse_at_references("look at @src/main.py")
        assert len(refs) == 1
        assert refs[0].raw == "@src/main.py"
        assert refs[0].path == "src/main.py"

    def test_multiple_references(self):
        refs = parse_at_references("compare @a.py and @b/c.ts")
        assert len(refs) == 2
        assert refs[0].path == "a.py"
        assert refs[1].path == "b/c.ts"

    def test_no_extension_no_match(self):
        """@mentions without extension should NOT match (avoid email confusion)."""
        refs = parse_at_references("hey @john review this")
        assert len(refs) == 0

    def test_deduplication(self):
        refs = parse_at_references("@main.py and again @main.py")
        assert len(refs) == 1

    def test_complex_paths(self):
        refs = parse_at_references("@src/octop_harness.cli/ui/file_ref.py")
        assert len(refs) == 1
        assert refs[0].path == "src/octop_harness.cli/ui/file_ref.py"

    def test_dotfile(self):
        refs = parse_at_references("edit @.gitignore")
        # .gitignore doesn't match our pattern (requires extension after last dot)
        # This is intentional to avoid noise
        assert len(refs) == 0

    def test_hyphen_in_path(self):
        refs = parse_at_references("check @my-file.ts")
        assert len(refs) == 1
        assert refs[0].path == "my-file.ts"


class TestResolveReferences:
    def test_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            test_file = cwd / "hello.py"
            test_file.write_text("print('hello')\n")

            blocks, refs = resolve_references("look at @hello.py", cwd)
            assert len(refs) == 1
            assert refs[0].is_resolved
            assert refs[0].size > 0
            assert len(blocks) == 2  # text + file content
            assert blocks[0]["type"] == "text"
            assert "[see attached: hello.py]" in blocks[0]["text"]
            assert '<file path="hello.py">' in blocks[1]["text"]

    def test_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            blocks, refs = resolve_references("look at @ghost.py", cwd)
            assert len(refs) == 0  # not resolved, so not in output
            assert len(blocks) == 1  # just the text

    def test_image_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            img = cwd / "logo.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            blocks, refs = resolve_references("see @logo.png", cwd)
            assert len(refs) == 1
            assert refs[0].is_image
            assert len(blocks) == 2
            assert blocks[1]["type"] == "image_url"
            assert blocks[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_no_refs_passthrough(self):
        blocks, refs = resolve_references("just a normal message", Path("."))
        assert len(refs) == 0
        assert len(blocks) == 1
        assert blocks[0]["text"] == "just a normal message"

    def test_path_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir) / "sub"
            cwd.mkdir()
            # Create a file above cwd
            above = Path(tmpdir) / "secret.py"
            above.write_text("SECRET=123")

            _blocks, refs = resolve_references("look at @../secret.py", cwd)
            # Should not resolve (path escapes project dir)
            assert len(refs) == 0


class TestListProjectFiles:
    def test_walk_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            (cwd / "a.py").write_text("x")
            (cwd / "b.txt").write_text("y")
            sub = cwd / "sub"
            sub.mkdir()
            (sub / "c.ts").write_text("z")

            files = list_project_files(cwd)
            assert "a.py" in files
            assert "b.txt" in files
            # sub/c.ts should also appear
            assert any("c.ts" in f for f in files)

    def test_hidden_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            hidden = cwd / ".hidden"
            hidden.mkdir()
            (hidden / "secret.py").write_text("x")
            (cwd / "visible.py").write_text("y")

            files = _walk_files(cwd, 100)
            assert "visible.py" in files
            assert not any("secret" in f for f in files)
