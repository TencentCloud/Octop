"""tests/unit/browser/test_browser_env_off_event_loop.py — browser probes stay off the loop.

``GET /browser/env-status`` and the ``POST /browser/install`` SSE handler reach the filesystem
synchronously: ``_probe_env`` globs the Playwright cache and ``find_chrome`` stats every
candidate binary, while ``_verify_browser_binary`` shells out to ``<chrome> --version`` with a
10 s timeout. AGENTS.md §8 ("Do not add blocking I/O in async functions") and the sibling
helpers in ``infra/browser/setup.py`` (``asyncio.to_thread``) are the contract pinned here.
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from tests.support.fakes import fake_bin_path

from octop.api.routers.browser import env as env_router

# How long the blocked ``--version`` double waits for the loop to prove it is still running.
_LOOP_CALLBACK_DEADLINE_S = 2.0


class _ThreadRecorder:
    """Probe double that remembers whether it was handed a worker thread or the loop's thread."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.ran_on_main_thread: bool | None = None
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        self.ran_on_main_thread = threading.current_thread() is threading.main_thread()
        return self.result


async def test_env_status_offloads_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _ThreadRecorder({"playwright": True, "browsers_ok": True})
    monkeypatch.setattr(env_router, "_probe_env", probe)

    payload = await env_router.env_status(None)  # type: ignore[arg-type]

    assert probe.calls == 1
    assert probe.ran_on_main_thread is False
    assert payload == {"playwright": True, "browsers_ok": True}


async def test_install_stream_offloads_probe_and_version_check() -> None:
    find_probe = _ThreadRecorder(fake_bin_path("chrome"))
    run_probe = _ThreadRecorder(SimpleNamespace(returncode=0, stdout="Chrome 1.0\n", stderr=""))

    with (
        patch("octop_browser.cdp.launcher.find_chrome", side_effect=find_probe),
        patch("subprocess.run", side_effect=run_probe),
    ):
        response = await env_router.install(None)  # type: ignore[arg-type]
        events = [chunk async for chunk in response.body_iterator]

    assert find_probe.calls == 1
    assert find_probe.ran_on_main_thread is False
    assert run_probe.calls == 1
    assert run_probe.ran_on_main_thread is False
    assert '"success": true' in events[-1]


async def test_install_stream_keeps_the_loop_running_while_verify_blocks() -> None:
    """A slow ``--version`` must not freeze the loop the rest of the server runs on."""
    loop = asyncio.get_running_loop()
    callback_ran = threading.Event()

    def blocking_run(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        loop.call_soon_threadsafe(callback_ran.set)
        callback_ran.wait(timeout=_LOOP_CALLBACK_DEADLINE_S)
        return SimpleNamespace(returncode=0, stdout="Chrome 1.0\n", stderr="")

    with (
        patch(
            "octop_browser.cdp.launcher.find_chrome",
            return_value=fake_bin_path("chrome"),
        ),
        patch("subprocess.run", side_effect=blocking_run),
    ):
        response = await env_router.install(None)  # type: ignore[arg-type]
        events = [chunk async for chunk in response.body_iterator]

    # ``call_soon_threadsafe`` only queues the callback, so it is drained only while the loop is
    # free. On the event-loop path the probe blocks before the loop can run it and the wait expires.
    assert callback_ran.is_set(), "the browser version check blocked the event loop"
    assert '"success": true' in events[-1]
