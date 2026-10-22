"""Material choices bind actual MCP IDs; source writes require a fresh complete read."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import types

from octop.infra.connectors.open_design_console import OpenDesignConsole
from octop.infra.errors import ErrorCode, OctopError


@pytest.fixture
def console() -> Any:
    settings: dict[str, str] = {}
    repos = SimpleNamespace(
        settings_repo=SimpleNamespace(
            get=lambda key: settings.get(key), set=lambda key, value: settings.update({key: value})
        ),
        open_design_task_repo=SimpleNamespace(active_project=lambda *args: []),
    )
    runtime = SimpleNamespace(
        tasks=SimpleNamespace(
            list_authorized=AsyncMock(return_value=[{"instance_id": "i", "project": "p"}])
        )
    )
    service = SimpleNamespace(
        list_user_instances=lambda *args, **kwargs: [
            SimpleNamespace(instance_id="i", kind="open-design")
        ]
    )
    return OpenDesignConsole(runtime, service, repos)


def client_stub(*, source: str = "original", truncated: bool = False) -> Any:
    state = {"source": source}

    async def call(name: str, args: dict[str, Any]) -> Any:
        if name == "get_file":
            blocks = (
                [
                    types.TextContent(
                        type="text",
                        text="[od:file-window offset=0 returnedLines=2001 totalLines=3000]",
                    )
                ]
                if truncated
                else []
            )
            return types.CallToolResult(
                content=[*blocks, types.TextContent(type="text", text=state["source"])]
            )
        if name == "write_file":
            state["source"] = args["content"]
            payload: dict[str, Any] = {}
        elif name == "get_project":
            payload = {"previewUrl": "https://example.com/preview"}
        else:
            payload = {"agents": [{"id": "opencode", "models": ["provider/model"]}]}
        return types.CallToolResult(content=[], structuredContent=payload)

    pages = [
        SimpleNamespace(
            resources=[SimpleNamespace(uri="od://skills/template%3Ax/SKILL.md")], nextCursor="next"
        ),
        SimpleNamespace(
            resources=[SimpleNamespace(uri="od://design-systems/brand/DESIGN.md")], nextCursor=None
        ),
    ]
    return SimpleNamespace(
        call_tool=AsyncMock(side_effect=call),
        list_resources=AsyncMock(side_effect=lambda cursor=None: pages[1 if cursor else 0]),
    )


def use_client(console: Any, client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def context(*args: Any) -> Any:
        yield client

    monkeypatch.setattr(console, "client", context)


@pytest.mark.asyncio
async def test_selection_revalidated_and_bound_to_actual_generation(
    console: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_stub()
    use_client(console, client, monkeypatch)
    choices = {
        "agent": "opencode",
        "model": "provider/model",
        "skills": ["template:x"],
        "designSystem": "brand",
    }
    await console.save_selection(1, "i", "", "", choices)
    arguments: dict[str, Any] = {"skills": ["template:x"], "agent": "inferred"}
    await console.apply_selection(client, 1, "i", "a", "t", "start_run", arguments)
    assert arguments == {"agent": "opencode", "model": "provider/model", "skills": ["template:x"]}
    project: dict[str, Any] = {}
    await console.apply_selection(client, 1, "i", "a", "t", "create_project", project)
    assert project == {"designSystem": "brand", "skill": "template:x"}
    # An explicit empty conversation choice disables personal defaults.
    await console.save_selection(1, "i", "a", "t", {"skills": []})
    arguments = {}
    await console.apply_selection(client, 1, "i", "a", "t", "start_run", arguments)
    assert arguments == {}
    client.list_resources.assert_any_await("next")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "choices",
    [
        {"agent": "guessed"},
        {"model": "provider/model"},
        {"agent": "opencode", "model": "unknown"},
        {"skills": ["missing"]},
        {"designSystem": "missing"},
    ],
)
async def test_unknown_choices_rejected(console: Any, choices: dict[str, Any]) -> None:
    with pytest.raises(OctopError) as error:
        await console.validate_selection(client_stub(), choices)
    assert error.value.code == ErrorCode.OPEN_DESIGN_SELECTION_INVALID


@pytest.mark.parametrize(
    "path", ["", ".", "../secret", "/secret", "C:/secret", "a\\b", "a/../b", "a\x00b"]
)
def test_project_relative_paths_only(path: str) -> None:
    with pytest.raises(OctopError):
        OpenDesignConsole.file_path(path)


@pytest.mark.asyncio
async def test_edit_rechecks_digest_verifies_write_and_preview(
    console: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_stub()
    use_client(console, client, monkeypatch)
    before = await console.file(1, "i", "a", "t", "p", "index.html")
    result = await console.edit(
        1, "i", "a", "t", "p", "index.html", before["digest"], "changed", "en"
    )
    assert result["content"] == "changed" and result["previewUrl"] == "https://example.com/preview"
    assert [call.args[0] for call in client.call_tool.await_args_list] == [
        "get_file",
        "get_file",
        "write_file",
        "get_file",
        "get_project",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("truncated", [True, False])
async def test_stale_or_partial_read_never_writes(
    console: Any, monkeypatch: pytest.MonkeyPatch, truncated: bool
) -> None:
    client = client_stub(source="new", truncated=truncated)
    use_client(console, client, monkeypatch)
    with pytest.raises(OctopError) as error:
        await console.edit(
            1, "i", "a", "t", "p", "index.html", hashlib.sha256(b"old").hexdigest(), "edited", "en"
        )
    assert error.value.code == ErrorCode.OPEN_DESIGN_FILE_CONFLICT
    assert all(call.args[0] != "write_file" for call in client.call_tool.await_args_list)


@pytest.mark.asyncio
async def test_active_task_and_foreign_project_blocked(
    console: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_stub()
    use_client(console, client, monkeypatch)
    console.repos.open_design_task_repo.active_project = lambda *args: [{"status": "running"}]
    with pytest.raises(OctopError) as error:
        await console.edit(1, "i", "a", "t", "p", "index.html", "digest", "edited", "en")
    assert error.value.code == ErrorCode.OPEN_DESIGN_TASK_RUNNING
    with pytest.raises(OctopError):
        await console.file(1, "i", "a", "t", "foreign", "index.html")
    client.call_tool.assert_not_awaited()
