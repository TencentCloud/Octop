"""octop chats — thread CRUD + interactive REPL (CLI channel / local DB)."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click

from octop.cli.support.ctx import json_output_enabled, require_agent
from octop.infra.utils.paths import PathLayout


def _run_turn(
    agent_id: str,
    prompt: str,
    *,
    session_key: str,
    thread_id: str | None,
    model: str | None = None,
    conversation_mode: str | None = None,
    plain: bool = False,
    as_user: str | None = None,
) -> Any:
    import asyncio

    from octop.cli.repl.render import ChunkRenderer
    from octop.cli.repl.runtime import run_chat_turn_async
    from octop.cli.repl.turn import ChatTurnResult

    renderer = ChunkRenderer(plain=plain)
    renderer.begin_turn()
    actions: list[dict[str, Any]] = []

    def on_chunk(chunk: dict[str, Any]) -> None:
        if chunk.get("type") == "slash_action":
            actions.append(chunk)
        renderer.feed(chunk)

    asyncio.run(
        run_chat_turn_async(
            agent_id,
            prompt,
            as_user=as_user,
            session_key=session_key,
            thread_id=thread_id,
            model=model,
            conversation_mode=conversation_mode,
            on_chunk=on_chunk,
        )
    )
    renderer.finish_turn()
    return ChatTurnResult(
        text=renderer.token_buffer or "",
        actions=actions,
        elapsed=renderer.last_elapsed,
    )


def _apply_slash_actions(
    result: Any,
    *,
    agent_id: str,
    repl_state: Any | None = None,
    model_holder: list[str | None] | None = None,
) -> str:
    """Apply slash side-effects; return possibly updated agent_id."""
    holder: list[str | None] = model_holder if model_holder is not None else [None]
    for act in result.actions:
        name = str(act.get("action", ""))
        if name == "switch_agent" and act.get("agent_id"):
            agent_id = str(act["agent_id"])
            click.echo(click.style(f"switched agent → {agent_id}", fg="cyan"))
        elif name == "set_model" and act.get("model"):
            holder[0] = str(act["model"])
            click.echo(click.style(f"model → {holder[0]}", fg="cyan"))
        elif name == "clear_model":
            holder[0] = None
            click.secho("model override cleared", fg="cyan")
        elif name == "new_chat" and repl_state is not None:
            repl_state.on_new_chat(act.get("thread_id"))
        elif name == "rebind_thread" and repl_state is not None:
            repl_state.on_rebind_thread(act.get("thread_id"))
        elif name == "set_conversation_mode" and repl_state is not None:
            mode = str(act.get("mode") or "").strip()
            if mode in ("ask", "plan", "craft"):
                repl_state.conversation_mode = mode
                click.echo(click.style(f"mode → {mode}", fg="cyan"))
    return agent_id


@click.group("chats")
def chats() -> None:
    """Thread list/history and interactive chat (CLI channel / local DB)."""


@chats.command("list")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None, help="Admin: act as user (username).")
@click.option("--limit", default=50, show_default=True)
def list_chats(agent_id: str | None, as_user: str | None, limit: int) -> None:
    """List conversation threads for an agent."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.db import list_threads_offline

    aid = require_agent(agent_id)
    try:
        rows = list_threads_offline(agent_id=aid, as_user=as_user, limit=limit)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Threads")
    for col in ("thread_id", "title", "is_active", "last_active"):
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row.get("thread_id", "")),
            row.get("title", "") or "",
            "✓" if row.get("is_active") else "",
            str(row.get("last_active", "") or ""),
        )
    Console(file=sys.stdout).print(table)


@chats.command("get")
@click.argument("thread_id")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None)
@click.option("--limit", default=50, show_default=True)
def get_chat(thread_id: str, agent_id: str | None, as_user: str | None, limit: int) -> None:
    """Show message history for a thread."""
    from octop.cli.support.embedded_ops import fetch_thread_history
    from octop.cli.support.offline_ops import resolve_cron_user_id
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        resolve_cron_user_id(aid, as_user)
        data = fetch_thread_history(aid, thread_id, limit=limit)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(data, indent=2, default=str))


@chats.command("create")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None)
def create_chat(agent_id: str | None, as_user: str | None) -> None:
    """Start a new thread (/new equivalent)."""
    from octop.cli.support.offline_ops import create_thread_offline, resolve_cron_user_id
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        uid = resolve_cron_user_id(aid, as_user)
        data = create_thread_offline(agent_id=aid, user_id=uid)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(data, indent=2))


@chats.command("update")
@click.argument("thread_id")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None)
@click.option("--title", default=None)
@click.option("--pinned/--unpinned", default=None)
def update_chat(
    thread_id: str,
    agent_id: str | None,
    as_user: str | None,
    title: str | None,
    pinned: bool | None,
) -> None:
    """Rename or pin a thread."""
    if title is None and pinned is None:
        raise click.ClickException("pass --title and/or --pinned/--unpinned")
    aid = require_agent(agent_id)
    from octop.cli.support.offline_ops import resolve_cron_user_id, update_thread_offline
    from octop.infra.errors import OctopError

    try:
        resolve_cron_user_id(aid, as_user)
        data = update_thread_offline(aid, thread_id, title=title, pinned=pinned)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(data, indent=2))


@chats.command("delete")
@click.argument("thread_id")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None)
@click.option("--yes", is_flag=True, default=False)
def delete_chat(thread_id: str, agent_id: str | None, as_user: str | None, yes: bool) -> None:
    """Delete a thread."""
    from octop.cli.support.offline_ops import delete_thread_offline, resolve_cron_user_id
    from octop.infra.errors import OctopError

    if not yes:
        click.confirm(f"Really delete thread {thread_id}?", abort=True)
    aid = require_agent(agent_id)
    try:
        resolve_cron_user_id(aid, as_user)
        delete_thread_offline(aid, thread_id)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo("deleted")


