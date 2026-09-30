"""Unit tests for thread folder/tag REST APIs (list filters + patch + folders endpoint)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from octop.api.routers.chat import history as history_mod
from octop.api.routers.chat.models import RenameThreadBody
from octop.infra.db.repos.threads import ThreadRow


def _thread_row(
    thread_id: str,
    *,
    folder: str | None = None,
    tags: tuple[str, ...] = (),
) -> ThreadRow:
    return ThreadRow(
        id=1,
        thread_id=thread_id,
        agent_id="agt_1",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
        title="t",
        last_active=5,
        created_at=1,
        folder=folder,
        tags=tags,
    )


def _server_with_registry(thread_registry: MagicMock) -> MagicMock:
    server = MagicMock()
    agent_row = MagicMock(user_id=1)
    server.app_runtime.agent_registry.get_row.return_value = agent_row
    server.app_runtime.gateway.thread_registry = thread_registry
    return server


_USER = MagicMock(id=1, is_admin=False)


@pytest.mark.asyncio
async def test_list_threads_response_includes_folder_and_tags() -> None:
    thread_registry = MagicMock()
    thread_registry.list_threads.return_value = [
        _thread_row("thr_a", folder="工作", tags=("重要", "日报")),
        _thread_row("thr_b"),
    ]
    thread_registry.get_bound_thread_id.return_value = None
    server = _server_with_registry(thread_registry)

    out = await history_mod.list_threads("agt_1", limit=10, user=_USER, server=server)

    assert out[0]["folder"] == "工作"
    assert out[0]["tags"] == ["重要", "日报"]
    assert out[1]["folder"] is None
    assert out[1]["tags"] == []


@pytest.mark.asyncio
async def test_list_threads_filters_by_folder() -> None:
    thread_registry = MagicMock()
    thread_registry.list_threads_by_folder.return_value = [
        _thread_row("thr_a", folder="工作"),
    ]
    thread_registry.get_bound_thread_id.return_value = None
    server = _server_with_registry(thread_registry)

    out = await history_mod.list_threads(
        "agt_1", limit=10, folder="工作", user=_USER, server=server
    )

    thread_registry.list_threads_by_folder.assert_called_once_with(
        agent_id="agt_1", user_id=1, folder="工作", limit=10
    )
    thread_registry.list_threads.assert_not_called()
    assert [r["thread_id"] for r in out] == ["thr_a"]


@pytest.mark.asyncio
async def test_list_threads_filters_by_tag() -> None:
    thread_registry = MagicMock()
    thread_registry.list_threads_by_tag.return_value = [
        _thread_row("thr_a", tags=("重要",)),
    ]
    thread_registry.get_bound_thread_id.return_value = None
    server = _server_with_registry(thread_registry)

    out = await history_mod.list_threads("agt_1", limit=10, tag="重要", user=_USER, server=server)

    thread_registry.list_threads_by_tag.assert_called_once_with(
        agent_id="agt_1", user_id=1, tag="重要", limit=10
    )
    assert [r["thread_id"] for r in out] == ["thr_a"]


@pytest.mark.asyncio
async def test_patch_thread_sets_folder() -> None:
    thread_registry = MagicMock()
    thread_registry.get_thread.return_value = _thread_row("thr_a", folder="工作")
    server = _server_with_registry(thread_registry)

    body = RenameThreadBody(folder="工作")
    out = await history_mod.patch_thread("agt_1", "thr_a", body, user=_USER, server=server)

    thread_registry.set_folder.assert_called_once_with("thr_a", "工作")
    assert out["folder"] == "工作"


@pytest.mark.asyncio
async def test_patch_thread_clears_folder_with_null() -> None:
    thread_registry = MagicMock()
    thread_registry.get_thread.return_value = _thread_row("thr_a")
    server = _server_with_registry(thread_registry)

    body = RenameThreadBody(folder=None)
    out = await history_mod.patch_thread("agt_1", "thr_a", body, user=_USER, server=server)

    thread_registry.set_folder.assert_called_once_with("thr_a", None)
    assert out["folder"] is None


@pytest.mark.asyncio
async def test_patch_thread_sets_tags() -> None:
    thread_registry = MagicMock()
    thread_registry.get_thread.return_value = _thread_row("thr_a", tags=("重要",))
    server = _server_with_registry(thread_registry)

    body = RenameThreadBody(tags=["重要", "日报"])
    out = await history_mod.patch_thread("agt_1", "thr_a", body, user=_USER, server=server)

    thread_registry.set_tags.assert_called_once_with("thr_a", ["重要", "日报"])
    assert out["tags"] == ["重要"]


@pytest.mark.asyncio
async def test_patch_thread_empty_body_keeps_existing_values() -> None:
    thread_registry = MagicMock()
    thread_registry.get_thread.return_value = _thread_row("thr_a", folder="工作", tags=("重要",))
    server = _server_with_registry(thread_registry)

    body = RenameThreadBody()
    out = await history_mod.patch_thread("agt_1", "thr_a", body, user=_USER, server=server)

    thread_registry.set_folder.assert_not_called()
    thread_registry.set_tags.assert_not_called()
    assert out["folder"] == "工作"
    assert out["tags"] == ["重要"]


@pytest.mark.asyncio
async def test_list_thread_folders_returns_distinct_names() -> None:
    thread_registry = MagicMock()
    thread_registry.list_folders.return_value = ["学习", "工作"]
    server = _server_with_registry(thread_registry)

    out = await history_mod.list_thread_folders("agt_1", user=_USER, server=server)

    thread_registry.list_folders.assert_called_once_with(agent_id="agt_1", user_id=1)
    assert out == {"folders": ["学习", "工作"]}


@pytest.mark.asyncio
async def test_list_thread_tags_returns_distinct_tags() -> None:
    thread_registry = MagicMock()
    thread_registry.list_tags.return_value = ["天气", "学习"]
    server = _server_with_registry(thread_registry)

    out = await history_mod.list_thread_tags("agt_1", user=_USER, server=server)

    thread_registry.list_tags.assert_called_once_with(agent_id="agt_1", user_id=1)
    assert out == {"tags": ["天气", "学习"]}
