"""Unit tests for cross-platform subprocess stdout reads."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from octop.infra.utils.subprocess_io import parse_json_lines, parse_subprocess_json_lines


def test_parse_json_lines_decodes_ndjson() -> None:
    raw = b'{"action":"log","message":"hi"}\nnot-json\n'
    lines = parse_json_lines(raw)
    assert len(lines) == 2
    assert lines[0]["action"] == "log"
    assert lines[1]["step"] == "raw"


def test_parse_subprocess_json_lines_from_echo() -> None:
    payload = {"action": "show_qrcode", "content": "{}"}
    code = f"import json; print(json.dumps({json.dumps(payload)}))"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    try:
        proc.wait(timeout=5)
        lines = parse_subprocess_json_lines(proc)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert any(line.get("action") == "show_qrcode" for line in lines)


def test_parse_json_lines_accepts_text() -> None:
    lines = parse_json_lines('{"action":"scan_code","scan_code":"abc"}\n')
    assert lines == [{"action": "scan_code", "scan_code": "abc"}]


@pytest.mark.skipif(os.name != "nt", reason="text-mode pipes only read as str on Windows")
def test_text_mode_pipe_events_are_read() -> None:
    payload = {"action": "scan_code", "scan_code": "abc"}
    code = f"import json; print(json.dumps({json.dumps(payload)}), flush=True)"
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True,
    )
    try:
        proc.wait(timeout=5)
        lines = parse_subprocess_json_lines(proc)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert lines == [payload]
