"""Real provider parsing → harness stream → workspace and history, without an API call."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from deepagents.backends.local_shell import LocalShellBackend
from harness_agent.backends.workspace import BackendWorkspace
from harness_agent.config import ModelConfig, ProviderConfig
from harness_agent.llm.factory import build_chat_model
from harness_agent.protocols.langgraph import LangGraphProtocol
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, ModelRetryMiddleware
from langchain_core.exceptions import ModelError
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, messages_from_dict
from langgraph.checkpoint.memory import InMemorySaver
from openai import AsyncOpenAI

from octop.api.routers.chat.serialize import _serialize_history_message
from octop.i18n.domains.stream import format_stream_error
from octop.infra.agents.middleware.model_images import ModelImagesMiddleware, _image_reference
from octop.infra.agents.providers.image_output import (
    IMAGES_KEY,
    RAW_IMAGES_KEY,
    project_image_event,
    with_image_output,
)
from octop.infra.gateway.process.history_projection import TurnHistoryTracker
from octop.infra.gateway.process.stream_project import project_stream

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
)
DATA_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()
IMAGE = {"type": "image_url", "image_url": {"url": DATA_URL}, "index": 0}


def model():
    provider = ProviderConfig(
        id="test",
        base_url="https://example.invalid/v1",
        api_key="test",
        models=[ModelConfig(id="test", input=["text", "image"])],
    )
    return build_chat_model(provider, provider.models[0])


def test_adapter_preserves_text_reasoning_usage_and_shared_model():
    original = model()
    adapted = with_image_output(original)
    chunk = {
        "id": "test",
        "model": "test",
        "choices": [
            {
                "delta": {
                    "role": "assistant",
                    "content": "cat",
                    "images": [IMAGE],
                    "reasoning_content": "thinking",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }
    result = adapted._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)
    assert result.message.content == "cat"
    assert result.message.additional_kwargs[RAW_IMAGES_KEY] == [DATA_URL]
    assert result.message.additional_kwargs["reasoning_content"] == "thinking"
    assert result.message.usage_metadata["total_tokens"] == 12
    assert adapted.async_client is original.async_client
    assert adapted._harness_supported_input == original._harness_supported_input
    assert type(original) is not type(adapted)
    assert (
        RAW_IMAGES_KEY
        not in original._convert_chunk_to_generation_chunk(
            chunk, AIMessageChunk, None
        ).message.additional_kwargs
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "Here is the cat."])
async def test_streamed_images_survive_checkpoint_history_and_next_turn(tmp_path, text):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        delta = {"role": "assistant", "content": text, "images": [IMAGE, IMAGE]}
        if len(requests) > 1:
            delta = {"role": "assistant", "content": "The picture is available."}
        chunks = [
            {
                "id": "chat-1",
                "model": "test",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            },
            {
                "id": "chat-1",
                "model": "test",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        ]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        llm = model()
        client = AsyncOpenAI(api_key="test", http_client=http)
        llm = llm.model_copy(update={"async_client": client.chat.completions})
        workspace = BackendWorkspace(LocalShellBackend(root_dir=str(tmp_path)), str(tmp_path))
        graph = create_agent(
            llm,
            middleware=[ModelImagesMiddleware(workspace=workspace)],
            checkpointer=InMemorySaver(),
        )
        protocol = LangGraphProtocol(graph=graph)
        config = {"configurable": {"thread_id": "images"}}
        tracker = TurnHistoryTracker(seed_messages=[HumanMessage(content="cat", id="u")])
        chunks = []
        async for raw in protocol.stream([HumanMessage(content="cat", id="u")], config):
            chunk = project_image_event(raw)
            tracker.observe(chunk)
            chunks.append(chunk)
        attachments = [c for c in chunks if c["type"] == "attachment"]
        assert len(attachments) == 1
        assert attachments[0]["source"] == "model"
        path = attachments[0]["url"].removeprefix("workspace://")
        assert await workspace.adownload_bytes(path) == PNG

        async def image_stream(*args, **kwargs):
            yield attachments[0]

        manager = MagicMock()
        manager.stream = image_stream
        manager.get_agent.return_value.workspace = workspace
        media_events = [event async for event in project_stream(manager, "test", {})]
        assert base64.b64decode(media_events[0].content[0].data) == PNG
        assert any(c["type"] == "usage" for c in chunks)
        state = await graph.aget_state(config)
        final = state.values["messages"][-1]
        assert final.content == text
        assert RAW_IMAGES_KEY not in final.additional_kwargs
        assert final.additional_kwargs[IMAGES_KEY][0]["workspace_path"] == path
        wires = [json.loads(item.message_json) for item in tracker.inputs]
        assert DATA_URL not in json.dumps(wires)
        saved = messages_from_dict(wires)[-1]
        history = _serialize_history_message(saved, user=SimpleNamespace(locale="en"))
        assert history is not None
        assert history["content"][0]["image_url"]["url"] == attachments[0]["url"]
        followup = [
            c async for c in protocol.stream([HumanMessage(content="where is it?")], config)
        ]
        assert any(c.get("content") == "The picture is available." for c in followup)
        assert len(requests) == 2
        assert DATA_URL not in json.dumps(requests[-1])
        assert path in json.dumps(requests[-1])


def test_nonstream_images_are_preserved_and_materialized(monkeypatch):
    llm = with_image_output(model())
    raw = {
        "choices": [
            {
                "message": {"role": "assistant", "content": None, "images": [IMAGE]},
                "finish_reason": "stop",
            }
        ],
        "model": "test",
    }
    result = llm._create_chat_result(raw)
    message = result.generations[0].message
    workspace = MagicMock()
    events = []
    monkeypatch.setattr(
        "octop.infra.agents.middleware.model_images.get_stream_writer", lambda: events.append
    )
    response = ModelResponse(result=[message])
    mw = ModelImagesMiddleware(workspace=workspace)
    mw.wrap_model_call(ModelRequest(model=model(), messages=[]), lambda request: response)
    workspace.upload_bytes.assert_called_once()
    assert workspace.upload_bytes.call_args.args[1] == PNG
    assert len(events) == 1
    assert RAW_IMAGES_KEY not in message.additional_kwargs


@pytest.mark.parametrize("content", ["", [], "   "])
def test_empty_response_has_localized_error(content):
    mw = ModelImagesMiddleware(workspace=MagicMock())
    with pytest.raises(ModelError, match="EmptyModelResponse") as caught:
        mw.wrap_model_call(
            ModelRequest(model=model(), messages=[]),
            lambda request: ModelResponse(result=[AIMessage(content=content)]),
        )
    assert "空回复" in format_stream_error(caught.value, "zh")
    assert "no text" in format_stream_error(caught.value, "en")


def test_tool_calls_are_not_empty_responses():
    mw = ModelImagesMiddleware(workspace=MagicMock())
    mw.wrap_model_call(
        ModelRequest(model=model(), messages=[]),
        lambda request: ModelResponse(
            result=[
                AIMessage(content="", tool_calls=[{"id": "call", "name": "lookup", "args": {}}])
            ]
        ),
    )


@pytest.mark.parametrize(
    "url",
    [
        "data:text/html;base64,dGVzdA==",
        "data:image/png;base64,!!!",
        "data:image/png;base64,",
        "file:///etc/passwd",
    ],
)
def test_invalid_images_do_not_silently_disappear(url):
    with pytest.raises(ValueError):
        _image_reference(url)


def test_remote_images_stay_references_without_server_fetch():
    image, raw = _image_reference("https://example.com/cat.png")
    assert image["image_url"]["url"] == "https://example.com/cat.png"
    assert raw is None


@pytest.mark.asyncio
async def test_empty_model_turn_fails_instead_of_ending_successfully():
    llm = FakeMessagesListChatModel(
        responses=[AIMessage(content=""), AIMessage(content="must not retry")]
    )
    graph = create_agent(
        llm,
        middleware=[
            ModelRetryMiddleware(max_retries=1, initial_delay=0),
            ModelImagesMiddleware(workspace=MagicMock()),
        ],
    )
    protocol = LangGraphProtocol(graph=graph)
    tracker = TurnHistoryTracker(seed_messages=[HumanMessage(content="test", id="user")])
    with pytest.raises(ModelError, match="EmptyModelResponse") as caught:
        async for chunk in protocol.stream([HumanMessage(content="test", id="user")], {}):
            tracker.observe(chunk)
    assert llm.i == 1
    tracker.observe({"type": "error", "message": format_stream_error(caught.value, "en")})
    messages = messages_from_dict([json.loads(item.message_json) for item in tracker.inputs])
    assert len(messages) == 2
    assert all(
        _serialize_history_message(message, user=SimpleNamespace(locale="en")) is not None
        for message in messages
    )
