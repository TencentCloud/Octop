"""Tests for ``BootstrapMiddleware``."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from octop_harness.backends.workspace import BackendWorkspace
from octop_harness.middleware.bootstrap import (
    BOOTSTRAP_FILENAME,
    BOOTSTRAPPED_MARKER,
    DEFAULT_BOOTSTRAP_PATH,
    DEFAULT_BOOTSTRAPPED_PATH,
    DEFAULT_USER_PATH,
    BootstrapMiddleware,
)


def _fs_backend(tmp_path: Path) -> Any:
    from deepagents.backends import FilesystemBackend

    return FilesystemBackend(root_dir=str(tmp_path), virtual_mode=False)


def _workspace(tmp_path: Path) -> BackendWorkspace:
    return BackendWorkspace(_fs_backend(tmp_path), tmp_path)


def _middleware(
    tmp_path: Path,
    *,
    bootstrap_file: str | Path | None = DEFAULT_BOOTSTRAP_PATH,
    bootstrap_marker: str | Path | None = DEFAULT_BOOTSTRAPPED_PATH,
) -> BootstrapMiddleware:
    return BootstrapMiddleware(
        _workspace(tmp_path),
        bootstrap_file=bootstrap_file,
        bootstrap_marker=bootstrap_marker,
    )


def _state(*messages: object) -> dict[str, list[object]]:
    return {"messages": list(messages)}


def _system_texts(message: SystemMessage) -> list[str]:
    blocks = getattr(message, "content_blocks", None) or []
    texts = [str(b.get("text") or "") for b in blocks if isinstance(b, dict)]
    if texts:
        return texts
    content = message.content
    if isinstance(content, str):
        return [content]
    return [str(content)]


def test_wrap_model_call_appends_bootstrap_after_compiled_system_prompt(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = BootstrapMiddleware(ws, bootstrap_file=DEFAULT_BOOTSTRAP_PATH, bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH)

    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    base_prompt = SystemMessage(content="Your working directory is /.octop/workspaces/ABC123.")
    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=base_prompt,
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )

    mw.wrap_model_call(request, handler)

    applied = captured["request"]
    assert applied.system_message is not None
    texts = _system_texts(applied.system_message)
    joined = "\n".join(texts)
    assert texts[0].strip().startswith("Your working directory is /.octop/workspaces/ABC123.")
    assert "onboarding instructions" in joined
    assert joined.find("Your working directory is /.octop/workspaces/ABC123.") < joined.find("onboarding instructions")
    assert all(not isinstance(m, SystemMessage) for m in applied.messages)


def test_bootstrap_injection_is_logged_once_at_debug(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = BootstrapMiddleware(ws, bootstrap_file=DEFAULT_BOOTSTRAP_PATH, bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH)

    def handler(request: ModelRequest) -> ModelResponse:
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    with caplog.at_level(logging.DEBUG, logger="octop_harness.middleware.bootstrap"):
        mw.wrap_model_call(request, handler)
        mw.wrap_model_call(request, handler)
    logged = [rec for rec in caplog.records if "Bootstrap active" in rec.message]
    assert len(logged) == 1
    assert logged[0].levelno == logging.DEBUG


def test_wrap_model_call_uses_bootstrap_alone_when_system_message_missing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = BootstrapMiddleware(ws, bootstrap_file=DEFAULT_BOOTSTRAP_PATH, bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH)

    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=None,
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    mw.wrap_model_call(request, handler)
    assert captured["request"].system_message is not None
    assert "onboarding instructions" in "\n".join(_system_texts(captured["request"].system_message))


def test_wrap_model_call_skips_after_marker(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    ws.write_text(DEFAULT_BOOTSTRAPPED_PATH, "", force=True)
    mw = BootstrapMiddleware(ws, bootstrap_file=DEFAULT_BOOTSTRAP_PATH, bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH)

    base_prompt = SystemMessage(content="You are a deep agent")
    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=base_prompt,
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )

    def handler(req: ModelRequest) -> ModelResponse:
        assert req.system_message is base_prompt
        return ModelResponse(result=[AIMessage(content="ok")])

    mw.wrap_model_call(request, handler)


def test_wrap_model_call_injects_on_every_turn_until_marker_exists(tmp_path: Path) -> None:
    """Onboarding uses the model-request path only — no state.message pollution."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = _middleware(tmp_path)

    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> ModelResponse:
        captured.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    for _ in range(2):
        request = ModelRequest(
            model=MagicMock(),
            tools=[],
            system_message=SystemMessage(content="You are a deep agent"),
            messages=[HumanMessage(content="hi")],
            tool_choice=None,
            response_format=None,
            state={"messages": [HumanMessage(content="hi")]},
            runtime=MagicMock(),
        )
        mw.wrap_model_call(request, handler)

    assert len(captured) == 2
    for applied in captured:
        assert applied.system_message is not None
        texts = _system_texts(applied.system_message)
        joined = "\n".join(texts)
        assert "You are a deep agent" in joined
        assert "onboarding instructions" in joined
        assert joined.find("You are a deep agent") < joined.find("onboarding instructions")
        assert all(not isinstance(m, SystemMessage) for m in applied.messages)


