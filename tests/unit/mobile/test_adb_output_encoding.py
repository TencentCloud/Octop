"""Unit tests for adb subprocess output decoding.

``adb`` is a native binary that emits UTF-8, so every text-mode call must pin
the decode codec instead of inheriting the desktop session's ANSI code page
(cp936 on Chinese Windows). See issue #1124.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import patch

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.mobile import adb as adb_mod
from octop.infra.mobile.adb import (
    _adb_client_command,
    adb_connect,
    list_devices,
    primary_display_id,
    shell,
    wm_size,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX shell script stub")

ADB = fake_bin_path("adb")

# Every adb entry point whose stdout is decoded as text.
TEXT_CALLERS = [
    (list_devices, ()),
    (adb_connect, ("127.0.0.1:5555",)),
    (primary_display_id, ("emulator-5554",)),
    (wm_size, ("emulator-5554",)),
    (_adb_client_command, ("emulator-5554", "get-state")),
    (shell, ("emulator-5554", "getprop")),
]


@pytest.mark.parametrize(("func", "args"), TEXT_CALLERS)
def test_text_calls_pin_utf8_decode(func: Any, args: tuple) -> None:
    """The locale's preferred encoding must never be used to decode adb output."""
    seen: dict[str, Any] = {}

    def _capture(*_argv: Any, **kwargs: Any) -> CompletedProcess[str]:
        seen.update(kwargs)
        return CompletedProcess(args=["adb"], returncode=0, stdout="", stderr="")

    with patch("octop.infra.mobile.adb.subprocess.run", _capture):
        func(*args, adb=ADB)

    assert seen["text"] is True
    assert seen["encoding"] == "utf-8"
    # ``replace`` keeps an undecodable byte from raising inside the reader
    # thread, which would leave ``CompletedProcess.stdout`` as ``None``.
    assert seen["errors"] == "replace"


def test_list_devices_skips_header_and_parses_serials() -> None:
    stdout = "List of devices attached\nemulator-5554\tdevice\n3b678f5c\tdevice\n"
    with patch(
        "octop.infra.mobile.adb.subprocess.run",
        return_value=CompletedProcess(args=["adb"], returncode=0, stdout=stdout, stderr=""),
    ):
        assert list_devices(adb=ADB) == ["emulator-5554", "3b678f5c"]


def test_list_devices_returns_empty_when_stdout_is_missing() -> None:
    """A failed decode leaves ``stdout`` as ``None``; that means "no devices"."""
    with patch(
        "octop.infra.mobile.adb.subprocess.run",
        return_value=CompletedProcess(args=["adb"], returncode=0, stdout=None, stderr=""),
    ):
        assert list_devices(adb=ADB) == []


def test_shell_returns_text_for_utf8_device_model() -> None:
    """``getprop ro.product.marketname`` is UTF-8 on China-market ROMs."""
    payload = "model=\u5c0f\u7c73 14 Pro\n"
    with patch(
        "octop.infra.mobile.adb.subprocess.run",
        return_value=CompletedProcess(args=["adb"], returncode=0, stdout=payload, stderr=""),
    ):
        code, out = shell("emulator-5554", "getprop", adb=ADB)

    assert code == 0
    assert out == payload.strip()
    assert adb_mod.parse_device_info_payload("emulator-5554", out)["model"] == "\u5c0f\u7c73 14 Pro"


@posix_only
def test_list_devices_reads_a_real_utf8_child_process(tmp_path: Path) -> None:
    """A UTF-8-emitting child stands in for ``adb devices`` on any desktop locale."""
    fake_adb = tmp_path / "adb"
    fake_adb.write_text(
        "#!/bin/sh\n"
        "printf 'List of devices attached\\n\\345\\260\\217\\347\\261\\26314Pro\\tdevice\\n'\n",
        encoding="utf-8",
    )
    fake_adb.chmod(0o755)

    assert list_devices(adb=str(fake_adb)) == ["\u5c0f\u7c7314Pro"]


def test_binary_capture_calls_stay_binary() -> None:
    """Screencap must keep reading raw bytes, so it takes no text codec."""
    seen: dict[str, Any] = {}

    def _capture(*_argv: Any, **kwargs: Any) -> CompletedProcess[bytes]:
        seen.update(kwargs)
        return CompletedProcess(args=["adb"], returncode=0, stdout=b"", stderr=b"")

    with patch("octop.infra.mobile.adb.subprocess.run", _capture):
        adb_mod.screencap_png("emulator-5554", adb=ADB)

    assert "text" not in seen
    assert "encoding" not in seen
    assert seen["timeout"] == 8


@pytest.mark.parametrize(
    "exc",
    [OSError("adb missing"), subprocess.TimeoutExpired(cmd="adb", timeout=5)],
)
def test_list_devices_swallows_launch_failures(exc: BaseException) -> None:
    with patch("octop.infra.mobile.adb.subprocess.run", side_effect=exc):
        assert list_devices(adb=ADB) == []
