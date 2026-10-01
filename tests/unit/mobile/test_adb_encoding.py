"""adb writes UTF-8, so ``infra/mobile/adb.py`` must not decode it with the ANSI code page.

Same defect family as #1118, one module over: ``text=True`` without ``encoding``
makes ``subprocess`` decode with ``locale.getpreferredencoding()``. ``adb`` is a
native binary that prints UTF-8 device strings, so on a Chinese Windows host
(cp936) the CJK ``ro.product.marketname`` of a Xiaomi/Huawei device comes back as
mojibake, and any byte cp936 cannot represent kills the reader thread silently —
``CompletedProcess.stdout`` then arrives as ``None`` and ``list_devices()`` raises
``AttributeError`` on ``None.splitlines()``, escaping its ``except OSError`` guard.
"""

from __future__ import annotations

import ast
import os
import shlex
import sys
from pathlib import Path

from octop.infra.mobile import adb

_FAKE_ADB = """
import sys

argv = sys.argv[1:]
out = sys.stdout.buffer
if argv[:1] == ["devices"]:
    out.write(b"List of devices attached\\n")
    out.write(b"12345678\\tdevice\\n")
    out.write(b"** daemon \\xff\\xfe\\n")
    sys.exit(0)
if "echo model=" in " ".join(argv):
    out.write("market=小米 14 Pro\\n".encode("utf-8"))
    out.write(b"model=2211133C\\n")
    out.write(b"manufacturer=Xiaomi\\n")
    out.write(b"release=14\\n")
    out.write(b"sdk=34\\n")
    out.write(b"size=Physical size: 1080x2400\\n")
    sys.exit(0)
sys.exit(1)
"""


def _fake_adb(tmp_path: Path) -> str:
    """A stand-in ``adb`` that writes raw bytes, like the real binary does."""
    script = tmp_path / "fake_adb.py"
    script.write_text(_FAKE_ADB, encoding="utf-8")
    if os.name == "nt":
        # Windows cannot exec a shebang script; a .cmd shim dispatches to this
        # interpreter, mirroring tests/unit/agents/test_octop_builtin_skills.py.
        exe = tmp_path / "adb.cmd"
        exe.write_text(f'@"{sys.executable}" "%~dp0fake_adb.py" %*\n', encoding="utf-8")
    else:
        exe = tmp_path / "adb"
        exe.write_text(
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n',
            encoding="utf-8",
        )
        exe.chmod(0o755)
    return str(exe)


def test_list_devices_survives_undecodable_bytes(tmp_path: Path) -> None:
    """One bad byte used to erase the whole listing: the reader thread died on it,
    ``stdout`` became ``None`` and the parse loop raised ``AttributeError``."""
    assert adb.list_devices(adb=_fake_adb(tmp_path)) == ["12345678"]


def test_device_info_keeps_the_utf8_market_name(tmp_path: Path) -> None:
    """The Remote Phone info panel reads its model name from the device."""
    info = adb.device_info("12345678", adb=_fake_adb(tmp_path))
    assert info["model"] == "小米 14 Pro"
    assert info["width"] == 1080


def test_every_text_run_pins_utf8_and_a_lossy_handler() -> None:
    """Codec-agnostic guard: the two tests above only go red where the host codec
    actually chokes on the payload, so assert the pinned codec everywhere instead."""
    tree = ast.parse(Path(adb.__file__).read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"run", "check_output", "check_call"} or not isinstance(
            node.func.value, ast.Name
        ):
            continue
        if node.func.value.id != "subprocess":
            continue
        pinned = {k.arg: getattr(k.value, "value", None) for k in node.keywords if k.arg}
        if not {"text", "universal_newlines"} & pinned.keys():
            continue
        # errors="strict" would leave the reader thread free to die all over again.
        if pinned.get("encoding") != "utf-8" or pinned.get("errors") != "replace":
            offenders.append(node.lineno)
    assert offenders == []
