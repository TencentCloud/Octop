"""Team callback contract: TeamProcessor + ReplyEvent.

A :class:`TeamProcessor` turns the inbox into an *active* mailbox. When a
manager is constructed with one, :class:`~octop_harness.teams.inbox.HarnessAgentInboxManager`
processes queued messages and, for each, asks the host to:

1. ``compose_followup`` — combine the target agent's result (or error) into a
   prompt for the *source* agent;
2. ``on_reply`` — deliver the source agent's synthesized reply so the host
   can push it. octop-harness does not talk to a gateway or IM; DM and
   group rooms use this same hook. Extra room data (transcript, cards)
   is a host concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from octop_harness.teams.inbox import InboxMessage

ReplyStatus = Literal["done", "failed", "cancelled"]


@dataclass
class ReplyEvent:
    """Final outcome of one inbox message, handed to :meth:`TeamProcessor.on_reply`."""

    inbox_id: str
    status: ReplyStatus
    source_agent_id: str
    source_thread_id: str | None
    target_agent_id: str
    user_id: str | int
    reply_text: str | None = None
    error_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TeamProcessor(Protocol):
    """Host hook that powers inbox-driven (asynchronous) peer collaboration."""

    def compose_followup(
        self,
        msg: InboxMessage,
        *,
        result_text: str | None,
        error_text: str | None,
    ) -> str:
        """Return the prompt fed to the *source* agent to synthesize a reply."""
        ...

    async def on_reply(self, event: ReplyEvent) -> None:
        """Deliver the source agent's reply to the user surface (push)."""
        ...


def default_compose_followup(
    msg: InboxMessage,
    *,
    result_text: str | None,
    error_text: str | None,
) -> str:
    """Generic prompt combining the peer result back into the source thread.

    Hosts typically provide their own (localized / richer) implementation;
    this exists so a minimal :class:`TeamProcessor` can reuse it.
    """
    lines = [f"[background task from agent {msg.target_agent_id}]", f"Task: {msg.message}"]
    if msg.original_user_prompt and msg.original_user_prompt.strip() != msg.message.strip():
        lines.append(f"Original user question: {msg.original_user_prompt.strip()}")
    if error_text:
        lines += [
            "",
            f"The task failed: {error_text}",
            "",
            "Briefly explain to the user and suggest next steps.",
        ]
    else:
        lines += [
            "",
            "Result:",
            (result_text or "(empty)").strip(),
            "",
            "Reply to the user using the conversation context.",
        ]
    return "\n".join(lines)


__all__ = ["ReplyEvent", "ReplyStatus", "TeamProcessor", "default_compose_followup"]
