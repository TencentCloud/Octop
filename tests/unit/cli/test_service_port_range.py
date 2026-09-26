"""``--port`` bounds for `octop service` (argument parsing, every platform).

`octop service` only manages units on Linux and macOS, so ``test_service_cmd.py``
is POSIX-gated. These assertions stop inside Click's parameter parsing — before
any platform code is reached — so they have to stay ungated: the range check is
what keeps an unbindable port out of ``config.json``.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.main import cli


def _all_output(result: Any) -> str:
    """stdout + stderr across click versions (8.2+ can separate the streams)."""
    text = result.output or ""
    with contextlib.suppress(ValueError, AttributeError):
        text += result.stderr
    return text


@pytest.mark.parametrize("value", ["70000", "-1"])
def test_service_start_rejects_unbindable_port_before_saving_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """``--port 70000`` must be a usage error: nothing can bind it.

    ``octop run --port`` got this bound, but ``octop service start --port`` still
    took the raw int and wrote it into ``config.json`` before installing the
    unit — so every later start, including the unit's bare ``octop run``,
    inherited the unusable port.
    """
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(cli, ["service", "start", "--port", value])
    assert result.exit_code != 0, _all_output(result)
    assert "is not in the range" in _all_output(result)
    assert not (tmp_path / "config.json").exists()


@pytest.mark.parametrize("value", ["0", "65535"])
def test_bindable_ports_stay_accepted_by_service_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Port 0 asks the OS for a free port and 65535 is bindable, so neither is a
    range error — whatever the command reports next is a later concern."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(cli, ["service", "start", "--port", value])
    assert "is not in the range" not in _all_output(result)
