"""CLI chat turn preparation (thread binding + InboundMessage)."""

from __future__ import annotations

from typing import Any

from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.cli.cli_channel import CLI_CHANNEL_ID, CLI_CONNECTION_META
from octop.infra.gateway.threads import ThreadRegistry

__all__ = ["build_cli_inbound", "prepare_cli_turn"]


async def prepare_cli_turn(
    thread_registry: ThreadRegistry,
    *,
    agent_id: str,
    user_id: int,
    thread_id: str | None,
    session_key: str | None,
) -> tuple[str, str]:
    """Resolve session_key and thread_id for a CLI turn."""
    sk = session_key or ThreadRegistry.cli_key(agent_id=agent_id, user_id=user_id)
    if thread_id:
        row = thread_registry.get_thread(thread_id)
        if row is None or row.agent_id != agent_id:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"thread {thread_id!r} not found")
        await thread_registry.rebind(session_key=sk, thread_id=thread_id, agent_id=agent_id)
        return thread_id, sk
    bound = thread_registry.get_bound_thread_id(sk)
    if bound:
        return bound, sk
    tid = await thread_registry.get_or_create_by_key(
        session_key=sk,
        agent_id=agent_id,
        user_id=user_id,
        channel_type=ThreadRegistry.CHANNEL_CLI,
        channel_channel_id=CLI_CHANNEL_ID,
    )
    return tid, sk


def build_cli_inbound(
    *,
    agent_id: str,
    user_id: int,
    text: str,
    session_key: str,
    thread_id: str,
    cli_connection_id: str,
    model: str | None = None,
    conversation_mode: str | None = None,
    user_is_admin: bool = False,
) -> InboundMessage:
    metadata: dict[str, Any] = {
        CLI_CONNECTION_META: cli_connection_id,
        "session_key": session_key,
        "thread_id": thread_id,
        "user_is_admin": user_is_admin,
    }
    if model:
        metadata["model"] = model
    if conversation_mode in ("ask", "plan", "craft"):
        metadata["conversation_mode"] = conversation_mode
    return InboundMessage(
        channel_id=CLI_CHANNEL_ID,
        channel_type=ThreadRegistry.CHANNEL_CLI,
        tenant_id=agent_id,
        channel_subject=ChannelSubject(subject_id=str(user_id)),
        channel_session_id=session_key,
        content=[TextContent(text=text)],
        metadata=metadata,
    )
