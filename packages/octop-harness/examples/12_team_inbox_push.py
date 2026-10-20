# pylint: disable=invalid-name
"""Async ``ask_agent`` follow-up: DM and team rooms share one push hook.

octop-harness does **not** depend on a gateway, IM, or HTTP server. After a
background peer job finishes it:

1. ``call``s the source agent on the original ``thread_id`` / ``session_key``
2. hands ``TeamProcessor.on_reply`` a ``ReplyEvent``

The host (Octop) is what talks to the gateway. DM and group rooms use that
same ``on_reply`` → ``gateway.push`` path. A group room only adds host-side
data (room transcript, member cards) around the identical push.

::

    ask_agent (async)
        → inbox: target.call → compose_followup → source.call
        → TeamProcessor.on_reply(ReplyEvent)
        → host gateway.push(surface, thread_id, text)
             └─ room only: also write Octop room transcript

This script fakes the agents and the gateway so it runs without API keys.

Run with::

    uv run python examples/12_team_inbox_push.py
"""

from __future__ import annotations

import asyncio
from typing import Any

from octop_harness.request import ChatRequest
from octop_harness.teams import (
    HarnessAgentInboxManager,
    InboxMessage,
    ReplyEvent,
    default_compose_followup,
)


class FakeGateway:
    """Stand-in for the host IM gateway. octop-harness never imports this."""

    def __init__(self) -> None:
        self.pushes: list[tuple[str, str, str]] = []

    async def push(self, *, surface: str, thread_id: str, text: str) -> None:
        self.pushes.append((surface, thread_id, text))
        print(f"[gateway.push] surface={surface} thread={thread_id}\n  {text}\n")


class HostProcessor:
    """Octop-shaped host: one push path, extra room write only for groups."""

    def __init__(self, gateway: FakeGateway) -> None:
        self._gateway = gateway
        self.room_transcript: list[str] = []

    def compose_followup(self, msg: InboxMessage, *, result_text: str | None, error_text: str | None) -> str:
        return default_compose_followup(msg, result_text=result_text, error_text=error_text)

    async def on_reply(self, event: ReplyEvent) -> None:
        surface = str(event.metadata.get("surface") or "dm")
        thread_id = event.source_thread_id or event.source_agent_id
        text = event.reply_text or event.error_text or ""
        # Group rooms: host-only extra write. Push below is unchanged.
        if surface == "room":
            self.room_transcript.append(f"{event.target_agent_id} → {thread_id}: {text}")
        await self._gateway.push(surface=surface, thread_id=thread_id, text=text)


async def _fake_call(agent_id: str, request: ChatRequest) -> dict[str, Any]:
    session = (request.configurable or {}).get("session_key", "")
    if agent_id in {"researcher", "analyst"}:
        return {"messages": [{"role": "assistant", "content": f"{agent_id} done ({session})"}]}
    return {"messages": [{"role": "assistant", "content": f"follow-up for user via {session}"}]}


async def main() -> None:
    gateway = FakeGateway()
    processor = HostProcessor(gateway)
    inbox = HarnessAgentInboxManager(call_agent=_fake_call, processor=processor)

    # Same enqueue / on_reply / gateway.push for a 1:1 DM and a team room.
    inbox.enqueue(
        target_agent_id="researcher",
        source_agent_id="host-expert",
        source_thread_id="thr_dm_7",
        message="summarize the brief",
        user_id=7,
        metadata={"session_key": "host-expert:app:7:dm", "surface": "dm"},
    )
    inbox.enqueue(
        target_agent_id="analyst",
        source_agent_id="host-expert",
        source_thread_id="thr_room_9",
        message="plot last week's trend",
        user_id=7,
        metadata={"session_key": "host-expert:app:7:room:9", "surface": "room"},
    )

    while len(gateway.pushes) < 2:
        await asyncio.sleep(0.01)

    print("=== same push path, two surfaces ===")
    for surface, thread_id, _text in gateway.pushes:
        print(f"  {surface:4} → {thread_id}")
    print(f"room transcript extras (host/Octop only): {len(processor.room_transcript)}")

    await inbox.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
