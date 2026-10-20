"""Unit tests for XiaoYi channel."""

from __future__ import annotations

from octop_gateway.channels.xiaoyi import XiaoyiChannel, XiaoyiConfig
from octop_gateway.models import InboundMessage, MessageEvent, TextContent


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


class TestXiaoyiChannelUnit:
    def test_config_display_flags(self) -> None:
        config = XiaoyiConfig(ak="ak", sk="sk", agent_id="agent1", show_thinking=True)
        ch = XiaoyiChannel(processor=_noop_processor, config=config)
        assert ch.channel_type == "xiaoyi"
        assert ch.constraints.show_thinking is True

    def test_parse_inbound(self) -> None:
        ch = XiaoyiChannel(
            processor=_noop_processor,
            config=XiaoyiConfig(ak="ak", sk="sk", agent_id="agent1"),
        )
        msg = ch.parse_inbound(
            {
                "session_id": "sess-001",
                "task_id": "task-001",
                "message_id": "msg-001",
                "content": [TextContent(text="hello xiaoyi")],
            }
        )
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "sess-001"
        assert msg.metadata["task_id"] == "task-001"
        assert msg.content[0].text == "hello xiaoyi"  # type: ignore[union-attr]

    def test_deduplication(self) -> None:
        ch = XiaoyiChannel(
            processor=_noop_processor,
            config=XiaoyiConfig(ak="ak", sk="sk", agent_id="agent1"),
        )
        assert ch._is_duplicate("msg-1") is False
        assert ch._is_duplicate("msg-1") is True
