"""tests/unit/text_assist/test_service.py"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.text_assist.service import ASSIST_KINDS, run_text_assist


def _server_with_llm(llm: Any, *, model_ref: str = "openai/gpt-4o-mini") -> Any:
    factory = MagicMock()
    factory.get.return_value = llm
    providers = MagicMock()
    providers.is_model_ref_usable.side_effect = lambda ref: bool(ref) and ref != "bad/model"
    providers.resolve_first_model_ref.return_value = model_ref
    registry = MagicMock()
    registry.providers = providers
    registry.resolve_fallback_model_ref.return_value = model_ref
    registry.harness_manager = MagicMock(shared_factory=factory)
    server = MagicMock()
    server.app_runtime = MagicMock(agent_registry=registry)
    return server


@pytest.mark.asyncio
async def test_chat_prompt_requires_text() -> None:
    server = _server_with_llm(MagicMock())
    with pytest.raises(OctopError) as exc:
        await run_text_assist(server=server, kind="chat.prompt", text="  ")
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.asyncio
async def test_form_kind_requires_name() -> None:
    server = _server_with_llm(MagicMock())
    with pytest.raises(OctopError) as exc:
        await run_text_assist(
            server=server,
            kind="expert.description",
            text="",
            context={},
        )
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.asyncio
async def test_unknown_kind_rejected() -> None:
    server = _server_with_llm(MagicMock())
    with pytest.raises(OctopError) as exc:
        await run_text_assist(server=server, kind="nope.kind", text="x")  # type: ignore[arg-type]
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.asyncio
async def test_generate_from_name_uses_auto_model(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = MagicMock()
    server = _server_with_llm(llm, model_ref="p/auto-model")
    invoke = AsyncMock(return_value="A concise expert description.")
    monkeypatch.setattr(
        "octop.infra.text_assist.service.ainvoke_text",
        invoke,
    )

    out = await run_text_assist(
        server=server,
        kind="expert.description",
        text="",
        context={"name": "产品顾问"},
        locale="zh",
    )
    assert out == "A concise expert description."
    server.app_runtime.agent_registry.harness_manager.shared_factory.get.assert_called_once_with(
        "p/auto-model"
    )
    messages = invoke.await_args.args[1]
    assert "产品顾问" in messages[1].content


@pytest.mark.asyncio
async def test_explicit_model_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = MagicMock()
    server = _server_with_llm(llm)
    invoke = AsyncMock(return_value="polished")
    monkeypatch.setattr("octop.infra.text_assist.service.ainvoke_text", invoke)

    out = await run_text_assist(
        server=server,
        kind="chat.prompt",
        text="help me write a plan",
        default_model="openai/gpt-4o",
    )
    assert out == "polished"
    server.app_runtime.agent_registry.harness_manager.shared_factory.get.assert_called_once_with(
        "openai/gpt-4o"
    )


def test_assist_kinds_cover_p0() -> None:
    assert "chat.prompt" in ASSIST_KINDS
    assert "expert.description" in ASSIST_KINDS
    assert "knowledge_base.description" in ASSIST_KINDS
