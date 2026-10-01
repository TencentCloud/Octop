"""Connector CLIs write UTF-8, so the runner must not decode them with the ANSI code page."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from octop.infra.connectors.gateway import cli_runner

_ECHO_STDOUT = """
import sys, json
payload = json.loads(sys.argv[1])
sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
"""

_ECHO_STDIN = """
import sys
data = sys.stdin.buffer.read().decode("utf-8")
sys.stdout.buffer.write(("回声:" + data).encode("utf-8"))
"""

_EMIT_STDERR = """
import sys
text = "\\u6743\\u9650\\u4e0d\\u8db3\\uff1a\\u65e0\\u6cd5\\u8bfb\\u53d6\\u901a\\u8baf\\u5f55"
sys.stderr.buffer.write(text.encode("utf-8") + b"\\n")
sys.exit(1)
"""


def test_run_cli_decodes_connector_output_as_utf8() -> None:
    """A CLI returning CJK must not come back as the empty '{}' fallback."""
    payload = {"name": "张三", "msg": "已完成 ✅"}
    argv = [sys.executable, "-c", _ECHO_STDOUT, json.dumps(payload, ensure_ascii=False)]
    out = cli_runner.run_cli(argv, timeout_s=60.0)
    assert json.loads(out) == payload


def test_run_cli_encodes_stdin_as_utf8() -> None:
    argv = [sys.executable, "-c", _ECHO_STDIN]
    assert cli_runner.run_cli(argv, stdin_text="你好", timeout_s=60.0) == "回声:你好"


def test_run_cli_surfaces_utf8_stderr_in_the_error() -> None:
    argv = [sys.executable, "-c", _EMIT_STDERR]
    with pytest.raises(ValueError, match="权限不足"):
        cli_runner.run_cli(argv, timeout_s=60.0)


def test_run_cli_pins_an_explicit_codec(monkeypatch: pytest.MonkeyPatch) -> None:
    """Codec-agnostic guard: without this the two tests above only go red on a
    machine whose default codec is not UTF-8, so CI could never see the regression."""
    captured: dict[str, object] = {}
    real_run = subprocess.run

    def spy(argv: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return real_run(argv, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(cli_runner.subprocess, "run", spy)
    cli_runner.run_cli([sys.executable, "-c", "pass"], timeout_s=60.0)
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"