def test_wrap_model_call_appends_without_flattening_blocks(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = BootstrapMiddleware(ws, bootstrap_file=DEFAULT_BOOTSTRAP_PATH, bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH)
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    existing = SystemMessage(
        content_blocks=[
            {"type": "text", "text": "Your working directory is /.octop/workspaces/ABC123."},
            {"type": "text", "text": "slash skill rule"},
        ]
    )
    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=existing,
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    mw.wrap_model_call(request, handler)

    blocks = captured["request"].system_message.content_blocks
    texts = [str(b.get("text", "")) for b in blocks if isinstance(b, dict)]
    assert texts[0] == "Your working directory is /.octop/workspaces/ABC123."
    assert "slash skill rule" in texts[1]
    assert any("onboarding instructions" in t for t in texts)
    assert len(texts) >= 3


def test_before_agent_does_not_persist_system_message(tmp_path: Path) -> None:
    """Bootstrap must not write SystemMessage into checkpoint state via before_agent.

    LangGraph's add_messages reducer appends unmatched message ids to the tail,
    so a returned SystemMessage would land mid-list after the next user turn and
    break strict backends once bootstrap middleware is removed.
    """
    from langgraph.graph.message import add_messages

    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding instructions", force=True)
    mw = _middleware(tmp_path)

    # Inherited no-op from AgentMiddleware — must not inject into state.
    assert mw.before_agent(_state(HumanMessage(content="hi")), runtime=None) is None

    # Document the reducer trap that made the old before_agent unsafe.
    left = [HumanMessage(content="hi", id="h1")]
    mistaken = [SystemMessage(content="BOOTSTRAP"), HumanMessage(content="hi", id="h1")]
    merged = add_messages(left, mistaken)
    assert isinstance(merged[-1], SystemMessage)
    assert merged[-1].content == "BOOTSTRAP"


def test_skips_when_marker_exists(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    ws.write_text(DEFAULT_BOOTSTRAPPED_PATH, "", force=True)
    mw = _middleware(tmp_path)

    assert mw.is_bootstrapped
    base_prompt = SystemMessage(content="You are a deep agent")
    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=base_prompt,
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )

    def handler(req: ModelRequest) -> ModelResponse:
        assert req.system_message is base_prompt
        return ModelResponse(result=[AIMessage(content="ok")])

    mw.wrap_model_call(request, handler)


def test_missing_bootstrap_file_does_not_write_marker(tmp_path: Path) -> None:
    mw = _middleware(tmp_path)

    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    mw.wrap_model_call(request, lambda req: ModelResponse(result=[AIMessage(content="ok")]))
    assert not _workspace(tmp_path).exists(DEFAULT_BOOTSTRAPPED_PATH)


def test_keeps_bootstrap_file_when_marker_absent(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = _middleware(tmp_path)

    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    mw.wrap_model_call(request, lambda req: ModelResponse(result=[AIMessage(content="ok")]))
    assert ws.exists(DEFAULT_BOOTSTRAP_PATH)


def test_marker_detected_on_backend(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    ws.write_text(DEFAULT_BOOTSTRAPPED_PATH, "", force=True)

    mw = _middleware(tmp_path)
    assert mw.is_bootstrapped


def test_user_md_write_attempt_does_not_complete_onboarding(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)

    mw = _middleware(tmp_path)
    state = _state(
        HumanMessage(content="hi"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "edit_file",
                    "args": {"file_path": DEFAULT_USER_PATH, "old_string": "a", "new_string": "b"},
                    "id": "1",
                    "type": "tool_call",
                },
            ],
        ),
    )
    mw.after_agent(state, runtime=None)

    assert not mw.is_bootstrapped
    assert not ws.exists(DEFAULT_BOOTSTRAPPED_PATH)


def test_after_agent_does_not_write_marker_on_read_file_bootstrap_marker(tmp_path: Path) -> None:
    """read_file on .bootstrapped must NOT be treated as onboarding completion."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = _middleware(tmp_path)

    state = _state(
        HumanMessage(content="hi"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_file",
                    "args": {"file_path": DEFAULT_BOOTSTRAPPED_PATH},
                    "id": "1",
                    "type": "tool_call",
                },
            ],
        ),
    )
    mw.after_agent(state, runtime=None)
    assert not mw.is_bootstrapped


def test_after_agent_writes_marker_on_first_reply(tmp_path: Path) -> None:
    """Bootstrap completes once the agent gives a non-empty final reply."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = _middleware(tmp_path)

    state = _state(
        HumanMessage(content="hi"),
        AIMessage(content="Hello! What's your name?"),
    )
    mw.after_agent(state, runtime=None)
    assert mw.is_bootstrapped


def test_after_agent_writes_marker_after_max_bootstrap_turns(tmp_path: Path) -> None:
    """Legacy test name — first final reply completes onboarding regardless of max_bootstrap_turns."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = BootstrapMiddleware(
        ws,
        bootstrap_file=DEFAULT_BOOTSTRAP_PATH,
        bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH,
        max_bootstrap_turns=2,
    )

    state1 = _state(
        HumanMessage(content="hi"),
        AIMessage(content="Hello! What's your name?"),
    )
    mw.after_agent(state1, runtime=None)
    assert mw.is_bootstrapped


def test_after_agent_does_not_count_tool_call_steps_as_final_response(tmp_path: Path) -> None:
    """AIMessages that still have tool_calls must not count toward the turn threshold."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = BootstrapMiddleware(
        ws,
        bootstrap_file=DEFAULT_BOOTSTRAP_PATH,
        bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH,
        max_bootstrap_turns=1,
    )

    # AIMessage with tool_calls (intermediate step) must not count
    state = _state(
        HumanMessage(content="hi"),
        AIMessage(
            content="Let me check...",
            tool_calls=[{"name": "read_file", "args": {"file_path": "/AGENTS.md"}, "id": "t1", "type": "tool_call"}],
        ),
    )
    mw.after_agent(state, runtime=None)
    assert not mw.is_bootstrapped


