"""tests/unit/text_assist/test_service.py"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.text_assist import ASSIST_KINDS, run_text_assist


def _models(result: str = "polished") -> Any:
    access = MagicMock()
    access.model_ref = "openai/gpt-4o-mini"
    access.ainvoke_text = AsyncMock(return_value=result)
    models = MagicMock()
    models.get.return_value = access
    return models


@pytest.mark.asyncio
async def test_chat_prompt_requires_text() -> None:
    models = _models()
    with pytest.raises(OctopError) as exc:
        await run_text_assist(models=models, kind="chat.prompt", text="  ")
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS
    models.get.assert_not_called()


@pytest.mark.asyncio
async def test_form_kind_requires_name() -> None:
    models = _models()
    with pytest.raises(OctopError) as exc:
        await run_text_assist(
            models=models,
            kind="expert.description",
            text="",
            context={},
        )
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS
    models.get.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_kind_rejected() -> None:
    models = _models()
    with pytest.raises(OctopError) as exc:
        await run_text_assist(models=models, kind="nope.kind", text="x")  # type: ignore[arg-type]
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS
    models.get.assert_not_called()


@pytest.mark.asyncio
async def test_generate_from_name_uses_auto_model() -> None:
    models = _models("A concise expert description.")

    out = await run_text_assist(
        models=models,
        kind="expert.description",
        text="",
        context={"name": "产品顾问"},
        locale="zh",
    )
    assert out == "A concise expert description."
    models.get.assert_called_once_with(None)
    prompt = models.get.return_value.ainvoke_text.await_args.args[0]
    assert "产品顾问" in prompt


@pytest.mark.asyncio
async def test_explicit_model_forwarded() -> None:
    models = _models()

    out = await run_text_assist(
        models=models,
        kind="chat.prompt",
        text="help me write a plan",
        default_model="openai/gpt-4o",
    )
    assert out == "polished"
    models.get.assert_called_once_with("openai/gpt-4o")


def test_assist_kinds_cover_p0() -> None:
    assert "chat.prompt" in ASSIST_KINDS
    assert "expert.description" in ASSIST_KINDS
    assert "knowledge_base.description" in ASSIST_KINDS
    assert "connector.description" in ASSIST_KINDS
    assert "bridge.notes" in ASSIST_KINDS
    assert "user_group.description" in ASSIST_KINDS
    assert "user_role.description" in ASSIST_KINDS
    assert "skill.description" in ASSIST_KINDS
    assert "skill.label_zh" in ASSIST_KINDS
    assert "skill.body" in ASSIST_KINDS
