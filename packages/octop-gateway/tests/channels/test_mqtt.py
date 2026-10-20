"""Unit tests for MQTT channel."""

from __future__ import annotations

from octop_gateway.channels.mqtt import MQTTChannel, MQTTConfig
from octop_gateway.models import InboundMessage, MessageEvent


async def _noop_processor(msg: InboundMessage):
    yield MessageEvent.completed()


class TestMQTTChannelUnit:
    def test_config_display_flags(self) -> None:
        config = MQTTConfig(show_thinking=True, show_tool_hints=False)
        ch = MQTTChannel(processor=_noop_processor, config=config)
        assert ch.constraints.show_thinking is True
        assert ch.constraints.show_tool_hints is False

    def test_parse_inbound_text(self) -> None:
        ch = MQTTChannel(processor=_noop_processor, config=MQTTConfig(host="broker"))
        msg = ch.parse_inbound(
            {
                "client_id": "robot-01",
                "text": "hello mqtt",
                "topic": "devices/robot-01/in",
            }
        )
        assert msg.channel_type == "mqtt"
        assert msg.channel_subject is not None
        assert msg.channel_subject.subject_id == "robot-01"
        assert msg.content[0].text == "hello mqtt"  # type: ignore[union-attr]
        assert msg.metadata["client_id"] == "robot-01"
