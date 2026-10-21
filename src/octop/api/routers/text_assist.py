"""Unified one-shot text assist (polish / generate) for dashboard UI."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_access
from octop.api.deps import current_user, get_server
from octop.infra.text_assist import run_text_assist
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()

AssistKind = Literal[
    "chat.prompt",
    "expert.description",
    "expert.welcome_message",
    "team.description",
    "team.welcome_message",
    "skill_package.description",
    "knowledge_base.description",
]


class TextAssistBody(BaseModel):
    kind: AssistKind = Field(description="Assist scenario; selects the backend prompt.")
    text: str = Field(
        default="",
        description="Draft to polish. Required for chat.prompt; optional for form kinds.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Scenario context. Form kinds require `name`.",
    )
    locale: str | None = Field(
        default=None,
        description="Output locale (`zh` / `en`). Defaults to the request locale.",
    )
    default_model: str | None = Field(
        default=None,
        description="Model ref override. Omit or `auto` for automatic routing.",
    )
    agent_id: str | None = Field(
        default=None,
        description="Optional agent scope for access checks (e.g. chat polish).",
    )


class TextAssistResponse(BaseModel):
    text: str


@router.post(
    "/text/assist",
    summary="Polish or generate short copy",
    response_model=TextAssistResponse,
)
async def text_assist(
    body: TextAssistBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TextAssistResponse:
    """One-shot LLM rewrite/generate for form fields and chat composer polish.

    Prompts live in backend i18n (`text_assist.kinds.*`). Model selection uses
    an explicit usable ``default_model`` when provided; otherwise the automatic
    route. Does not touch thread history.
    """
    agent_id = (body.agent_id or "").strip()
    if agent_id:
        assert_agent_access(server, agent_id, user)

    locale = (body.locale or "").strip() or resolve_request_locale(request)
    text = await run_text_assist(
        server=server,
        kind=body.kind,
        text=body.text,
        context=body.context,
        locale=locale,
        default_model=body.default_model,
    )
    return TextAssistResponse(text=text)
