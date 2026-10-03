"""Unit tests for the terminal-state guard in the download task store.

A cancelled download task must stay cancelled even when the background
pull thread later reports completion or failure (late updates must not
resurrect or rewrite terminal states).
"""

from __future__ import annotations

import pytest

from octop.api.routers import ollama_download_store as store
from octop.api.routers.ollama_download_store import DownloadTaskStatus


@pytest.fixture(autouse=True)
def _clean_store():
    """Isolate the module-level task dict around every test."""
    store._tasks.clear()
    yield
    store._tasks.clear()


async def _make_task() -> str:
    task = await store.create_task(
        repo_id="qwen2.5:0.5b",
        filename=None,
        backend="ollama",
        source="ollama",
    )
    return task.task_id


async def test_update_status_does_not_resurrect_cancelled_task() -> None:
    task_id = await _make_task()
    assert await store.cancel_task(task_id) is True

    await store.update_status(
        task_id,
        DownloadTaskStatus.COMPLETED,
        result={"digest": "abc"},
    )

    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.CANCELLED
    assert task.result is None


async def test_update_status_does_not_overwrite_cancelled_with_failed() -> None:
    task_id = await _make_task()
    assert await store.cancel_task(task_id) is True

    await store.update_status(
        task_id,
        DownloadTaskStatus.FAILED,
        error="connection reset",
    )

    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.CANCELLED
    assert task.error is None


async def test_cancelled_task_cannot_return_to_downloading() -> None:
    task_id = await _make_task()
    assert await store.cancel_task(task_id) is True

    await store.update_status(task_id, DownloadTaskStatus.DOWNLOADING)

    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.CANCELLED


async def test_completed_task_is_immutable() -> None:
    task_id = await _make_task()
    await store.update_status(
        task_id,
        DownloadTaskStatus.COMPLETED,
        result={"digest": "abc"},
    )

    await store.update_status(
        task_id,
        DownloadTaskStatus.FAILED,
        error="late failure",
    )

    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.COMPLETED
    assert task.error is None


async def test_normal_lifecycle_still_transitions() -> None:
    task_id = await _make_task()

    await store.update_status(task_id, DownloadTaskStatus.DOWNLOADING)
    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.DOWNLOADING

    await store.update_status(
        task_id,
        DownloadTaskStatus.COMPLETED,
        result={"digest": "abc"},
    )
    task = await store.get_task(task_id)
    assert task is not None
    assert task.status is DownloadTaskStatus.COMPLETED
    assert task.result == {"digest": "abc"}

    # Cancelling a finished task is still rejected.
    assert await store.cancel_task(task_id) is False
