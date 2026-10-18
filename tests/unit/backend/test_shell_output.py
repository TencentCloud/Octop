"""Host shell output survives a non-UTF-8 locale (issue #1959)."""

from __future__ import annotations

import locale
import subprocess
import sys
from pathlib import Path

from octop_harness.backends.local_shell import HarnessLocalShellBackend

from octop.infra.backend.shell_output import (
    _ShellSubprocess,
    decode_child_output,
    install_shell_output_decoding,
)

# Valid GBK, illegal in UTF-8 and in cp1252 (GitHub Windows). Forces the GBK step.
_GBK_ONLY = bytes((0x81, 0x40))


def _after_utf8(data: bytes) -> str:
    """What the chain should return once strict UTF-8 has failed.

    A single-byte locale such as cp1252 accepts every byte in ``中文测试``'s
    GBK form, so that console code page wins and GBK is not reached. Locales
    that reject the bytes (UTF-8, and cp1252 for ``_GBK_ONLY``) fall through.
    """
    encoding = locale.getpreferredencoding(False)
    if encoding:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    try:
        return data.decode("gbk")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _script(tmp_path: Path, name: str, payload: bytes) -> str:
    path = tmp_path / name
    path.write_text(
        "import sys\nsys.stdout.buffer.write(" + repr(payload) + ")\n",
        encoding="utf-8",
    )
    return f'"{sys.executable}" "{path}"'


def test_decode_child_output_chain() -> None:
    assert decode_child_output(None) == ""
    assert decode_child_output(b"") == ""
    assert decode_child_output("已经是文本") == "已经是文本"
    assert decode_child_output("中文测试".encode()) == "中文测试"
    assert decode_child_output("中文测试".encode("gbk")) == _after_utf8("中文测试".encode("gbk"))
    assert decode_child_output(_GBK_ONLY) == "丂"
    mixed = b"before" + bytes([0xFF]) + b"after"
    assert decode_child_output(mixed) == _after_utf8(mixed)
    assert "before" in decode_child_output(mixed)
    assert "after" in decode_child_output(mixed)


def test_cp1252_locale_accepts_gbk_text_but_not_every_gbk_byte(monkeypatch) -> None:
    """GitHub Windows is cp1252: that code page swallows ``中文测试``'s GBK bytes."""
    monkeypatch.setattr(locale, "getpreferredencoding", lambda _do_setlocale=False: "cp1252")
    text = "中文测试".encode("gbk")
    assert decode_child_output(text) == text.decode("cp1252")
    assert decode_child_output(_GBK_ONLY) == "丂"
    mixed = b"before" + bytes([0xFF]) + b"after"
    assert decode_child_output(mixed) == "beforeÿafter"


def test_install_is_idempotent_and_leaves_stdlib() -> None:
    import octop_harness.backends.bwrap_shell as bwrap_shell
    import octop_harness.backends.local_shell as local_shell

    install_shell_output_decoding()
    first = local_shell.subprocess
    install_shell_output_decoding()
    assert local_shell.subprocess is first
    assert isinstance(first, _ShellSubprocess)
    assert isinstance(bwrap_shell.subprocess, _ShellSubprocess)
    assert subprocess.Popen is not first.run
    assert local_shell.subprocess.TimeoutExpired is subprocess.TimeoutExpired
    assert local_shell.subprocess.DEVNULL is subprocess.DEVNULL
    assert local_shell.subprocess.list2cmdline(["a b"]) == subprocess.list2cmdline(["a b"])


def test_explicit_encoding_is_left_alone() -> None:
    import octop_harness.backends.local_shell as local_shell

    install_shell_output_decoding()
    result = local_shell.subprocess.run(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes([255]))"],
        check=False,
        capture_output=True,
        text=True,
        encoding="latin-1",
    )
    assert result.stdout == "ÿ"


def test_execute_decodes_utf8_and_gbk(tmp_path: Path) -> None:
    install_shell_output_decoding()
    backend = HarnessLocalShellBackend(root_dir=tmp_path, virtual_mode=False)

    gbk_bytes = "中文测试".encode("gbk")
    utf8 = backend.execute(_script(tmp_path, "utf8.py", "中文测试".encode()))
    gbk = backend.execute(_script(tmp_path, "gbk.py", gbk_bytes))
    mixed = backend.execute(_script(tmp_path, "mixed.py", b"before" + bytes([0xFF]) + b"after"))
    gbk_only = backend.execute(_script(tmp_path, "gbk_only.py", _GBK_ONLY))

    assert utf8.exit_code == 0
    assert "中文测试" in utf8.output
    assert "<no output>" not in utf8.output
    assert gbk.exit_code == 0
    assert _after_utf8(gbk_bytes) in gbk.output
    assert "<no output>" not in gbk.output
    assert gbk_only.exit_code == 0
    assert "丂" in gbk_only.output
    assert mixed.exit_code == 0
    assert "before" in mixed.output
    assert "after" in mixed.output
    assert "<no output>" not in mixed.output


def test_bwrap_module_run_uses_the_same_decoder() -> None:
    import octop_harness.backends.bwrap_shell as bwrap_shell

    install_shell_output_decoding()
    result = bwrap_shell.subprocess.run(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes([0x81, 0x40]))"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == "丂"


def test_skips_install_when_harness_already_decodes(monkeypatch) -> None:
    import octop_harness.backends.local_shell as local_shell

    import octop.infra.backend.shell_output as shell_output

    monkeypatch.setattr(shell_output, "_INSTALLED", False)
    monkeypatch.setattr(local_shell, "decode_child_output", lambda data: data, raising=False)
    current = local_shell.subprocess
    if isinstance(current, _ShellSubprocess):
        monkeypatch.setattr(local_shell, "subprocess", current._real)
    shell_output.install_shell_output_decoding()
    assert not isinstance(local_shell.subprocess, _ShellSubprocess)
