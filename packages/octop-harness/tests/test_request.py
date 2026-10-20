"""Tests for ``octop_harness.request.ChatRequest``."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from octop_harness.request import ChatRequest


class TestThreadId:
    def test_auto_generated_thread_id(self) -> None:
        req = ChatRequest(messages="hello")
        assert req.thread_id is not None
        assert len(req.thread_id) > 0
        assert req._auto_thread_id is True

    def test_explicit_thread_id_preserved(self) -> None:
        req = ChatRequest(messages="hi", thread_id="abc")
        assert req.thread_id == "abc"
        assert req._auto_thread_id is False


class TestNormalizeMessages:
    def test_string_becomes_human_message(self) -> None:
        msgs = ChatRequest(messages="hi").normalize_messages()
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "hi"

    def test_dict_list_normalized(self) -> None:
        msgs = ChatRequest(
            messages=[
                {"role": "system", "content": "be helpful"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        ).normalize_messages()
        assert isinstance(msgs[0], SystemMessage)
        assert isinstance(msgs[1], HumanMessage)
        assert isinstance(msgs[2], AIMessage)

    def test_basemessage_list_passed_through(self) -> None:
        original = [HumanMessage(content="x"), AIMessage(content="y")]
        msgs = ChatRequest(messages=original).normalize_messages()
        assert msgs == original

    def test_tool_message_requires_tool_call_id(self) -> None:
        with pytest.raises(ValueError, match="tool_call_id"):
            ChatRequest(messages=[{"role": "tool", "content": "result"}]).normalize_messages()

    def test_tool_message_with_call_id(self) -> None:
        msgs = ChatRequest(
            messages=[{"role": "tool", "content": "ok", "tool_call_id": "call_1"}],
        ).normalize_messages()
        assert isinstance(msgs[0], ToolMessage)
        assert msgs[0].tool_call_id == "call_1"

    def test_unknown_role_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown role"):
            ChatRequest(messages=[{"role": "wizard", "content": "x"}]).normalize_messages()

    def test_missing_role_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing required 'role'"):
            ChatRequest(messages=[{"content": "x"}]).normalize_messages()

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ChatRequest(messages=[]).normalize_messages()

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="messages must be"):
            ChatRequest(messages=42).normalize_messages()  # type: ignore[arg-type]


class TestCoerce:
    def test_coerce_string(self) -> None:
        req = ChatRequest.coerce("hi")
        assert isinstance(req, ChatRequest)
        assert req.messages == "hi"

    def test_coerce_dict(self) -> None:
        req = ChatRequest.coerce({"messages": "hi", "user": "alice"})
        assert req.user == "alice"

    def test_coerce_request_passthrough(self) -> None:
        original = ChatRequest(messages="hi", thread_id="t1")
        assert ChatRequest.coerce(original) is original

    def test_coerce_invalid_type(self) -> None:
        with pytest.raises(TypeError, match="Cannot coerce"):
            ChatRequest.coerce(123)  # type: ignore[arg-type]


class TestToRunnableConfig:
    def test_minimal(self) -> None:
        cfg = ChatRequest(messages="hi", thread_id="t1").to_runnable_config()
        assert cfg["configurable"] == {"thread_id": "t1"}
        assert "metadata" not in cfg
        assert "recursion_limit" not in cfg

    def test_full_population(self) -> None:
        cfg = ChatRequest(
            messages="hi",
            thread_id="t1",
            user="alice",
            source="cli",
            model="hai/Kimi",
            configurable={"feature_flag": True},
            metadata={"trace": "abc"},
            recursion_limit=50,
        ).to_runnable_config()
        configurable = cfg["configurable"]
        assert configurable["thread_id"] == "t1"
        assert configurable["user"] == "alice"
        assert configurable["source"] == "cli"
        assert configurable["model"] == "hai/Kimi"
        assert configurable["feature_flag"] is True
        assert cfg["metadata"] == {"trace": "abc"}
        assert cfg["recursion_limit"] == 50

    def test_callbacks_forwarded(self) -> None:
        sentinel = object()
        cfg = ChatRequest(messages="hi", callbacks=[sentinel]).to_runnable_config()
        assert cfg["callbacks"] == [sentinel]

    def test_user_configurable_overrides_auto(self) -> None:
        # When user explicitly sets thread_id inside configurable, it wins
        # (this is the expected escape hatch for advanced users).
        cfg = ChatRequest(
            messages="hi",
            thread_id="auto",
            configurable={"thread_id": "manual"},
        ).to_runnable_config()
        assert cfg["configurable"]["thread_id"] == "manual"

    def test_mcp_fields_omitted_by_default(self) -> None:
        cfg = ChatRequest(messages="hi").to_runnable_config()
        assert "mcp_servers" not in cfg["configurable"]
        assert "mcp_use_default" not in cfg["configurable"]

    def test_mcp_explicit_servers(self) -> None:
        cfg = ChatRequest(messages="hi", mcp_servers=["github", "math"]).to_runnable_config()
        assert cfg["configurable"]["mcp_servers"] == ["github", "math"]

    def test_mcp_use_default(self) -> None:
        cfg = ChatRequest(messages="hi", mcp_use_default=True).to_runnable_config()
        assert cfg["configurable"]["mcp_use_default"] is True

    def test_skills_and_agent_id(self) -> None:
        cfg = ChatRequest(
            messages="hi",
            skills=["web-search", "joke-mode"],
            agent_id="agent-42",
        ).to_runnable_config()
        assert cfg["configurable"]["skills"] == ["web-search", "joke-mode"]
        assert cfg["configurable"]["agent_id"] == "agent-42"

    def test_skills_empty_list(self) -> None:
        cfg = ChatRequest(messages="hi", skills=[]).to_runnable_config()
        assert cfg["configurable"]["skills"] == []

    def test_skills_and_agent_id_omitted_by_default(self) -> None:
        cfg = ChatRequest(messages="hi").to_runnable_config()
        assert "skills" not in cfg["configurable"]
        assert "agent_id" not in cfg["configurable"]
