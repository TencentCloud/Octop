"""Embedded OctopServer chat runtime via the CLI gateway channel."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from octop.cli.repl.embedded_session import embedded_runtime
from octop.cli.repl.turn import ChatTurnResult
from octop.infra.gateway.cli import CLI_CHANNEL_ID
from octop.infra.gateway.cli.turn import build_cli_inbound, prepare_cli_turn
from octop.infra.server import OctopServer


def resolve_embedded_user_id(
    server: OctopServer,
    *,
    agent_id: str,
    as_user: str | None,
) -> int:
    """Pick acting user: explicit ``--user``, CLI state, or agent owner."""
    from octop.cli.support.ctx import resolve_user
    from octop.cli.support.state import default_state_path, load
    from octop.infra.users.acting import resolve_acting_user_id

    assert server.services is not None
    pinned = load(default_state_path()).default_user
    return resolve_acting_user_id(
        server.services,
        as_username=resolve_user(as_user),
        pinned_username=pinned,
        agent_id=agent_id,
    )


class CliChatSession:
    """One CLI connection into Gateway.cli_hub for streaming turns."""

    def __init__(self, server: OctopServer, *, user_id: int) -> None:
        if server.app_runtime is None:
            raise RuntimeError("server not started")
        self._server = server
        self._user_id = user_id
        self._gateway = server.app_runtime.gateway
        self._connection_id = uuid.uuid4().hex
        self._done = asyncio.Event()
        self._on_chunk: Callable[[dict[str, Any]], None] | None = None
        self._gateway.cli_hub.register(self._connection_id, self._deliver_chunk)

    async def _deliver_chunk(self, frame: dict[str, Any]) -> None:
        if self._on_chunk is not None:
            self._on_chunk(frame)
        if frame.get("type") in ("done", "error"):
            self._done.set()

    def close(self) -> None:
        self._gateway.cli_hub.unregister(self._connection_id)

    async def run_turn(
        self,
        agent_id: str,
        text: str,
        *,
        session_key: str,
        thread_id: str | None,
        model: str | None,
        conversation_mode: str | None = None,
        on_chunk: Callable[[dict[str, Any]], None],
    ) -> ChatTurnResult:
        channel_manager = self._gateway.channel_manager
        if channel_manager is None:
            raise RuntimeError("gateway not ready")

        user_row = (
            self._server.services.user_repo.get(self._user_id) if self._server.services else None
        )
        user_is_admin = bool(user_row and user_row.role == "admin")

        tid, sk = await prepare_cli_turn(
            self._gateway.thread_registry,
            agent_id=agent_id,
            user_id=self._user_id,
            thread_id=thread_id,
            session_key=session_key,
        )
        inbound = build_cli_inbound(
            agent_id=agent_id,
            user_id=self._user_id,
            text=text,
            session_key=sk,
            thread_id=tid,
            cli_connection_id=self._connection_id,
            model=model,
            conversation_mode=conversation_mode,
            user_is_admin=user_is_admin,
        )

        self._done.clear()
        self._on_chunk = on_chunk
        channel_manager.enqueue(CLI_CHANNEL_ID, inbound)
        await self._done.wait()
        self._on_chunk = None
        return ChatTurnResult()


async def run_chat_turn_async(
    agent_id: str,
    text: str,
    *,
    as_user: str | None,
    session_key: str,
    thread_id: str | None,
    model: str | None,
    conversation_mode: str | None = None,
    on_chunk: Callable[[dict[str, Any]], None],
) -> ChatTurnResult:
    async with embedded_runtime() as server:
        user_id = resolve_embedded_user_id(server, agent_id=agent_id, as_user=as_user)
        session = CliChatSession(server, user_id=user_id)
        try:
            return await session.run_turn(
                agent_id,
                text,
                session_key=session_key,
                thread_id=thread_id,
                model=model,
                conversation_mode=conversation_mode,
                on_chunk=on_chunk,
            )
        finally:
            session.close()
