"""Unit tests for SkillHub install error mapping and CLI subprocess helpers."""

from __future__ import annotations

import asyncio
import sys

import pytest
from fastapi import HTTPException

from octop.api.routers.skills import (
    _close_subprocess,
    _map_skillhub_install_error,
    _run_skillhub_cmd,
    _skillhub_stderr_suggests_upgrade,
)


def test_map_install_error_http_404() -> None:
    err = (
        '[skillhub] info: "agent-browser" not in index, using remote registry exact match\n'
        "Error: Download failed: HTTP 404 for https://api.skillhub.cn/api/v1/download?slug=agent-browser"
    )
    exc = _map_skillhub_install_error(err, "agent-browser")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert "agent-browser" in str(exc.detail)


def test_map_install_error_not_found() -> None:
    exc = _map_skillhub_install_error("skill nonexistent-xyz not found", "nonexistent-xyz")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404


def test_map_install_error_unknown_returns_none() -> None:
    assert _map_skillhub_install_error("network timeout", "foo") is None


def test_map_install_error_ssl_record_layer() -> None:
    from octop.i18n import error_message

    err = (
        "Failed to fetch hot rankings: [SSL: RECORD_LAYER_FAILURE] "
        "record layer failure (_ssl.c:1081)"
    )
    exc = _map_skillhub_install_error(err, "any-skill")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 502
    assert exc.detail == error_message("SKILLHUB_SSL_FAILED", "en")


def test_skillhub_cli_failure_detail_ssl() -> None:
    from octop.api.routers.skills import _skillhub_cli_failure_detail
    from octop.i18n import error_message

    detail = _skillhub_cli_failure_detail(
        "rankings",
        "Error: [SSL: RECORD_LAYER_FAILURE] record layer failure",
        locale="zh",
    )
    assert detail == error_message("SKILLHUB_SSL_FAILED", "zh")
    assert "openssl" in detail.lower() or "SSL" in detail or "证书" in detail


def test_skillhub_cli_failure_detail_passthrough() -> None:
    from octop.api.routers.skills import _skillhub_cli_failure_detail

    detail = _skillhub_cli_failure_detail("search", "network timeout", locale="en")
    assert detail == "skillhub search failed: network timeout"


def test_stderr_suggests_upgrade() -> None:
    assert _skillhub_stderr_suggests_upgrade(
        "[skillhub] 发现新版本 2026.6.18（当前 2026.6.17）。运行 `skillhub self-upgrade` 进行升级。"
    )
    assert not _skillhub_stderr_suggests_upgrade("Download failed: HTTP 404")


@pytest.mark.asyncio
async def test_run_skillhub_cmd_timeout_kills_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout must kill+drain the child so transports close on a live loop."""
    procs: list[asyncio.subprocess.Process] = []
    real_exec = asyncio.create_subprocess_exec

    async def _tracking_exec(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        proc = await real_exec(*args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _tracking_exec)
    with pytest.raises(TimeoutError):
        await _run_skillhub_cmd(
            sys.executable,
            ["-c", "import time; time.sleep(60)"],
            timeout=0.05,
        )
    assert procs, "expected create_subprocess_exec to run"
    assert procs[0].returncode is not None, "timed-out child must be reaped"
    # Flush deferred pipe close callbacks while the loop is still open.
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_close_subprocess_is_noop_when_already_exited() -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    assert proc.returncode is not None
    await _close_subprocess(proc)
    assert proc.returncode is not None
