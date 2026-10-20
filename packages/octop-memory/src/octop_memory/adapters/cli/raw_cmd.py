"""Memory CLI: `raw` subcommand group for L0 raw events."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, get_args

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.types import RawEvent, RawEventType

_EVENT_TYPES = list(get_args(RawEventType))

SNIPPET_MAX_LEN = 80
"""Max characters of raw event content shown in the CLI list view."""


def _raw_to_dict(e: RawEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "host": e.host,
        "session_id": e.session_id,
        "thread_id": e.thread_id,
        "user": e.user,
        "timestamp": e.timestamp.isoformat(),
        "event_type": e.event_type,
        "content": e.content,
        "payload": e.payload,
    }


def _parse_payload(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--payload must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.BadParameter("--payload must be a JSON object (got array/scalar)")
    return parsed


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter(f"invalid ISO 8601 datetime: {value!r}") from exc


@click.group(name="raw")
def raw_group() -> None:
    """Inspect / manage L0 raw events."""


@raw_group.command(name="add")
@click.option("--content", required=True, help="Event content, or '-' to read from stdin.")
@click.option(
    "--event-type",
    "event_type",
    type=click.Choice(_EVENT_TYPES, case_sensitive=False),
    default="manual",
    show_default=True,
)
@click.option("--host", default="manual", show_default=True)
@click.option("--session-id", default=None)
@click.option("--thread-id", default=None)
@click.option("--user", default=None)
@click.option(
    "--timestamp",
    "timestamp_raw",
    default=None,
    help="ISO 8601 datetime; defaults to now(UTC).",
)
@click.option(
    "--payload",
    "payload_raw",
    default=None,
    help='Payload as JSON object, e.g. \'{"role":"user"}\'.',
)
@click.pass_context
def add_cmd(
    ctx: click.Context,
    content: str,
    event_type: str,
    host: str,
    session_id: str | None,
    thread_id: str | None,
    user: str | None,
    timestamp_raw: str | None,
    payload_raw: str | None,
) -> None:
    """Append a raw event (mostly for testing / manual ingest)."""
    output_json: bool = ctx.obj["output_json"]
    if content == "-":
        content = sys.stdin.read()

    payload = _parse_payload(payload_raw)
    timestamp = _parse_iso(timestamp_raw)

    memory = get_memory(ctx)
    event = memory.add_raw(
        content,
        event_type=event_type,  # type: ignore[arg-type]
        host=host,
        session_id=session_id,
        thread_id=thread_id,
        user=user,
        timestamp=timestamp,
        payload=payload,
    )

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": _raw_to_dict(event)}))
    else:
        click.echo(f"Added raw event: {event.id}")


@raw_group.command(name="show")
@click.argument("event_id")
@click.pass_context
def show_cmd(ctx: click.Context, event_id: str) -> None:
    """Show a raw event by id."""
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)
    event = memory.get_raw(event_id)

    if event is None:
        if output_json:
            click.echo(json.dumps({"status": "error", "error": "not found"}))
        else:
            click.echo(f"Raw event not found: {event_id}", err=True)
        ctx.exit(1)
        return

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": _raw_to_dict(event)}))
    else:
        click.echo(f"[{event.timestamp.isoformat()}] {event.host} / {event.event_type}")
        click.echo(f"  id={event.id}")
        if event.session_id:
            click.echo(f"  session={event.session_id}")
        if event.user:
            click.echo(f"  user={event.user}")
        click.echo(f"  content: {event.content}")
        if event.payload:
            click.echo(f"  payload: {json.dumps(event.payload, ensure_ascii=False)}")


@raw_group.command(name="list")
@click.option("--host", default=None)
@click.option("--session-id", default=None)
@click.option("--thread-id", default=None)
@click.option("--user", default=None)
@click.option(
    "--event-type",
    "event_type",
    type=click.Choice(_EVENT_TYPES, case_sensitive=False),
    default=None,
)
@click.option("--after", "after_raw", default=None, help="ISO 8601 datetime, inclusive.")
@click.option("--before", "before_raw", default=None, help="ISO 8601 datetime, inclusive.")
@click.option("--limit", default=20, show_default=True)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    host: str | None,
    session_id: str | None,
    thread_id: str | None,
    user: str | None,
    event_type: str | None,
    after_raw: str | None,
    before_raw: str | None,
    limit: int,
) -> None:
    """List raw events (most recent first)."""
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)

    events = memory.list_raw(
        host=host,
        session_id=session_id,
        thread_id=thread_id,
        user=user,
        event_type=event_type,  # type: ignore[arg-type]
        after=_parse_iso(after_raw),
        before=_parse_iso(before_raw),
        limit=limit,
    )

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"events": [_raw_to_dict(e) for e in events]}}))
        return

    if not events:
        click.echo("(no events)")
        return
    for e in events:
        snippet = e.content if len(e.content) <= SNIPPET_MAX_LEN else e.content[: SNIPPET_MAX_LEN - 3] + "..."
        click.echo(f"{e.timestamp.isoformat()}  {e.host:8s}  {e.event_type:18s}  {snippet}")
        click.echo(f"  id={e.id}")


@raw_group.command(name="search")
@click.argument("query")
@click.option("--limit", default=10, show_default=True)
@click.pass_context
def search_cmd(ctx: click.Context, query: str, limit: int) -> None:
    """FTS search over raw event content."""
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)
    events = memory.search_raw(query, limit=limit)

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"events": [_raw_to_dict(e) for e in events]}}))
        return

    if not events:
        click.echo("(no results)")
        return
    for e in events:
        snippet = e.content if len(e.content) <= SNIPPET_MAX_LEN else e.content[: SNIPPET_MAX_LEN - 3] + "..."
        click.echo(f"{e.timestamp.isoformat()}  {e.host:8s}  {snippet}")
        click.echo(f"  id={e.id}")