def test_after_agent_already_bootstrapped_skips_write(tmp_path: Path) -> None:
    """after_agent must be idempotent when the marker already exists."""
    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    ws.write_text(DEFAULT_BOOTSTRAPPED_PATH, "", force=True)
    mw = _middleware(tmp_path)

    state = _state(
        HumanMessage(content="hi"),
        AIMessage(content="Already done."),
        AIMessage(content="Already done."),
        AIMessage(content="Already done."),
    )
    # Should not raise and marker should remain as-is
    mw.after_agent(state, runtime=None)
    assert mw.is_bootstrapped


def test_aafter_agent_delegates_to_after_agent(tmp_path: Path) -> None:
    """aafter_agent must write the marker just like the sync version."""
    import asyncio

    ws = _workspace(tmp_path)
    ws.write_text(DEFAULT_BOOTSTRAP_PATH, "onboarding", force=True)
    mw = BootstrapMiddleware(
        ws,
        bootstrap_file=DEFAULT_BOOTSTRAP_PATH,
        bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH,
        max_bootstrap_turns=1,
    )

    state = _state(
        HumanMessage(content="hi"),
        AIMessage(content="Hello! I am your assistant."),
    )
    asyncio.run(mw.aafter_agent(state, runtime=None))
    assert mw.is_bootstrapped


def test_complete_storage_bootstrap_path(tmp_path: Path) -> None:
    storage = str(tmp_path / "agent" / BOOTSTRAP_FILENAME)
    ws = _workspace(tmp_path)
    ws.write_text(storage, "custom onboarding", force=True)

    mw = BootstrapMiddleware(
        ws,
        bootstrap_file=storage,
        bootstrap_marker=str(tmp_path / "agent" / BOOTSTRAPPED_MARKER),
    )
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    request = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="hi")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="hi")]},
        runtime=MagicMock(),
    )
    mw.wrap_model_call(request, handler)
    assert captured["request"].system_message is not None
    joined = "\n".join(_system_texts(captured["request"].system_message))
    assert "base" in joined
    assert "custom onboarding" in joined
    assert joined.find("base") < joined.find("custom onboarding")


def test_missing_marker_is_checked_once(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    calls = 0
    real_exists = ws.exists

    def _counted(path: str) -> bool:
        nonlocal calls
        calls += 1
        return real_exists(path)

    ws.exists = _counted  # type: ignore[method-assign]
    mw = BootstrapMiddleware(
        ws,
        bootstrap_file=DEFAULT_BOOTSTRAP_PATH,
        bootstrap_marker=DEFAULT_BOOTSTRAPPED_PATH,
    )

    assert mw.is_bootstrapped is False
    assert mw.is_bootstrapped is False
    assert calls == 1
