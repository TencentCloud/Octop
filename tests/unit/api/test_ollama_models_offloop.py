"""Ollama routes must not run the blocking manager calls on the event loop.

``ollama_manager`` blocks: ``_is_ollama_reachable`` is a 3s-timeout
``urllib.request.urlopen``, ``_start_ollama_server`` polls 10x1s, and
``stop_ollama_service`` polls 20x0.25s. ``_run_pull`` already offloads its
``pull_model`` call with ``run_in_executor`` — these sibling call sites in the
same module were simply never converted.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.api.routers import ollama_models


def _server(values: dict[str, str | None]) -> SimpleNamespace:
    store = dict(values)
    repo = MagicMock()
    repo.get.side_effect = lambda key: store.get(key)

    def _set(key: str, value: str) -> None:
        store[key] = value

    repo.set.side_effect = _set
    return SimpleNamespace(services=SimpleNamespace(settings_repo=repo))


def _blocker(seconds: float) -> MagicMock:
    """A manager call that blocks the thread it runs on, like the real one."""
    return MagicMock(side_effect=lambda *a, **k: time.sleep(seconds))


async def _run_measuring_lag(coro_fn) -> float:
    """Run ``coro_fn`` while a 20ms ticker measures the longest loop stall.

    The ticker is warmed up before ``coro_fn`` runs and kept alive after it
    returns, so a call that blocks the loop *synchronously* (before its first
    ``await``) is still bracketed by two marks. Verified against a bare
    ``time.sleep(0.4)`` (~430ms) and the same sleep offloaded to an executor
    (~60ms).
    """
    marks: list[float] = []

    async def ticker() -> None:
        while True:
            marks.append(time.perf_counter())
            await asyncio.sleep(0.02)

    tick = asyncio.create_task(ticker())
    await asyncio.sleep(0.08)  # let the ticker establish a baseline
    try:
        await coro_fn()
    finally:
        await asyncio.sleep(0.06)  # keep ticking across the call boundary
        tick.cancel()
        await asyncio.gather(tick, return_exceptions=True)

    if len(marks) < 2:
        return 0.0
    return max(b - a for a, b in zip(marks, marks[1:], strict=False)) * 1000


@pytest.mark.asyncio
async def test_list_ollama_models_does_not_block_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.utils import ollama_manager as om
    from octop.infra.utils.ollama_manager import OllamaModelInfo

    monkeypatch.setattr(om, "is_ollama_reachable", lambda: True)
    listed = MagicMock(
        side_effect=lambda *a, **k: (time.sleep(0.4), [OllamaModelInfo(name="m:latest", size=1)])[1]
    )
    monkeypatch.setattr(om.OllamaModelManager, "list_models", listed)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "false"})

    sink: dict = {}
    lag = await _run_measuring_lag(
        lambda: _capture(lambda: ollama_models.list_ollama_models(server=server, _=None), sink)
    )

    assert [m.name for m in sink["result"]] == ["m:latest"], "route must still return the models"
    assert lag < 250, f"event loop stalled for {lag:.0f}ms while listing models"


@pytest.mark.asyncio
async def test_delete_ollama_model_does_not_block_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.utils import ollama_manager as om

    monkeypatch.setattr(om.OllamaModelManager, "delete_model", _blocker(0.4))
    monkeypatch.setattr(om, "apply_models_dir", lambda *a, **k: None)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "false"})

    sink: dict = {}
    lag = await _run_measuring_lag(
        lambda: _capture(
            lambda: ollama_models.delete_ollama_model(name="m:latest", server=server, _=None),
            sink,
        )
    )

    assert sink.get("result") == {"status": "deleted", "name": "m:latest"}
    assert lag < 250, f"event loop stalled for {lag:.0f}ms while deleting a model"


@pytest.mark.asyncio
async def test_put_ollama_service_does_not_block_the_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.utils import ollama_manager as om

    monkeypatch.setattr(om, "stop_ollama_service", _blocker(0.3))
    monkeypatch.setattr(om, "start_ollama_service", _blocker(0.3))
    monkeypatch.setattr(om, "is_ollama_reachable", lambda: True)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "true"})

    sink: dict = {}
    lag = await _run_measuring_lag(
        lambda: _capture(
            lambda: ollama_models.put_ollama_service(
                body=ollama_models.OllamaServiceBody(models_dir=str(tmp_path)),
                server=server,
                _=None,
            ),
            sink,
        )
    )

    assert sink["result"].enabled is True, "the route must still return the service status"
    assert lag < 250, f"event loop stalled for {lag:.0f}ms while restarting the service"


async def _capture(awaitable_fn, sink: dict) -> None:
    """Await ``awaitable_fn()`` and record the result under ``"result"``."""
    sink["result"] = await awaitable_fn()
