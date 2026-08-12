"""Pydantic models for dashboard chat (WebSocket turn + REST helpers)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurnBody(BaseModel):
    """User turn payload — same fields for WebSocket ``user_turn`` and legacy HTTP bodies."""

    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="OpenAI-style message list for the turn.",
    )
    thread_id: str | None = Field(
        default=None,
        description="Existing conversation thread. Omit to reuse or create the dashboard session thread.",
    )
    session_key: str | None = Field(
        default=None,
        description="Dashboard session key. Defaults to the per-user dashboard key for this agent.",
    )
    mcp_servers: list[str] | None = Field(
        default=None,
        description="Connector MCP server names to attach for this request only.",
    )
    knowledge_base_ids: list[str] | None = Field(
        default=None,
        description="Knowledge base ids to retrieve for this request (empty disables defaults).",
    )
    skills: list[str] | None = Field(
        default=None,
        description="Skill names to enable for this request (empty list disables all skills).",
    )
    default_model: str | None = Field(
        default=None,
        description="Model ref override, e.g. `openai/gpt-4o`. Uses the agent default when omitted.",
    )
    reasoning_mode: Literal["auto", "enabled", "disabled"] | None = None
    reasoning_effort: str | None = None
    target_agent_ids: list[str] | None = Field(
        default=None,
        description="Optional agent ids to involve via @mention (same user only).",
    )
    locale: str | None = Field(
        default=None,
        description="Deprecated — locale is read from the user profile. Ignored when set.",
    )
    text: str | None = Field(default=None, description="Plain-text user message (WS shorthand).")

    @classmethod
    def from_ws_payload(cls, payload: dict[str, Any]) -> ChatTurnBody:
        """Normalize a WebSocket ``user_turn`` frame into :class:`ChatTurnBody`."""
        text = str(payload.get("text") or "").strip()
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            messages = [{"role": "user", "content": text}] if text else []
        model = payload.get("model") or payload.get("default_model")
        return cls(
            messages=messages,
            thread_id=str(payload["thread_id"]) if payload.get("thread_id") else None,
            session_key=str(payload["session_key"]) if payload.get("session_key") else None,
            mcp_servers=payload.get("mcp_servers")
            if isinstance(payload.get("mcp_servers"), list)
            else None,
            knowledge_base_ids=payload.get("knowledge_base_ids")
            if isinstance(payload.get("knowledge_base_ids"), list)
            else None,
            skills=payload.get("skills")
            if isinstance(payload.get("skills"), list)
            else payload.get("skills"),
            default_model=str(model).strip()
            if isinstance(model, str) and str(model).strip()
            else None,
            reasoning_mode=payload.get("reasoning_mode")
            if payload.get("reasoning_mode") in ("auto", "enabled", "disabled")
            else None,
            reasoning_effort=str(payload["reasoning_effort"]).strip()
            if isinstance(payload.get("reasoning_effort"), str)
            and str(payload["reasoning_effort"]).strip()
            else None,
            target_agent_ids=(
                [str(x) for x in payload["target_agent_ids"]]
                if isinstance(payload.get("target_agent_ids"), list)
                else None
            ),
            text=text or None,
        )


class UserTurnWsFrame(BaseModel):
    """Inbound WebSocket frame from the dashboard."""

    type: Literal["user_turn", "ping"] = "user_turn"
    text: str | None = None
    session_key: str | None = None
    thread_id: str | None = None
    model: str | None = None
    default_model: str | None = None
    reasoning_mode: Literal["auto", "enabled", "disabled"] | None = None
    reasoning_effort: str | None = None
    mcp_servers: list[str] | None = None
    knowledge_base_ids: list[str] | None = None
    skills: list[str] | None = None
    messages: list[dict[str, Any]] | None = None
    target_agent_ids: list[str] | None = None

    def to_turn_body(self) -> ChatTurnBody:
        return ChatTurnBody.from_ws_payload(self.model_dump(exclude_none=True))


class PolishBody(BaseModel):
    text: str
    default_model: str | None = None


class RebindSessionBody(BaseModel):
    thread_id: str


class RenameThreadBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    model_ref: str | None = None
    reasoning_mode: Literal["auto", "enabled", "disabled"] | None = None
    reasoning_effort: str | None = None


class HitlResumeBody(BaseModel):
    thread_id: str = Field(..., description="Conversation thread awaiting approval.")
    decisions: list[dict[str, Any]] = Field(
        ...,
        description='Human decisions, e.g. [{"type": "approve"}] or [{"type": "reject", "message": "..."}].',
    )
