"""BridgeSession JSON encoding must tolerate LangChain message objects."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from octop.infra.bridge.transport import BridgeSession, bridge_json_default


@pytest.mark.asyncio
async def test_send_json_serializes_human_message() -> None:
    sent: list[str] = []

    async def capture(text: str) -> None:
        sent.append(text)

    sess = BridgeSession(connection_id="c1", send_text=capture)
    await sess.send_json(
        {
            "type": "turn.chunk",
            "frame": {
                "type": "messages",
                "messages": [HumanMessage(content="hi"), AIMessage(content="yo")],
            },
        }
    )
    assert len(sent) == 1
    payload = json.loads(sent[0])
    assert payload["type"] == "turn.chunk"
    msgs = payload["frame"]["messages"]
    assert isinstance(msgs, list) and len(msgs) == 2
    assert msgs[0]["content"] == "hi"
    assert msgs[1]["content"] == "yo"


@pytest.mark.asyncio
async def test_close_frame_records_deleted_reason() -> None:
    async def noop(_text: str) -> None:
        return None

    sess = BridgeSession(connection_id="c1", send_text=noop)
    await sess.handle_message(json.dumps({"type": "close", "reason": "deleted"}))
    assert sess.close_reason == "deleted"
    assert sess.closed is True


def test_bridge_json_default_falls_back_to_repr() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    assert bridge_json_default(Weird()) == "<weird>"
