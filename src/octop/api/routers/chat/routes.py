"""Dashboard chat helpers: polish prompt and HITL resume (SSE)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from octop.api.common.agent import assert_agent_access
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import HitlResumeBody, PolishBody
from octop.api.routers.chat.sse import format_sse
from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    read_workspace_manifest_welcome,
    welcome_payload_from_expert,
    welcome_payload_has_content,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.llm_text import ainvoke_text

router = APIRouter()
logger = logging.getLogger(__name__)

_POLISH_SYSTEM_PROMPT = (
    "You are a prompt editor, not an assistant that answers questions.\n"
    "The user message is a DRAFT PROMPT they will later send to another AI. "
    "Your only job is to rewrite that draft so another AI can understand it more "
    "clearly — improve clarity, specificity, structure, and actionable detail.\n"
    "Hard rules:\n"
    "- Do NOT answer the draft, solve the task, or provide the requested content.\n"
    "- Do NOT add explanations, greetings, or meta commentary.\n"
    "- Preserve the user's original intent and language (e.g. keep Chinese if the "
    "draft is Chinese).\n"
    "- Output ONLY the rewritten prompt text — no preamble, labels, quotes, "
    "thinking blocks, or XML tags."
)


@router.get("/agents/{agent_id}/chat/welcome", summary="Chat welcome quick cards")
async def get_chat_welcome(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Welcome copy for the empty chat screen.

    Resolution order:
    1. Agent workspace ``manifest.json`` (seeded at create; instance-owned).
    2. Bundled expert catalog entry for ``template_name`` (legacy agents).
    3. Default quick cards (``general-assistant`` or a small built-in set).
    """
    assert_agent_access(server, agent_id, user)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    catalog = server.expert_catalog

    workspace = registry.workspace_for_agent(agent_id)
    if workspace is not None:
        payload = await read_workspace_manifest_welcome(workspace)
        if payload is not None:
            return payload

    row = registry.get_row(agent_id)
    template = (row.template_name if row else None) or ""
    if catalog is not None and template:
        expert = catalog.get(template)
        if expert is not None:
            payload = welcome_payload_from_expert(expert)
            if welcome_payload_has_content(payload):
                return payload

    return default_welcome_payload(catalog)


@router.post("/agents/{agent_id}/chat/hitl/resume", summary="Resume HITL approval (SSE)")
async def resume_hitl(
    agent_id: str,
    body: HitlResumeBody,
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> StreamingResponse:
    """Resume a paused human-in-the-loop tool approval and stream subsequent chunks."""
    assert_agent_access(server, agent_id, user)
    agent_registry = server.app_runtime.agent_registry

    async def gen() -> AsyncIterator[str]:
        try:
            async for chunk in agent_registry.resume_hitl(agent_id, body.thread_id, body.decisions):
                if await request.is_disconnected():
                    break
                yield format_sse("chunk", chunk)
            yield format_sse("chunk", {"type": "done"})
        except Exception as exc:
            yield format_sse("chunk", {"type": "error", "message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agents/{agent_id}/chat/polish", summary="Polish prompt")
async def polish_prompt(
    agent_id: str,
    body: PolishBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, str]:
    """One-shot prompt refinement without touching thread history."""
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    assert_agent_access(server, agent_id, user)

    draft = body.text.strip()
    if not draft:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "text is required")

    harness = server.app_runtime.agent_registry.get_agent(agent_id)
    model_ref = (body.default_model or "").strip() or harness.config.pick_default_model_ref()
    llm = harness.model_factory.get(model_ref)
    try:
        polished = await ainvoke_text(
            llm,
            [
                SystemMessage(content=_POLISH_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        "Rewrite the following draft prompt. Do not answer it.\n\n"
                        f"---\n{draft}\n---"
                    ),
                ),
            ],
            timeout=30.0,
        )
    except TimeoutError:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "polish request timed out") from None
    except Exception as exc:
        logger.exception("polish failed agent=%s model=%s", agent_id, model_ref)
        raise OctopError(ErrorCode.INTERNAL_ERROR, str(exc)) from exc

    if not polished:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "model returned empty polish result")
    return {"text": polished}
