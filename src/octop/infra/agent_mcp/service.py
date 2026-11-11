"""Domain service for external Agent-to-Octop expert calls."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import (
    HitlStreamContext,
    decision_rejection_reason,
)
from octop.infra.gateway.hitl.format import normalize_hitl_request
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.gateway.gateway import Gateway
    from octop.infra.gateway.hitl.store import HitlPendingRecord
    from octop.infra.users.identity import User

MCP_CHANNEL_ID = "octop-agent-mcp"
_MAX_MESSAGE_CHARS = 100_000
_MAX_DECISIONS = 16
_MAX_DECISION_MESSAGE_CHARS = 100_000
_DECISION_TYPES = frozenset({"approve", "edit", "reject", "respond"})


class AgentMcpGatewayService:
    """Expose accessible Octop experts through a small, isolated call surface."""

    def __init__(self, *, agent_manager: AgentManager, gateway: Gateway) -> None:
        self._agent_manager = agent_manager
        self._gateway = gateway

    def list_experts(self, user: User) -> dict[str, Any]:
        experts = []
        for row in self._agent_manager.list_rows():
            if row.kind != "expert" or not self._can_access(row, user):
                continue
            experts.append(
                {
                    "expert_id": row.agent_id,
                    "name": row.name,
                    "description": row.description or "",
                    "state": row.last_state or "unknown",
                    "default_model": row.default_model,
                    "template_name": row.template_name,
                    "shared": bool(row.is_shared),
                }
            )
        return {"experts": experts, "count": len(experts)}

    async def call_expert(
        self,
        user: User,
        *,
        expert_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._require_expert(expert_id, user)
        text = self._validate_message(message)
        thread, session_key = await self._resolve_thread(
            expert_id=row.agent_id,
            user=user,
            thread_id=thread_id,
        )
        inbound = InboundMessage(
            channel_id=MCP_CHANNEL_ID,
            channel_type=ThreadRegistry.CHANNEL_MCP,
            tenant_id=row.agent_id,
            channel_subject=ChannelSubject(subject_id=str(user.id)),
            channel_session_id=session_key,
            content=[TextContent(text=text)],
            metadata={
                "session_key": session_key,
                "thread_id": thread,
                "user_is_admin": user.is_admin,
            },
        )
        chunks = self._gateway.processor.iter_turn_chunks(inbound)
        return await self._collect_result(
            chunks,
            expert_id=row.agent_id,
            thread_id=thread,
        )

    async def resume_expert(
        self,
        user: User,
        *,
        expert_id: str,
        thread_id: str,
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = self._require_expert(expert_id, user)
        thread = self._require_mcp_thread(
            thread_id,
            expert_id=row.agent_id,
            user_id=user.id,
        )
        normalized = self._validate_decisions(decisions)
        coordinator = self._gateway.processor.hitl_coordinator
        pending = coordinator.store.resolve_pending_for_thread(
            thread_id,
            agent_id=row.agent_id,
            user_id=user.id,
        )
        if pending is not None:
            reason = decision_rejection_reason(pending, normalized)
            if reason is not None:
                raise ValueError(reason)
        chunks = self._iter_resume_chunks(
            expert_id=row.agent_id,
            thread_id=thread_id,
            user_id=user.id,
            session_key=thread.session_key,
            decisions=normalized,
            pending=pending,
        )
        return await self._collect_result(
            chunks,
            expert_id=row.agent_id,
            thread_id=thread_id,
        )

    async def _iter_resume_chunks(
        self,
        *,
        expert_id: str,
        thread_id: str,
        user_id: int,
        session_key: str,
        decisions: list[dict[str, Any]],
        pending: HitlPendingRecord | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resolve the current pause and persist any follow-up approval."""
        coordinator = self._gateway.processor.hitl_coordinator
        rejected = any(decision.get("type") == "reject" for decision in decisions)
        if pending is not None:
            coordinator.store.mark_resolved(
                pending.pending_id,
                "rejected" if rejected else "approved",
            )
        try:
            chunks = self._gateway.processor.iter_hitl_resume_chunks(
                agent_id=expert_id,
                thread_id=thread_id,
                user_id=user_id,
                decisions=decisions,
            )
            async for chunk in chunks:
                if isinstance(chunk, dict) and chunk.get("type") == "hitl_required":
                    request = chunk.get("request")
                    if isinstance(request, dict):
                        request = normalize_hitl_request(request)
                        record = coordinator.register_from_request(
                            request,
                            ctx=HitlStreamContext(
                                thread_id=thread_id,
                                agent_id=expert_id,
                                user_id=user_id,
                                session_key=session_key,
                                channel_type=ThreadRegistry.CHANNEL_MCP,
                            ),
                        )
                        request["pending_id"] = record.pending_id
                        chunk = {**chunk, "request": request}
                yield chunk
        except Exception:
            if pending is not None:
                coordinator.store.mark_resolved(pending.pending_id, "expired")
            raise

    async def _resolve_thread(
        self,
        *,
        expert_id: str,
        user: User,
        thread_id: str | None,
    ) -> tuple[str, str]:
        if thread_id:
            row = self._require_mcp_thread(thread_id, expert_id=expert_id, user_id=user.id)
            return row.thread_id, row.session_key

        registry = self._gateway.thread_registry
        session_key = ThreadRegistry.mcp_key(
            agent_id=expert_id,
            user_id=user.id,
            call_id=new_ulid(),
        )
        created = await registry.get_or_create_by_key(
            session_key=session_key,
            agent_id=expert_id,
            user_id=user.id,
            channel_type=ThreadRegistry.CHANNEL_MCP,
            channel_channel_id=MCP_CHANNEL_ID,
        )
        return created, session_key

    def _require_mcp_thread(self, thread_id: str, *, expert_id: str, user_id: int) -> Any:
        row = self._gateway.thread_registry.get_thread(thread_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"thread {thread_id!r} not found")
        if row.agent_id != expert_id or row.user_id != user_id:
            raise OctopError(ErrorCode.FORBIDDEN, "thread is not accessible")
        if row.channel_type != ThreadRegistry.CHANNEL_MCP:
            raise OctopError(
                ErrorCode.FORBIDDEN,
                "only MCP-created threads can be continued through this gateway",
            )
        return row

    def _require_expert(self, expert_id: str, user: User) -> Any:
        row = self._agent_manager.get_row(expert_id)
        if row is None or row.kind != "expert":
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"expert {expert_id!r} not found")
        if not self._can_access(row, user):
            raise OctopError(ErrorCode.FORBIDDEN, "expert is not accessible")
        if not row.enabled:
            raise OctopError(ErrorCode.AGENT_NOT_RUNNING, "expert is disabled")
        return row

    def _can_access(self, row: Any, user: User) -> bool:
        from octop.infra.users.groups import expert_visible_to  # noqa: PLC0415

        return expert_visible_to(
            self._agent_manager._repos,
            row,
            user_id=user.id,
            is_admin=bool(user.is_admin),
        )

    @staticmethod
    def _validate_message(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            raise ValueError("message is required")
        if len(text) > _MAX_MESSAGE_CHARS:
            raise ValueError(f"message exceeds {_MAX_MESSAGE_CHARS} characters")
        return text

    @staticmethod
    def _validate_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not decisions or len(decisions) > _MAX_DECISIONS:
            raise ValueError(f"decisions must contain 1 to {_MAX_DECISIONS} items")
        normalized: list[dict[str, Any]] = []
        for decision in decisions:
            if not isinstance(decision, dict):
                raise ValueError("each decision must be an object")
            kind = str(decision.get("type") or "")
            if kind not in _DECISION_TYPES:
                raise ValueError(f"unsupported decision type: {kind!r}")
            if kind == "edit" and not isinstance(decision.get("edited_action"), dict):
                raise ValueError("edit decision requires an 'edited_action' object")
            message = decision.get("message")
            if kind == "respond" and (not isinstance(message, str) or not message.strip()):
                raise ValueError("respond decision requires a non-empty 'message'")
            if message is not None:
                if not isinstance(message, str):
                    raise ValueError("decision 'message' must be a string")
                if len(message) > _MAX_DECISION_MESSAGE_CHARS:
                    raise ValueError(
                        f"decision 'message' exceeds {_MAX_DECISION_MESSAGE_CHARS} characters"
                    )
            normalized.append(dict(decision))
        return normalized

    @staticmethod
    async def _collect_result(
        chunks: Any,
        *,
        expert_id: str,
        thread_id: str,
    ) -> dict[str, Any]:
        text_parts: list[str] = []
        error: dict[str, Any] | None = None
        approval: dict[str, Any] | None = None
        usage: dict[str, Any] | None = None
        async for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            kind = str(chunk.get("type") or "")
            if kind in {"token", "delta"}:
                text = chunk.get("content", chunk.get("text", ""))
                if text:
                    text_parts.append(str(text))
            elif kind == "error":
                error = {
                    "message": str(chunk.get("message") or "expert call failed"),
                    **({"code": str(chunk["error_code"])} if chunk.get("error_code") else {}),
                }
            elif kind == "hitl_required":
                request = chunk.get("request")
                pending_id = chunk.get("pending_id")
                if pending_id is None and isinstance(request, dict):
                    pending_id = request.get("pending_id")
                approval = {
                    "pending_id": pending_id,
                    "request": request,
                }
            elif kind == "usage" and isinstance(chunk.get("usage"), dict):
                usage = dict(chunk["usage"])

        status = "failed" if error else "approval_required" if approval else "completed"
        result: dict[str, Any] = {
            "status": status,
            "expert_id": expert_id,
            "thread_id": thread_id,
            "response": "".join(text_parts),
        }
        if error:
            result["error"] = error
        if approval:
            result["approval"] = approval
        if usage:
            result["usage"] = usage
        return result
