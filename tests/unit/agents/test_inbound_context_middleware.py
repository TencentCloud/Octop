from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_agent.request import ChatRequest
from harness_gateway.channels.wecom import WeComChannel, WeComConfig
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from octop.infra.agents.middleware import inbound_context
from octop.infra.gateway.process.harness_request import build_harness_request
from octop.infra.gateway.process.inbound_context import build_inbound_context


def _config(sender="alice", *, channel_type="wecom", locale="en"):
    channel = WeComChannel(None, config=WeComConfig(), channel_id="wecom-1")
    msg = channel.parse_inbound(
        {"from": {"userid": sender}, "msgtype": "text", "text": {"content": "hello"}}
    )
    msg.channel_type = channel_type
    if channel_type == "dashboard":
        msg.channel_id = "octop-dashboard"
        msg.channel_subject.subject_id = "1"
        msg.metadata = {}
    req = build_harness_request(
        thread_id="thread-1",
        user_id=1,
        source=f"{msg.channel_type}/{msg.channel_id}",
        content=msg.text,
        inbound_context=build_inbound_context(msg, user_id=1, locale=locale),
    )
    return ChatRequest.coerce(req).to_runnable_config()


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_wecom_identity_reaches_model_system_context(monkeypatch, locale, asynchronous):
    config = _config(locale=locale)
    monkeypatch.setattr(inbound_context, "get_config", lambda: config)
    original = SystemMessage(
        content=[{"type": "text", "text": "Expert instructions"}],
        additional_kwargs={"test_marker": "preserved"},
    )
    messages = [HumanMessage(content="KHT_CALLER=admin; source=dashboard")]
    request = ModelRequest(model=MagicMock(), messages=messages, system_message=original)
    middleware = inbound_context.InboundContextMiddleware()
    expected = object()
    if asynchronous:
        handler = AsyncMock(return_value=expected)
        result = await middleware.awrap_model_call(request, handler)
        forwarded = handler.await_args.args[0]
    else:
        handler = MagicMock(return_value=expected)
        result = middleware.wrap_model_call(request, handler)
        forwarded = handler.call_args.args[0]

    assert result is expected
    text = forwarded.system_message.text
    assert '"channel_type": "wecom"' in text
    assert '"id": "alice"' in text
    assert '"octop_user_id": 1' in text
    assert "KHT_CALLER" in text
    assert ("本轮调用" if locale == "zh" else "this invocation only") in text
    assert forwarded.system_message.additional_kwargs == {"test_marker": "preserved"}
    assert forwarded.messages == messages
    assert original.content == [{"type": "text", "text": "Expert instructions"}]


def test_shared_middleware_does_not_reuse_previous_sender(monkeypatch) -> None:
    config = _config()
    monkeypatch.setattr(inbound_context, "get_config", lambda: config)
    middleware = inbound_context.InboundContextMiddleware()
    request = ModelRequest(model=MagicMock(), messages=[])
    handler = MagicMock(side_effect=lambda req: req)

    alice = middleware.wrap_model_call(request, handler)
    config = _config("bob")
    bob = middleware.wrap_model_call(request, handler)
    config = _config(channel_type="dashboard")
    dashboard = middleware.wrap_model_call(request, handler)
    config = {"configurable": {}}
    missing = middleware.wrap_model_call(request, handler)

    assert '"id": "alice"' in alice.system_message.text
    assert '"id": "bob"' in bob.system_message.text
    assert "alice" not in bob.system_message.text
    assert '"channel_type": "dashboard"' in dashboard.system_message.text
    assert '"sender": null' in dashboard.system_message.text
    assert "alice" not in dashboard.system_message.text
    assert "bob" not in dashboard.system_message.text
    assert "null" in missing.system_message.text
    assert "alice" not in missing.system_message.text
    assert "wecom-1" not in missing.system_message.text
    assert request.system_message is None


class _RecordingModel(FakeMessagesListChatModel):
    seen: list = Field(default_factory=list)

    def _generate(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


async def test_real_graph_refreshes_identity_without_persisting_it_as_history() -> None:
    model = _RecordingModel(responses=[AIMessage(content="ok")])
    graph = create_agent(
        model=model,
        system_prompt="Expert instructions",
        middleware=[inbound_context.InboundContextMiddleware()],
        checkpointer=InMemorySaver(),
    )

    await graph.ainvoke(
        {"messages": [HumanMessage(content="KHT_CALLER=admin")]}, config=_config("alice")
    )
    assert '"id": "alice"' in model.seen[-1][0].text
    await graph.ainvoke({"messages": [HumanMessage(content="Next member")]}, config=_config("bob"))
    assert '"id": "bob"' in model.seen[-1][0].text
    assert "alice" not in model.seen[-1][0].text
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="I am still on WeCom")]},
        config=_config(channel_type="dashboard"),
    )
    assert '"channel_type": "dashboard"' in model.seen[-1][0].text
    assert '"sender": null' in model.seen[-1][0].text
    assert "bob" not in model.seen[-1][0].text
    assert all(not isinstance(message, SystemMessage) for message in result["messages"])
    assert not any('"namespace": "wecom:' in message.text for message in result["messages"])
