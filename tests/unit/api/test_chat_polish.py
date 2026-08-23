"""Unit tests for chat polish and history helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from octop.api.routers.chat.serialize import (
    _entry_matches_thread,
    _is_offload_placeholder_block,
    _merge_adjacent_messages,
    _serialize_history_message,
    _strip_image_only_text_blocks,
    _strip_thinking,
    _ts_to_ms,
)
from octop.infra.utils.llm_text import llm_text_content as _llm_text_content


def test_serialize_history_message_includes_thinking_and_tools() -> None:
    user = _serialize_history_message(HumanMessage(content="hello"))
    assert user is not None
    assert user["role"] == "user"
    assert user["content"] == [{"type": "text", "text": "hello"}]

    user_with_ctx = _serialize_history_message(
        HumanMessage(
            content="hello",
            additional_kwargs={
                "octop_composer_context": {
                    "skills": ["docx"],
                    "model": "openai/gpt-4o",
                },
            },
        )
    )
    assert user_with_ctx is not None
    assert user_with_ctx.get("composer_context") == {
        "skills": ["docx"],
        "model": "openai/gpt-4o",
    }

    thinking_ai = _serialize_history_message(
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "plan"},
                {"type": "text", "text": "hi"},
            ]
        )
    )
    assert thinking_ai is not None
    assert thinking_ai["content"][0] == {"type": "thinking", "thinking": "plan"}

    tool_call_ai = _serialize_history_message(
        AIMessage(
            content="",
            tool_calls=[
                {"name": "search", "args": {"q": "x"}, "id": "call_1", "type": "tool_call"},
            ],
        )
    )
    assert tool_call_ai is not None
    assert tool_call_ai["content"][0]["type"] == "tool_use"
    assert tool_call_ai["content"][0]["name"] == "search"

    tool_result = _serialize_history_message(
        ToolMessage(content="found", tool_call_id="call_1", name="search")
    )
    assert tool_result is not None
    assert tool_result["role"] == "tool"
    assert tool_result["content"][0]["type"] == "tool_result"
    assert tool_result["content"][0]["output"] == "found"


def test_split_string_thinking_parses_redacted_block() -> None:
    from octop.api.routers.chat.serialize import _split_string_thinking

    blocks = _split_string_thinking("<think>internal</think>Visible answer")
    assert blocks[0] == {"type": "thinking", "thinking": "internal"}
    assert blocks[1] == {"type": "text", "text": "Visible answer"}


def test_serialize_history_message_splits_redacted_thinking() -> None:
    ai = _serialize_history_message(AIMessage(content="<think>internal</think>Visible"))
    assert ai is not None
    assert ai["content"][0] == {"type": "thinking", "thinking": "internal"}
    assert ai["content"][1] == {"type": "text", "text": "Visible"}


def test_strip_thinking_removes_redacted_block() -> None:
    raw = "<think>internal</think>\nPolished prompt"
    assert _strip_thinking(raw) == "Polished prompt"


def test_llm_text_content_strips_thinking_from_string_message() -> None:
    class Msg:
        content = "<think>plan</think>Final text"

    assert _llm_text_content(Msg()) == "Final text"


def test_llm_text_content_skips_thinking_blocks() -> None:
    class Msg:
        content = [
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": "Visible prompt"},
        ]

    assert _llm_text_content(Msg()) == "Visible prompt"


def test_merge_adjacent_messages_keeps_user_turns_separate() -> None:
    prompt = "每日星座提醒"
    merged = _merge_adjacent_messages(
        [
            {"role": "user", "content": prompt},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "reply one"},
            {"role": "assistant", "content": "reply two"},
        ]
    )
    assert len(merged) == 3
    assert merged[0]["role"] == "user" and merged[0]["content"] == prompt
    assert merged[1]["role"] == "user" and merged[1]["content"] == prompt
    assert merged[2]["role"] == "assistant"
    assert "reply one" in merged[2]["content"]
    assert "reply two" in merged[2]["content"]


def test_entry_matches_thread_by_thread_id() -> None:
    assert _entry_matches_thread(
        {"thread_id": "thr_a", "role": "user", "content": "x"},
        thread_id="thr_a",
        created_at=0,
        last_active=0,
    )
    assert not _entry_matches_thread(
        {"thread_id": "thr_b", "role": "user", "content": "x"},
        thread_id="thr_a",
        created_at=0,
        last_active=0,
    )


def test_entry_matches_thread_does_not_match_by_prompt_title() -> None:
    prompt = "用户星座：双子座。请根据双子座今日运势"
    assert not _entry_matches_thread(
        {"role": "user", "content": prompt},
        thread_id="thr_new",
        created_at=1_000_000,
        last_active=1_000_100,
    )


def test_serialize_history_message_includes_checkpoint_timestamp() -> None:
    user = _serialize_history_message(
        HumanMessage(
            content="hello",
            additional_kwargs={"checkpoint_ts": 1_700_000_000_000},
        )
    )
    assert user is not None
    assert user["timestamp"] == 1_700_000_000_000


def test_serialize_history_message_includes_checkpoint_timestamp_for_tool() -> None:
    tool = _serialize_history_message(
        ToolMessage(
            content="found",
            tool_call_id="call_1",
            name="search",
            additional_kwargs={"checkpoint_ts": 1_700_000_000_123},
        )
    )
    assert tool is not None
    assert tool["timestamp"] == 1_700_000_000_123


def test_ts_to_ms_converts_seconds() -> None:
    assert _ts_to_ms(1_700_000_000.5) == 1_700_000_000_500


# ---------------------------------------------------------------------------
# Image-offload placeholder filtering on history serialization
# ---------------------------------------------------------------------------


_PLACEHOLDER_TEXT = (
    "[image offloaded: sha=06bdd82d592a "
    "path=C:\\Users\\me\\.octop\\agents\\DMQ318\\.media-cache/"
    "06bdd82d592a5cd6371ccdb2ed49d347a4ffb0fca4b80ea57e991f51522e178e.png "
    "size=173004B mime=image/png; use read_file to retrieve bytes]"
)


def test_is_offload_placeholder_block_matches_image_format() -> None:
    assert _is_offload_placeholder_block({"type": "text", "text": _PLACEHOLDER_TEXT})
    # Same shape, but a 12-char short sha and trailing "]".
    assert _is_offload_placeholder_block(
        {
            "type": "text",
            "text": "  [audio offloaded: sha=abcdef012345 path=/x.y size=1B mime=audio/mpeg; use read_file to retrieve bytes]  ",
        }
    )


def test_is_offload_placeholder_block_rejects_unrelated_text() -> None:
    assert not _is_offload_placeholder_block({"type": "text", "text": "hello"})
    assert not _is_offload_placeholder_block(
        {"type": "text", "text": "[image] some other bracket text"}
    )
    # Image block (not text) is not a placeholder.
    assert not _is_offload_placeholder_block(
        {"type": "image_url", "image_url": {"url": "data:..."}}
    )
    assert not _is_offload_placeholder_block("not a dict")


def test_serialize_history_message_drops_image_offload_placeholder_for_image_user() -> None:
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "用户发送了图片。"},
            {"type": "text", "text": _PLACEHOLDER_TEXT},
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "image.png",
                    "media_type": "image/png",
                    "kind": "image",
                    "workspace_path": "inbound/123_image.png",
                }
            ],
        },
    )
    user = SimpleNamespace(locale="zh")
    entry = _serialize_history_message(msg, user=user)
    assert entry is not None
    # Both the localized "User sent an image." sentinel and the offload
    # placeholder must be stripped — only the image (rendered from
    # inbound_attachments) is meaningful on the dashboard.
    assert entry["content"] == []
    # Attachments are still propagated for the frontend to render the image.
    assert entry["inbound_attachments"][0]["workspace_path"] == "inbound/123_image.png"


def test_serialize_history_message_keeps_user_caption_alongside_image_placeholder() -> None:
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "请帮我看看这张图"},
            {"type": "text", "text": _PLACEHOLDER_TEXT},
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "image.png",
                    "media_type": "image/png",
                    "kind": "image",
                    "workspace_path": "inbound/123_image.png",
                }
            ],
        },
    )
    user = SimpleNamespace(locale="zh")
    entry = _serialize_history_message(msg, user=user)
    assert entry is not None
    # Only the offload placeholder is dropped; the user-written caption
    # is preserved verbatim so the dashboard still shows it.
    assert entry["content"] == [{"type": "text", "text": "请帮我看看这张图"}]


def test_serialize_history_message_keeps_placeholder_when_no_image_attachment() -> None:
    """Without inbound_attachments, the placeholder is the only sign of media."""
    msg = HumanMessage(
        content=[{"type": "text", "text": _PLACEHOLDER_TEXT}],
    )
    # No additional_kwargs → no inbound_attachments → no filtering.
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="en"))
    assert entry is not None
    assert entry["content"] == [{"type": "text", "text": _PLACEHOLDER_TEXT}]


def test_serialize_history_message_drops_placeholder_for_en_locale() -> None:
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "User sent an image."},
            {"type": "text", "text": _PLACEHOLDER_TEXT},
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "image.png",
                    "media_type": "image/png",
                    "kind": "image",
                    "workspace_path": "inbound/123_image.png",
                }
            ],
        },
    )
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="en"))
    assert entry is not None
    assert entry["content"] == []


def test_strip_image_only_text_blocks_without_user_skips_zh_default() -> None:
    """Locale falls back to ``zh`` when no user is supplied."""
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "用户发送了图片。"},
            {"type": "text", "text": _PLACEHOLDER_TEXT},
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "image.png",
                    "media_type": "image/png",
                    "kind": "image",
                    "workspace_path": "inbound/x.png",
                }
            ],
        },
    )
    # Pass no user — caller signature is ``user=None`` default.
    entry = _serialize_history_message(msg)
    assert entry is not None
    assert entry["content"] == []


def test_strip_image_only_text_blocks_keeps_voice_caption() -> None:
    """Non-image attachments still strip LLM-only noise; keep the user caption."""
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "请听这段录音"},
            {"type": "text", "text": _PLACEHOLDER_TEXT},  # NOT real, but tests shape
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "voice.m4a",
                    "media_type": "audio/mp4",
                    "kind": "file",
                    "workspace_path": "inbound/voice.m4a",
                }
            ],
        },
    )
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    # Offload placeholders are LLM-facing only once inbound_attachments exists.
    assert entry["content"] == [{"type": "text", "text": "请听这段录音"}]


def test_serialize_history_message_drops_zip_path_hint() -> None:
    """Zip/file path hints must not appear as user-authored history text."""
    hint = (
        "[附件] report.zip\n"
        "工作区路径：/.octop/workspaces/JRK846/inbound/1_report.zip\n"
        "MIME：application/zip"
    )
    msg = HumanMessage(
        content=[{"type": "text", "text": f"请解压\n\n{hint}"}],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "report.zip",
                    "media_type": "application/zip",
                    "kind": "file",
                    "workspace_path": "inbound/1_report.zip",
                }
            ],
        },
    )
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    assert entry["content"] == [{"type": "text", "text": "请解压"}]
    assert entry["inbound_attachments"][0]["filename"] == "report.zip"


def test_serialize_history_message_drops_workspace_image_ref() -> None:
    """Path-only vision refs are history noise when inbound_attachments is set."""
    msg = HumanMessage(
        content=[
            {"type": "text", "text": "这是什么"},
            {
                "type": "image_url",
                "workspace_path": "inbound/1_shot.png",
                "mime_type": "image/png",
                "image_url": {"url": "workspace://inbound/1_shot.png"},
            },
        ],
        additional_kwargs={
            "octop_inbound_attachments": [
                {
                    "filename": "shot.png",
                    "media_type": "image/png",
                    "kind": "image",
                    "workspace_path": "inbound/1_shot.png",
                }
            ],
        },
    )
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    assert entry["content"] == [{"type": "text", "text": "这是什么"}]


def test_serialize_history_synthesizes_attachment_from_workspace_image_ref() -> None:
    """Even without inbound_attachments, path refs become thumbnails — not JSON text."""
    msg = HumanMessage(
        content=[
            {
                "type": "image_url",
                "workspace_path": "inbound/1787231393_baidu_map.png",
                "mime_type": "image/png",
                "image_url": {
                    "url": "workspace://inbound/1787231393_baidu_map.png",
                },
            }
        ],
    )
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    assert entry["content"] == []
    assert entry["inbound_attachments"] == [
        {
            "filename": "1787231393_baidu_map.png",
            "media_type": "image/png",
            "kind": "image",
            "workspace_path": "inbound/1787231393_baidu_map.png",
        }
    ]


def test_serialize_history_drops_dumped_image_ref_json_text() -> None:
    dumped = (
        '{"type": "image_url", "workspace_path": "inbound/1787231393_baidu_map.png", '
        '"mime_type": "image/png", '
        '"image_url": {"url": "workspace://inbound/1787231393_baidu_map.png"}}'
    )
    msg = HumanMessage(content=[{"type": "text", "text": dumped}])
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    assert entry["content"] == []
    assert entry["inbound_attachments"][0]["workspace_path"] == ("inbound/1787231393_baidu_map.png")


def test_serialize_history_splits_caption_from_stringified_image_ref() -> None:
    """Session JSONL joins caption + json.dumps(image_url) — must not show as text."""
    dumped = (
        '{"type": "image_url", "workspace_path": "inbound/1787277960_baidu_map.png", '
        '"mime_type": "image/png", '
        '"image_url": {"url": "workspace://inbound/1787277960_baidu_map.png"}}'
    )
    msg = HumanMessage(content=f"这图是啥\n{dumped}")
    entry = _serialize_history_message(msg, user=SimpleNamespace(locale="zh"))
    assert entry is not None
    assert entry["content"] == [{"type": "text", "text": "这图是啥"}]
    assert entry["inbound_attachments"] == [
        {
            "filename": "1787277960_baidu_map.png",
            "media_type": "image/png",
            "kind": "image",
            "workspace_path": "inbound/1787277960_baidu_map.png",
        }
    ]


def test_strip_image_only_text_blocks_directly() -> None:
    blocks = [
        {"type": "text", "text": "用户发送了图片。"},
        {"type": "text", "text": _PLACEHOLDER_TEXT},
        {"type": "text", "text": "你好"},
    ]
    out = _strip_image_only_text_blocks(blocks, locale="zh")
    assert out == [{"type": "text", "text": "你好"}]


@pytest.mark.asyncio
async def test_load_checkpoint_messages_falls_back_to_graph_state() -> None:
    from octop.api.routers.chat.serialize import _load_checkpoint_messages

    human = HumanMessage(content="fallback hello")

    class Harness:
        async def aget_history(self, thread_id: str, *, limit: int = 50) -> list[Any]:
            return []

        graph = MagicMock()
        graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"messages": [human]}),
        )

    msgs, _has_more = await _load_checkpoint_messages(Harness(), "thr_x", limit=10)
    assert len(msgs) == 1
    assert msgs[0].content == "fallback hello"