@chats.command("send")
@click.argument("prompt")
@click.option("--agent", "agent_id", default=None)
@click.option("--session-key", default="default")
@click.option("--thread-id", default=None, help="Pin this thread for every turn.")
@click.option("--model", default=None)
@click.option(
    "--mode",
    "conversation_mode",
    type=click.Choice(["ask", "plan", "craft"], case_sensitive=False),
    default=None,
    help="Ask (read-only), Plan (write plans/*.md), or Default (craft).",
)
@click.option("--plain", is_flag=True, help="Raw token stream (no Markdown finish).")
def send_chat(
    prompt: str,
    agent_id: str | None,
    session_key: str,
    thread_id: str | None,
    model: str | None,
    conversation_mode: str | None,
    plain: bool,
) -> None:
    """Send one message and stream the response (CLI channel)."""
    aid = require_agent(agent_id)
    _run_turn(
        aid,
        prompt,
        session_key=session_key,
        thread_id=thread_id,
        model=model,
        conversation_mode=conversation_mode,
        plain=plain,
    )


@chats.command("repl")
@click.option("--agent", "agent_id", default=None)
@click.option(
    "--user", "as_user", default=None, help="Act as user (username); defaults to agent owner."
)
@click.option("--session-key", default="cli")
@click.option("--thread-id", default=None, help="Pin this thread for every turn.")
@click.option("--model", default=None)
@click.option(
    "--mode",
    "conversation_mode",
    type=click.Choice(["ask", "plan", "craft"], case_sensitive=False),
    default=None,
    help="Ask (read-only), Plan (write plans/*.md), or Default (craft).",
)
@click.option("--plain", is_flag=True, help="Raw token stream (no Markdown finish).")
def repl(
    agent_id: str | None,
    as_user: str | None,
    session_key: str,
    thread_id: str | None,
    model: str | None,
    conversation_mode: str | None,
    plain: bool,
) -> None:
    """Interactive chat REPL (embedded server + CLI gateway channel)."""
    import asyncio

    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    from octop.cli.repl.embedded_session import embedded_chat_server
    from octop.cli.repl.render import print_slash_help, print_welcome
    from octop.cli.repl.runtime import (
        CliChatSession,
        resolve_embedded_user_id,
    )
    from octop.cli.repl.session import ReplSession
    from octop.cli.repl.toolbar import format_repl_toolbar

    aid = require_agent(agent_id)
    repl_state = ReplSession(
        agent_id=aid,
        session_key=session_key,
        model=model,
        thread_id=thread_id,
        conversation_mode=conversation_mode,
    )
    print_welcome(
        agent_id=aid,
        model=repl_state.model_label,
        session_key=session_key,
        thread_id=repl_state.thread_id,
    )

    history_path = PathLayout.from_env().root / "repl_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession[str] = PromptSession(
        history=FileHistory(str(history_path)),
        bottom_toolbar=lambda: format_repl_toolbar(repl_state),
    )

    async def _run_repl_turn(chat: CliChatSession, agent: str, text: str) -> Any:
        from octop.cli.repl.render import ChunkRenderer
        from octop.cli.repl.turn import ChatTurnResult

        renderer = ChunkRenderer(plain=plain)
        renderer.begin_turn()
        actions: list[dict[str, Any]] = []

        def on_chunk(chunk: dict[str, Any]) -> None:
            if chunk.get("type") == "slash_action":
                actions.append(chunk)
            renderer.feed(chunk)

        await chat.run_turn(
            agent,
            text,
            session_key=session_key,
            thread_id=repl_state.thread_id_for_send(),
            model=repl_state.model,
            conversation_mode=repl_state.conversation_mode,
            on_chunk=on_chunk,
        )
        renderer.finish_turn()
        return ChatTurnResult(
            text=renderer.token_buffer or "",
            actions=actions,
            elapsed=renderer.last_elapsed,
        )

    async def _loop() -> None:
        async with embedded_chat_server() as server:
            user_id = resolve_embedded_user_id(server, agent_id=aid, as_user=as_user)
            chat = CliChatSession(server, user_id=user_id)
            current_agent = aid
            try:
                while True:
                    try:
                        text = await asyncio.to_thread(session.prompt, "> ")
                    except (EOFError, KeyboardInterrupt):
                        click.echo("\nbye")
                        break
                    text = text.strip()
                    if not text:
                        continue
                    if text in ("/exit", "/quit"):
                        break
                    if text == "/help":
                        print_slash_help()
                        continue
                    if text == "/clear":
                        click.echo()
                        continue
                    if text == "/thread":
                        tid = repl_state.thread_id
                        if tid:
                            pin = " (pinned)" if repl_state.pin_thread else ""
                            click.echo(f"{tid}{pin}")
                        else:
                            click.echo("(server binds thread via session_key)")
                        continue
                    click.echo()
                    result = await _run_repl_turn(chat, current_agent, text)
                    repl_state.last_elapsed = result.elapsed
                    repl_state.apply_slash_text(result.text)
                    model_holder: list[str | None] = [repl_state.model]
                    current_agent = _apply_slash_actions(
                        result,
                        agent_id=current_agent,
                        repl_state=repl_state,
                        model_holder=model_holder,
                    )
                    repl_state.agent_id = current_agent
                    repl_state.model = model_holder[0]
                    if session.app is not None:
                        session.app.invalidate()
                    click.echo()
            finally:
                chat.close()

    asyncio.run(_loop())
