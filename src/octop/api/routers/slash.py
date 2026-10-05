"""Slash command discovery API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.agents.security import tool_execution_may_pause

router = APIRouter()


class SlashCommandOut(BaseModel):
    name: str = Field(..., description="Primary command name (without slash).")
    command: str = Field(..., description="Display form, e.g. `/help` or `/model <name>`.")
    aliases: list[str] = Field(default_factory=list)
    label_en: str = ""
    label_zh: str = ""
    description_en: str = ""
    description_zh: str = ""
    usage: str = ""
    icon: str = Field(..., description="Lucide icon name for the dashboard composer.")
    tone: str = Field(..., description="UI color tone key (emerald, violet, …).")
    category: str = Field(
        ...,
        description="Grouping: core, session, media, system, debug.",
    )
    origins: list[str] = Field(default_factory=list)
    client_action: Literal["none", "new_chat", "cancel_stream", "switch_agent"] = "none"


class SlashCommandListOut(BaseModel):
    origin: str
    commands: list[SlashCommandOut]


@router.get("/slash/commands", summary="List slash commands", response_model=SlashCommandListOut)
async def list_slash_commands(
    origin: str = Query(
        "ui",
        description="Filter by surface: `ui`, `im`, `cli`, or `all`.",
    ),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> SlashCommandListOut:
    """Return slash command metadata for composer menus and `/help`.

    Includes icon, tone, bilingual labels, usage hints, and client-side actions
    (e.g. `new_chat` is handled locally without sending to the LLM).
    """
    assert server.app_runtime is not None
    dispatcher = server.app_runtime.gateway.slash_dispatcher
    include_hitl = tool_execution_may_pause(server.app_runtime.agent_registry.security.load())
    specs = dispatcher.list_command_specs(
        origin=origin,
        include_hitl_approval=include_hitl,
    )
    commands = [
        SlashCommandOut(
            name=spec.name,
            command=spec.usage or spec.command,
            aliases=list(spec.aliases),
            label_en=spec.label_en,
            label_zh=spec.label_zh,
            description_en=spec.description_en,
            description_zh=spec.description_zh,
            usage=spec.usage or spec.command,
            icon=spec.icon,
            tone=spec.tone,
            category=spec.category,
            origins=sorted(spec.origins),
            client_action=spec.client_action,
        )
        for spec in specs
    ]
    return SlashCommandListOut(origin=origin, commands=commands)
