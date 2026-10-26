"""Regression: shell output must not be silently dropped on non-UTF-8 hosts.

On a Chinese Windows host ``locale.getpreferredencoding(False)`` returns
``cp936`` while most child processes emit UTF-8. With ``text=True`` and no
explicit ``encoding``, ``subprocess.run`` decoded the pipe as GBK inside its
reader thread, which raised ``UnicodeDecodeError`` there — the exception never
reached the caller, so ``stdout`` came back as ``None`` and the tool reported
``<no output>`` with exit code 0 (issue #1959).

Fixing it by hard-coding UTF-8 would repair that case but mangle ``cmd``
builtins, which emit the console code page, so the backend now decodes bytes
with a UTF-8 → locale → GBK fallback chain (see ``decode_child_output``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from octop_harness.backends.local_shell import (
    HarnessLocalShellBackend,
    decode_child_output,
)


def _backend(root: Path) -> HarnessLocalShellBackend:
    return HarnessLocalShellBackend(root_dir=root, virtual_mode=False)


def test_decode_child_output_handles_missing_and_empty() -> None:
    assert decode_child_output(None) == ""
    assert decode_child_output(b"") == ""


def test_decode_child_output_prefers_utf8() -> None:
    assert decode_child_output("中文测试".encode()) == "中文测试"


def test_decode_child_output_falls_back_to_the_console_code_page() -> None:
    """``cmd`` builtins emit GBK; forcing UTF-8 would mojibake them."""
    assert decode_child_output("中文测试".encode("gbk")) == "中文测试"


def test_decode_child_output_degrades_instead_of_raising() -> None:
    assert decode_child_output(b"before" + bytes([0xFF]) + b"after") == "before\ufffdafter"


def test_utf8_child_output_is_decoded_not_dropped(tmp_path: Path) -> None:
    script = tmp_path / "emit_utf8.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write('中文测试'.encode('utf-8'))\n",
        encoding="utf-8",
    )

    result = _backend(tmp_path).execute(f'"{sys.executable}" "{script}"')

    assert result.exit_code == 0
    assert "中文测试" in result.output
    assert "<no output>" not in result.output


def test_gbk_child_output_is_decoded_not_mangled(tmp_path: Path) -> None:
    """The fix must not trade one broken encoding for another."""
    script = tmp_path / "emit_gbk.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write('中文测试'.encode('gbk'))\n",
        encoding="utf-8",
    )

    result = _backend(tmp_path).execute(f'"{sys.executable}" "{script}"')

    assert result.exit_code == 0
    assert "中文测试" in result.output
    assert "<no output>" not in result.output


def test_undecodable_bytes_do_not_blank_the_output(tmp_path: Path) -> None:
    """A stray non-UTF-8 byte must degrade, not lose the whole output."""
    script = tmp_path / "emit_mixed.py"
    script.write_text(
        "import sys\nsys.stdout.buffer.write(b'before' + bytes([0xFF]) + b'after')\n",
        encoding="utf-8",
    )

    result = _backend(tmp_path).execute(f'"{sys.executable}" "{script}"')

    assert result.exit_code == 0
    assert "before" in result.output
    assert "after" in result.output
    assert "<no output>" not in result.output
