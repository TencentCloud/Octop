from __future__ import annotations

import pytest
from octop_gateway.models import (
    ChannelSubject,
    FileContent,
    GroupContext,
    GroupContextMessage,
    ImageContent,
    InboundMessage,
    TextContent,
)

from octop.infra.gateway.process.harness_request import build_content_from_message


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", ["telegram", "qq"])
@pytest.mark.parametrize("locale,label", [("en", "[Quoted message]"), ("zh", "[引用消息]")])
@pytest.mark.parametrize(
    "own_reply,explicit", [(False, False), (False, True), (True, False), (True, True)]
)
async def test_quoted_message_is_added_only_to_model_content(
    channel_type, locale, label, own_reply, explicit
):
    msg = InboundMessage(
        channel_id="tg",
        channel_type=channel_type,
        content=[TextContent(text="explain this")],
        metadata={
            "reply_to_text": "whole message",
            "reply_to_is_own_bot": own_reply,
            "reply_quote_text": "selection" if explicit else "",
        },
    )
    result = await build_content_from_message(msg, locale=locale)
    assert msg.text == "explain this"
    if channel_type == "qq" and own_reply and not explicit:
        assert result == "explain this"
    else:
        assert result.startswith(label)
        assert ("selection" if explicit else "whole message") in result
        assert result.endswith("explain this")


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


@pytest.mark.asyncio
async def test_group_context_promotes_recent_images_to_vision_without_path_hints(
    tmp_path,
) -> None:
    from deepagents.backends.local_shell import LocalShellBackend
    from octop_harness.backends.workspace import BackendWorkspace

    from octop.infra.gateway.media.ingress import AgentBackedMediaBackend

    workspace = BackendWorkspace(
        LocalShellBackend(root_dir=str(tmp_path), virtual_mode=False),
        str(tmp_path),
    )
    backend = AgentBackedMediaBackend(workspace)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    for idx in range(5):
        await backend.save(png_bytes, f"qq/group/img-{idx}.png")

    bg_msgs = [
        GroupContextMessage(
            message_id=f"m-{idx}",
            sender_id=f"u-{idx}",
            sender_name=f"Member{idx}",
            text="",
            content=[
                ImageContent(
                    local_path=f"qq/group/img-{idx}.png",
                    mime_type="image/png",
                )
            ],
        )
        for idx in range(5)
    ]
    msg = InboundMessage(
        channel_id="qq-1",
        channel_type="qq",
        channel_subject=ChannelSubject(subject_id="group-1", chat_type="group"),
        content=[
            TextContent(text="see latest"),
            ImageContent(local_path="qq/group/img-4.png", mime_type="image/png"),
        ],
        metadata={"sender_id": "bob-id", "sender_name": "Bob"},
        group_context=GroupContext(
            conversation_id="group-1",
            visibility="mention_recent",
            activation="mention",
            messages=bg_msgs,
        ),
    )

    content = await build_content_from_message(msg, media_backend=backend, locale="zh")

    assert isinstance(content, list)
    # 1 current image (img-4) + 3 most recent unique background images (img-1, img-2, img-3) = 4 max.
    image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image_url"]
    assert [b["workspace_path"] for b in image_blocks] == [
        "inbound/qq/group/img-4.png",
        "inbound/qq/group/img-1.png",
        "inbound/qq/group/img-2.png",
        "inbound/qq/group/img-3.png",
    ]
    text_block = content[0]["text"]
    assert "[Member1] [图片]" in text_block
    assert "[Member2] [图片]" in text_block
    assert "[Member3] [图片]" in text_block
    assert "[Member4] [图片]" in text_block
    # Promoted images must not expose raw inbound paths; excess img-0 retains path hint.
    assert "inbound/qq/group/img-3.png" not in text_block
    assert "inbound/qq/group/img-0.png" in text_block
    # Original GroupContextMessage must not be mutated in-place.
    assert len(msg.group_context.messages[1].content) == 1
    assert isinstance(msg.group_context.messages[1].content[0], ImageContent)
