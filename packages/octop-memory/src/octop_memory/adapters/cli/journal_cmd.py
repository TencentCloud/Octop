"""Memory CLI: ``journal`` subcommand group for L4 audit log.

Read-only — journal is append-only by design and the worker is the only
writer. This CLI exists for debugging / replay (D-?), not for end-user
operation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, get_args

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.types import JournalAction, JournalEntry

NOTE_PREVIEW_LEN = 60
"""Max characters of journal note shown in the CLI table view."""


def _entry_to_dict(e: JournalEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "timestamp": e.timestamp.isoformat(),
        "action": e.action,
        "actor": e.actor,
        "target_entity_id": e.target_entity_id,
        "target_atom_id": e.target_atom_id,
        "target_candidate_id": e.target_candidate_id,
        "before": e.before,
        "after": e.after,
        "note": e.note,
    }


@click.group(name="journal")
def journal_group() -> None:
    """Inspect L4 audit log (append-only)."""


@journal_group.command(name="list")
@click.option(
    "--action",
    type=click.Choice(list(get_args(JournalAction))),
    default=None,
    help="Filter to one action type.",
)
@click.option("--target-entity", "target_entity_id", default=None)
@click.option("--target-atom", "target_atom_id", default=None)
@click.option("--target-candidate", "target_candidate_id", default=None)
@click.option(
    "--since",
    default=None,
    help="ISO 8601 datetime or short duration like '24h' / '7d' / '30m'.",
)
@click.option("--limit", default=100, show_default=True, type=int)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    action: str | None,
    target_entity_id: str | None,
    target_atom_id: str | None,
    target_candidate_id: str | None,
    since: str | None,
    limit: int,
) -> None:
    """List journal entries (oldest-first within the window)."""
    memory = get_memory(ctx)
    after = _parse_since(since) if since else None
    entries = memory.list_journal(
        action=action,  # type: ignore[arg-type]
        target_entity_id=target_entity_id,
        target_atom_id=target_atom_id,
        target_candidate_id=target_candidate_id,
        after=after,
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_entry_to_dict(e) for e in entries], ensure_ascii=False, indent=2))
        return

    if not entries:
        click.echo("No journal entries found.")
        return
    for e in entries:
        cand = e.target_candidate_id[:8] if e.target_candidate_id else "-"
        atom = e.target_atom_id[:8] if e.target_atom_id else "-"
        ent = e.target_entity_id[:8] if e.target_entity_id else "-"
        note = (e.note[:NOTE_PREVIEW_LEN] + "…") if e.note and len(e.note) > NOTE_PREVIEW_LEN else (e.note or "")
        click.echo(
            f"{e.timestamp.isoformat()}  {e.action:10s} by {e.actor:5s}  cand={cand} atom={atom} ent={ent}  {note}"
        )


def _parse_since(spec: str) -> datetime:
    """Accept ISO datetime or '24h' / '7d' / '30m'."""
    spec = spec.strip()
    if spec[-1:].isalpha():
        unit = spec[-1].lower()
        try:
            value = int(spec[:-1])
        except ValueError as e:
            raise click.BadParameter(f"--since: invalid: {spec!r}") from e
        delta_map = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}
        if unit not in delta_map:
            raise click.BadParameter(f"--since: unsupported unit {unit!r} (use m / h / d)")
        return datetime.now().astimezone() - delta_map[unit]
    try:
        return datetime.fromisoformat(spec)
    except ValueError as e:
        raise click.BadParameter(f"--since: invalid ISO 8601 datetime: {spec!r}") from e
