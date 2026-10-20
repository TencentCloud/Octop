"""Memory CLI: ``entity`` subcommand group for L3 entity anchors.

Inspection only — entities are auto-created by the promotion worker
during candidate.subject resolution. Long-form summaries live in the
separate ``EntityPage`` table and are managed by the ``page`` commands.
"""

from __future__ import annotations

import json
import sys
from typing import Any, get_args

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.types import Entity, EntityType


def _entity_to_dict(e: Entity) -> dict[str, Any]:
    return {
        "id": e.id,
        "entity_type": e.entity_type,
        "canonical_name": e.canonical_name,
        "aliases": e.aliases,
        "atom_count": e.atom_count,
        "last_promoted_at": e.last_promoted_at.isoformat() if e.last_promoted_at else None,
        "created_at": e.created_at.isoformat(),
    }


@click.group(name="entity")
def entity_group() -> None:
    """Inspect L3 entities (anchors for atoms)."""


@entity_group.command(name="list")
@click.option(
    "--type",
    "entity_type",
    type=click.Choice(list(get_args(EntityType))),
    default=None,
    help="Filter by entity_type.",
)
@click.option("--limit", default=100, show_default=True, type=int)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    entity_type: str | None,
    limit: int,
) -> None:
    """List entities (alphabetical by canonical_name)."""
    memory = get_memory(ctx)
    entities = memory.list_entities(
        entity_type=entity_type,  # type: ignore[arg-type]
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_entity_to_dict(e) for e in entities], ensure_ascii=False, indent=2))
        return

    if not entities:
        click.echo("No entities found.")
        return
    for e in entities:
        click.echo(f"{e.id[:8]}  {e.entity_type:10s}  atoms={e.atom_count:3d}  {e.canonical_name}")


@entity_group.command(name="show")
@click.argument("entity_id")
@click.pass_context
def show_cmd(ctx: click.Context, entity_id: str) -> None:
    """Show entity details + its non-deprecated atoms (full UUID required)."""
    memory = get_memory(ctx)
    e = memory.get_entity(entity_id)
    if e is None:
        click.echo(f"Entity {entity_id} not found.", err=True)
        sys.exit(1)

    atoms = memory.list_atoms(entity_id=entity_id, limit=200)
    aliases = memory.list_aliases(entity_id=entity_id, limit=50)

    if ctx.obj.get("output_json"):
        click.echo(
            json.dumps(
                {
                    "entity": _entity_to_dict(e),
                    "atoms": [
                        {
                            "id": a.id,
                            "importance": a.importance,
                            "confidence": a.confidence,
                            "assertion": a.assertion,
                            "deprecated": a.deprecated_at is not None,
                        }
                        for a in atoms
                    ],
                    "aliases": [{"alias": al.alias, "created_by": al.created_by} for al in aliases],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    click.echo(f"id             : {e.id}")
    click.echo(f"type           : {e.entity_type}")
    click.echo(f"canonical_name : {e.canonical_name}")
    click.echo(f"atom_count     : {e.atom_count}")
    click.echo(f"created_at     : {e.created_at.isoformat()}")
    click.echo(f"last_promoted  : {e.last_promoted_at.isoformat() if e.last_promoted_at else '-'}")
    click.echo("")
    click.echo(f"aliases ({len(aliases)}):")
    for al in aliases:
        click.echo(f"  - {al.alias!r} (by {al.created_by})")
    click.echo("")
    click.echo(f"atoms ({len(atoms)}):")
    for a in atoms:
        flag = " DEPR" if a.deprecated_at else "     "
        click.echo(f"  - {a.id[:8]}{flag}  [{a.importance:6s}]  {a.assertion[:80]}")
