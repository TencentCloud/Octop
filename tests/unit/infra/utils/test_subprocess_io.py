"""Unit tests for cross-platform subprocess stdout reads."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from octop.infra.utils import subprocess_io
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


def test_subprocess_json_event_survives_split_utf8_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"action": "show_qrcode", "content": "扫码登录"}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\r\n"
    cut = raw.index("扫".encode()) + 1
    chunks = iter([raw[:cut], b"", raw[cut:]])
    monkeypatch.setattr(subprocess_io, "read_available_bytes", lambda _stream: next(chunks))
    proc = SimpleNamespace(stdout=object())
    assert parse_subprocess_json_lines(proc) == []
    assert parse_subprocess_json_lines(proc) == []
    assert parse_subprocess_json_lines(proc) == [payload]


def test_subprocess_json_buffers_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = iter([b'{"action":', b'{"action":"second"}\n', b'"first"}\n'])
    monkeypatch.setattr(subprocess_io, "read_available_bytes", lambda _stream: next(chunks))
    first = SimpleNamespace(stdout=object())
    second = SimpleNamespace(stdout=object())
    assert parse_subprocess_json_lines(first) == []
    assert parse_subprocess_json_lines(second) == [{"action": "second"}]
    assert parse_subprocess_json_lines(first) == [{"action": "first"}]


def test_subprocess_final_drain_joins_pending_bytes_and_flushes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = SimpleNamespace(stdout=io.BytesIO(b'"finish"}\nplain log'))
    monkeypatch.setattr(subprocess_io, "read_available_bytes", lambda _stream: b'{"action":')
    assert parse_subprocess_json_lines(proc) == []
    assert parse_subprocess_json_lines(proc, final=True) == [
        {"action": "finish"},
        {"action": "log", "level": "info", "step": "raw", "message": "plain log"},
    ]
    assert parse_subprocess_json_lines(proc, final=True) == []


def test_creator_poll_recovers_split_finish_event_from_real_child() -> None:
    from octop.infra.gateway.bot_creators.feishu_runner import poll_feishu_creator

    finish = {
        "action": "finish",
        "level": "success",
        "data": {"app_id": "cli_test", "app_secret": "fake-test-secret"},
    }
    raw = json.dumps(finish).encode("utf-8")
    cut = len(raw) // 2
    prefix = b'{"action":"log","message":"ready"}\n' + raw[:cut]
    code = (
        "import sys; "
        f"sys.stdout.buffer.write({prefix!r}); sys.stdout.buffer.flush(); "
        "sys.stdin.buffer.read(1); "
        f"sys.stdout.buffer.write({raw[cut:]!r}); sys.stdout.buffer.flush()"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    lines = []
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = poll_feishu_creator(proc, lines)
            if result["events"]:
                break
            time.sleep(0.01)
        else:
            pytest.fail("child did not flush its initial event")
        assert result["status"] == "running"
        assert proc.stdin is not None
        proc.stdin.write(b"x")
        proc.stdin.flush()
        proc.wait(timeout=5)
        result = poll_feishu_creator(proc, lines)
        assert result["status"] == "finished"
        assert result["app_id"] == "cli_test"
        assert result["app_secret"] == "fake-test-secret"
        assert result["events"] == [finish]
        assert lines.count(finish) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdin is not None:
            proc.stdin.close()
        if proc.stdout is not None:
            proc.stdout.close()
