from __future__ import annotations

import pytest
from harness_gateway.models import (
    ChannelSubject,
    FileContent,
    GroupContext,
    GroupContextMessage,
    InboundMessage,
    TextContent,
)

from octop.infra.gateway.process.harness_request import build_content_from_message


@pytest.mark.asyncio
async def test_group_context_is_rendered_as_background_inside_current_turn() -> None:
    msg = InboundMessage(
        channel_id="qq-1",
        channel_type="qq",
        channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
        content=[TextContent(text="when is deployment?")],
        metadata={"sender_id": "bob-id", "sender_name": "Bob"},
        group_context=GroupContext(
            conversation_id="group-1",
            visibility="mention_recent",
            activation="mention",
            messages=[
                GroupContextMessage(
                    message_id="m1",
                    sender_id="alice-id",
                    sender_name="Alice",
                    text="deployment is at 3pm",
                    timestamp=1,
                )
            ],
        ),
    )

    content = await build_content_from_message(msg)

    assert isinstance(content, str)
    assert "[Group context | reference only]" in content
    assert "[Alice] deployment is at 3pm" in content
    assert "[Current group message | reply to this]" in content
    assert content.endswith("[Bob] when is deployment?")
    assert "alice-id" not in content
    assert "bob-id" not in content


@pytest.mark.asyncio
async def test_mention_only_still_attributes_the_current_group_sender() -> None:
    msg = InboundMessage(
        channel_id="qq-1",
        channel_type="qq",
        channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
        content=[TextContent(text="hello")],
        metadata={"sender_id": "bob-id", "sender_name": "Bob"},
        group_context=GroupContext(
            conversation_id="group-1",
            visibility="mention_only",
            activation="mention",
        ),
    )

    content = await build_content_from_message(msg)

    assert isinstance(content, str)
    assert "Group context" not in content
    assert content == "[Current group message | reply to this]\n[Bob] hello"


@pytest.mark.asyncio
async def test_group_context_renders_passive_file_as_agent_path_hint() -> None:
    msg = InboundMessage(
        channel_id="qq-1",
        channel_type="qq",
        channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
        content=[TextContent(text="summarize the PDF")],
        metadata={"sender_id": "bob-id", "sender_name": "Bob"},
        group_context=GroupContext(
            conversation_id="group-1",
            visibility="mention_recent",
            activation="mention",
            messages=[
                GroupContextMessage(
                    message_id="m-file",
                    sender_id="alice-id",
                    sender_name="Alice",
                    text="",
                    content=[
                        FileContent(
                            filename="report.pdf",
                            mime_type="application/pdf",
                            local_path="qq/channel/report.pdf",
                        )
                    ],
                )
            ],
        ),
    )

    content = await build_content_from_message(msg)

    assert isinstance(content, str)
    assert "[Alice]" in content
    assert "report.pdf" in content
    assert "inbound/qq/channel/report.pdf" in content
    assert "alice-id" not in content


@pytest.mark.asyncio
async def test_group_context_uses_anonymous_labels_instead_of_raw_ids() -> None:
    msg = InboundMessage(
        channel_id="qq-1",
        channel_type="qq",
        channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
        content=[TextContent(text="你怎么看？")],
        metadata={"sender_id": "BD55218924C37DB7472F18A7FC8F59DA"},
        group_context=GroupContext(
            conversation_id="group-1",
            visibility="mention_recent",
            activation="mention",
            messages=[
                GroupContextMessage(
                    sender_id="1468FCD7983CD809F783D645F791ECF2",
                    text="这是之前的消息",
                )
            ],
        ),
    )

    content = await build_content_from_message(msg, locale="zh")

    assert isinstance(content, str)
    assert "【群聊背景｜仅供参考】" in content
    assert "[群成员1] 这是之前的消息" in content
    assert "【当前群消息｜请回复这条消息】" in content
    assert "[群成员2] 你怎么看？" in content
    assert "1468FCD" not in content
    assert "BD552189" not in content
