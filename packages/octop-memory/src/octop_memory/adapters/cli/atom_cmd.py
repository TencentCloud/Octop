"""Memory CLI: ``atom`` subcommand group for L2 AtomCards.

Read-only inspection commands. Atoms are produced by the M2.5 promotion
worker (``memory candidate promote``); they are NEVER manually inserted
via this CLI — the only way an atom enters the store is through promotion.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.types import AtomCard


def _atom_to_dict(a: AtomCard) -> dict[str, Any]:
    return {
        "id": a.id,
        "entity_id": a.entity_id,
        "candidate_id": a.candidate_id,
        "raw_event_ids": a.raw_event_ids,
        "assertion": a.assertion,
        "verbatim_quote": a.verbatim_quote,
        "quote_event_id": a.quote_event_id,
        "search_terms": a.search_terms,
        "occurred_at": a.occurred_at.isoformat(),
        "confidence": a.confidence,
        "importance": a.importance,
        "created_at": a.created_at.isoformat(),
        "superseded_by": a.superseded_by,
        "deprecated_at": a.deprecated_at.isoformat() if a.deprecated_at else None,
    }


@click.group(name="atom")
def atom_group() -> None:
    """Inspect L2 atoms (promoted candidates)."""


@atom_group.command(name="list")
@click.option("--entity-id", default=None, help="Filter atoms hanging off this entity.")
@click.option(
    "--importance",
    type=click.Choice(["low", "medium", "high"]),
    default=None,
    help="Filter by importance level.",
)
@click.option(
    "--include-deprecated",
    is_flag=True,
    default=False,
    help="Show atoms that have been superseded.",
)
@click.option("--limit", default=50, show_default=True, type=int)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    entity_id: str | None,
    importance: str | None,
    include_deprecated: bool,
    limit: int,
) -> None:
    """List atoms (most recently created first via list_atoms ordering)."""
    memory = get_memory(ctx)
    atoms = memory.list_atoms(
        entity_id=entity_id,
        importance=importance,  # type: ignore[arg-type]
        include_deprecated=include_deprecated,
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_atom_to_dict(a) for a in atoms], ensure_ascii=False, indent=2))
        return

    if not atoms:
        click.echo("No atoms found.")
        return
    for a in atoms:
        flag = "DEPR" if a.deprecated_at else "    "
        click.echo(
            f"{a.id[:8]}  {flag}  [{a.importance:6s}/{a.confidence:6s}]  entity={a.entity_id[:8]}  {a.assertion[:80]}"
        )


@atom_group.command(name="show")
@click.argument("atom_id")
@click.pass_context
def show_cmd(ctx: click.Context, atom_id: str) -> None:
    """Show full details of an atom by id (full UUID required)."""
    memory = get_memory(ctx)
    a = memory.get_atom(atom_id)
    if a is None:
        click.echo(f"Atom {atom_id} not found.", err=True)
        sys.exit(1)

    if ctx.obj.get("output_json"):
        click.echo(json.dumps(_atom_to_dict(a), ensure_ascii=False, indent=2))
        return

    click.echo(f"id            : {a.id}")
    click.echo(f"entity_id     : {a.entity_id}")
    click.echo(f"candidate_id  : {a.candidate_id}")
    click.echo(f"importance    : {a.importance}")
    click.echo(f"confidence    : {a.confidence}")
    click.echo(f"created_at    : {a.created_at.isoformat()}")
    click.echo(f"occurred_at   : {a.occurred_at.isoformat()}")
    if a.deprecated_at is not None:
        click.echo(f"deprecated_at : {a.deprecated_at.isoformat()}")
        click.echo(f"superseded_by : {a.superseded_by or '-'}")
    click.echo(f"raw_event_ids : {a.raw_event_ids}")
    click.echo(f"quote_event   : {a.quote_event_id}")
    click.echo(f"search_terms  : {a.search_terms}")
    click.echo("")
    click.echo("assertion:")
    click.echo(f"  {a.assertion}")
    click.echo("verbatim_quote:")
    click.echo(f"  {a.verbatim_quote}")


@atom_group.command(name="search")
@click.argument("query")
@click.option("--limit", default=10, show_default=True, type=int)
@click.option("--include-deprecated", is_flag=True, default=False)
@click.pass_context
def search_cmd(ctx: click.Context, query: str, limit: int, include_deprecated: bool) -> None:
    """FTS5 search over atom assertion + verbatim_quote + search_terms."""
    memory = get_memory(ctx)
    atoms = memory.search_atoms(query, include_deprecated=include_deprecated, limit=limit)

    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_atom_to_dict(a) for a in atoms], ensure_ascii=False, indent=2))
        return

    if not atoms:
        click.echo(f"No atoms matched {query!r}.")
        return
    for a in atoms:
        click.echo(f"{a.id[:8]}  [{a.importance}]  entity={a.entity_id[:8]}  {a.assertion[:80]}")
