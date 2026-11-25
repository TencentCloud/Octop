"""Public conversation share payload."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.api.routers.chat import share as share_mod
from octop.infra.errors import ErrorCode, OctopError


def test_public_messages_keep_tools_and_thinking() -> None:
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "see [notes](/api/agents/agt/workspace/secret.txt)"},
            ],
            "author": {
                "display_name": "Ada",
                "username": "ada",
                "user_id": 7,
                "avatar_icon": "staff",
                "avatar_url": "/api/users/7/avatar",
            },
            "timestamp": 10,
        },
        {
            "role": "assistant",
            "agent_id": "agt",
            "content": [
                {"type": "thinking", "thinking": "hidden"},
                {"type": "text", "text": "hi\n\n![shot](/api/uploads/x)"},
                {"type": "tool_use", "name": "bash", "input": {"cmd": "rm -rf"}},
            ],
            "usage": {"input_tokens": 3},
            "edited_files": ["secret.txt"],
        },
        {
            "role": "tool",
            "content": [{"type": "tool_result", "output": "secret output"}],
        },
    ]

    out = share_mod.public_conversation_messages(
        messages,
        speaker_faces={
            "agt": {
                "name": "Helper",
                "icon_url": "/experts/avatars/general-assistant.svg",
                "icon_name": "zap",
                "color": "#6366F1",
            }
        },
        default_agent_id="agt",
    )

    assert out[0] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "see notes"},
        ],
        "timestamp": 10,
        "author_name": "Ada",
        "author_avatar_icon": "staff",
    }
    assert out[1]["role"] == "assistant"
    assert out[1]["speaker_name"] == "Helper"
    assert out[1]["speaker_icon_url"] == "/experts/avatars/general-assistant.svg"
    assert out[1]["speaker_icon_name"] == "zap"
    assert out[1]["speaker_color"] == "#6366F1"
    assert [block["type"] for block in out[1]["content"]] == [
        "thinking",
        "text",
        "tool_use",
    ]
    assert out[1]["content"][0]["thinking"] == "hidden"
    assert out[1]["content"][1]["text"] == "hi"
    assert out[1]["content"][2]["name"] == "bash"
    assert out[1]["content"][2]["input"] == {"cmd": "rm -rf"}
    assert "usage" not in out[1]
    assert "edited_files" not in out[1]
    assert out[2] == {
        "role": "tool",
        "content": [{"type": "tool_result", "output": "secret output"}],
    }
    blob = str(out)
    assert "username" not in blob
    assert "user_id" not in blob
    assert "/api/" not in blob


@pytest.mark.asyncio
async def test_public_share_hides_internal_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    share = SimpleNamespace(
        share_id="a" * 24,
        thread_id="thr",
        agent_id="agt",
        created_by=7,
        created_at=1,
    )
    thread = SimpleNamespace(thread_id="thr", agent_id="agt", user_id=7, title="Weekly")
    server = MagicMock()
    server.services.thread_share_repo.get_active_by_token.return_value = share
    server.services.thread_repo.get.return_value = thread
    server.services.agent_repo.get.return_value = SimpleNamespace(
        name="Helper",
        icon_url="/experts/avatars/general-assistant.svg",
        icon_name="zap",
        color="#6366F1",
    )
    server.services.thread_message_repo.projection_status.return_value = "ready"
    server.config.default_timezone = "Asia/Shanghai"
    raw = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "author": {
                "display_name": "Ada",
                "username": "ada",
                "user_id": 7,
                "avatar_icon": "staff",
            },
        }
    ]
    monkeypatch.setattr(
        share_mod,
        "_load_projected_thread_messages",
        lambda *_args, **_kwargs: (raw, True),
    )

    out = await share_mod.get_public_share("a" * 24, server=server)

    assert out["title"] == "Weekly"
    assert out["agent_name"] == "Helper"
    assert out["timezone"] == "Asia/Shanghai"
    assert out["ready"] is True
    assert out["truncated"] is True
    assert out["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "author_name": "Ada",
            "author_avatar_icon": "staff",
        },
    ]
    assert "thread_id" not in out
    assert "user_id" not in str(out["messages"])


@pytest.mark.asyncio
async def test_missing_share_is_not_found() -> None:
    server = MagicMock()
    server.services.thread_share_repo.get_active_by_token.return_value = None
    with pytest.raises(OctopError) as raised:
        await share_mod.get_public_share("not-a-token", server=server)
    assert raised.value.code is ErrorCode.NOT_FOUND
    server.services.thread_share_repo.get_active_by_token.assert_not_called()


@pytest.mark.asyncio
async def test_create_reuses_the_live_link(monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(thread_id="thr", agent_id="agt", user_id=7)
    monkeypatch.setattr(share_mod, "_require_thread", lambda *_a, **_k: row)
    queued = MagicMock()
    monkeypatch.setattr(share_mod, "_queue_projection", queued)
    share = SimpleNamespace(share_id="tok" * 8, created_at=3)
    server = MagicMock()
    server.services.thread_share_repo.ensure.return_value = share
    user = SimpleNamespace(id=7)

    out = await share_mod.create_thread_share(
        "agt",
        "thr",
        body=None,
        user=user,
        server=server,
    )

    assert out == {"active": True, "share_id": share.share_id, "created_at": 3}
    server.services.thread_share_repo.rotate.assert_not_called()
    queued.assert_called_once()
