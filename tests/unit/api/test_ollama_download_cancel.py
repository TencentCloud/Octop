"""Cancelled Ollama pulls stay cancelled when the worker thread finishes."""

from __future__ import annotations

import asyncio

import pytest

from octop.api.routers import ollama_download_store as store
from octop.api.routers.ollama_download_store import DownloadTaskStatus


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_tasks", {})
    monkeypatch.setattr(store, "_lock", asyncio.Lock())


async def _new_task() -> str:
    task = await store.create_task(
        repo_id="qwen2.5:7b",
        filename=None,
        backend="ollama",
        source="ollama",
    )
    return task.task_id


@pytest.mark.asyncio
async def test_cancel_after_pull_started_is_terminal() -> None:
    task_id = await _new_task()
    await store.update_status(task_id, DownloadTaskStatus.DOWNLOADING)
    assert await store.cancel_task(task_id) is True

    # The blocking SDK pull cannot be interrupted, so the worker thread still
    # reports COMPLETED after the user cancelled. That must not resurrect the
    # record or record the model the user dismissed.
    await store.update_status(
        task_id,
        DownloadTaskStatus.COMPLETED,
        result={"name": "qwen2.5:7b"},
    )
    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.CANCELLED
    assert task.result is None
    assert task.error is None


@pytest.mark.asyncio
async def test_cancel_before_pull_started_skips_pull(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import ollama_models

    task_id = await _new_task()
    assert await store.cancel_task(task_id) is True

    pulls: list[str] = []

    class _Manager:
        @staticmethod
        def pull_model(name: str) -> object:
            pulls.append(name)
            raise AssertionError("a cancelled pull must not start")

    monkeypatch.setattr("octop.infra.utils.ollama_manager.OllamaModelManager", _Manager)
    await ollama_models._run_pull_in_background(
        task_id, "qwen2.5:7b", asyncio.get_running_loop()
    )

    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.CANCELLED
    assert pulls == []


@pytest.mark.asyncio
async def test_uncancelled_pull_records_completion() -> None:
    task_id = await _new_task()
    await store.update_status(task_id, DownloadTaskStatus.DOWNLOADING)
    await store.update_status(
        task_id,
        DownloadTaskStatus.COMPLETED,
        result={"name": "qwen2.5:7b"},
    )
    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.COMPLETED
    assert task.result == {"name": "qwen2.5:7b"}
