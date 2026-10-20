"""Memory CLI command group."""

from __future__ import annotations

import json
import sys
from typing import Any, get_args

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.core import MemoryLevel
from octop_memory.storage.backends import _UNSET
from octop_memory.types import MemoryNode

_LEVEL_CHOICES = list(get_args(MemoryLevel))


def _node_to_dict(n: MemoryNode) -> dict[str, Any]:
    return {
        "id": n.id,
        "parent_id": n.parent_id,
        "level": n.level,
        "content": n.content,
        "topic": n.topic,
        "conversation_id": n.conversation_id,
        "created_at": n.created_at.isoformat(),
        "updated_at": n.updated_at.isoformat(),
        "metadata": n.metadata,
    }


def _parse_metadata(raw: str | None) -> dict[str, Any] | None:
    """Parse ``--metadata`` JSON. Must be a JSON object (not array/scalar)."""
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--metadata must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.BadParameter("--metadata must be a JSON object (got array/scalar)")
    return parsed


@click.group(name="memory")
def memory_group() -> None:
    """Manage memory nodes."""


@memory_group.command(name="store")
@click.option(
    "--content",
    required=True,
    help="Memory content, or '-' to read from stdin.",
)
@click.option("--topic", default=None, help="Topic or category for this memory.")
@click.option(
    "--level",
    type=click.Choice(_LEVEL_CHOICES, case_sensitive=False),
    default="leaf",
    show_default=True,
    help="Node level in the memory tree.",
)
@click.option("--parent", "parent_id", default=None, help="Parent node ID.")
@click.option(
    "--metadata",
    "metadata_raw",
    default=None,
    help='Metadata as a JSON object, e.g. \'{"confidence":"high"}\'.',
)
@click.pass_context
def store_cmd(
    ctx: click.Context,
    content: str,
    topic: str | None,
    level: str,
    parent_id: str | None,
    metadata_raw: str | None,
) -> None:
    """Store a new memory node."""
    output_json: bool = ctx.obj["output_json"]

    if content == "-":
        content = sys.stdin.read()

    metadata = _parse_metadata(metadata_raw)

    memory = get_memory(ctx)
    try:
        node = memory.store(
            content,
            topic=topic,
            level=level,  # type: ignore[arg-type]
            parent_id=parent_id,
            metadata=metadata,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": _node_to_dict(node)}))
    else:
        click.echo(f"Stored memory node: {node.id}")


@memory_group.command(name="get")
@click.argument("node_id")
@click.pass_context
def get_cmd(ctx: click.Context, node_id: str) -> None:
    """Fetch a memory node by id."""
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)
    node = memory.get(node_id)

    if node is None:
        if output_json:
            click.echo(json.dumps({"status": "error", "error": "not found"}))
        else:
            click.echo(f"Node not found: {node_id}", err=True)
        ctx.exit(1)
        return

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": _node_to_dict(node)}))
    else:
        topic_str = f" [{node.topic}]" if node.topic else ""
        click.echo(f"{node.level}: {node.content}{topic_str}")
        click.echo(f"  id={node.id}")
        if node.parent_id:
            click.echo(f"  parent={node.parent_id}")
        if node.metadata:
            click.echo(f"  metadata={json.dumps(node.metadata, ensure_ascii=False)}")


@memory_group.command(name="update")
@click.argument("node_id")
@click.option("--content", default=None, help="New content.")
@click.option(
    "--topic",
    "topic_raw",
    default=None,
    help="New topic. Pass empty string to clear.",
)
@click.option(
    "--metadata",
    "metadata_raw",
    default=None,
    help="New metadata JSON object (REPLACE semantics, not merge).",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    node_id: str,
    content: str | None,
    topic_raw: str | None,
    metadata_raw: str | None,
) -> None:
    """Update an existing memory node's mutable fields.

    parent_id and level are NOT mutable — that requires a future
    ``move`` API. Metadata semantics is REPLACE.
    """
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)

    # Topic: distinguish "unchanged" vs "explicit clear".
    topic_arg: Any = _UNSET if topic_raw is None else (topic_raw or None)
    metadata_arg: Any = _UNSET if metadata_raw is None else _parse_metadata(metadata_raw)

    if content is None and topic_arg is _UNSET and metadata_arg is _UNSET:
        raise click.UsageError("nothing to update; pass --content / --topic / --metadata")

    updated = memory.update(
        node_id,
        content=content,
        topic=topic_arg,
        metadata=metadata_arg,
    )
    if not updated:
        if output_json:
            click.echo(json.dumps({"status": "error", "error": "not found"}))
        else:
            click.echo(f"Node not found: {node_id}", err=True)
        ctx.exit(1)
        return

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"id": node_id, "updated": True}}))
    else:
        click.echo(f"Updated memory node: {node_id}")


@memory_group.command(name="delete")
@click.argument("node_id")
@click.option("--cascade", is_flag=True, default=False, help="Recursively delete subtree.")
@click.pass_context
def delete_cmd(ctx: click.Context, node_id: str, cascade: bool) -> None:
    """Delete a memory node. Refuses if it has children unless --cascade."""
    output_json: bool = ctx.obj["output_json"]
    memory = get_memory(ctx)

    try:
        deleted = memory.delete(node_id, cascade=cascade)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if not deleted:
        if output_json:
            click.echo(json.dumps({"status": "error", "error": "not found"}))
        else:
            click.echo(f"Node not found: {node_id}", err=True)
        ctx.exit(1)
        return

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"id": node_id, "deleted": True}}))
    else:
        click.echo(f"Deleted memory node: {node_id}")


@memory_group.command(name="tree")
@click.pass_context
def tree_cmd(ctx: click.Context) -> None:
    """Show the full memory tree."""
    output_json: bool = ctx.obj["output_json"]

    memory = get_memory(ctx)
    nodes = memory.get_tree()

    if output_json:
        # Backwards-compatible: flat list of nodes for script consumers.
        click.echo(json.dumps({"status": "ok", "data": {"nodes": [_node_to_dict(n) for n in nodes]}}))
        return

    if not nodes:
        click.echo("(empty)")
        return

    by_id = {n.id: n for n in nodes}
    children: dict[str | None, list[MemoryNode]] = {}
    for n in nodes:
        # Normalize "parent referencing a non-existent node" as orphan.
        parent_key: str | None = None if n.parent_id is None or n.parent_id not in by_id else n.parent_id
        children.setdefault(parent_key, []).append(n)

    for siblings in children.values():
        siblings.sort(key=lambda x: x.created_at)

    def _render(node: MemoryNode, prefix: str, is_last: bool) -> None:
        connector = "`-- " if is_last else "|-- "
        topic_str = f" [{node.topic}]" if node.topic else ""
        head = f"{prefix}{connector}{node.content}{topic_str} ({node.level}) <{node.id}>"
        click.echo(head)
        kids = children.get(node.id, [])
        for i, kid in enumerate(kids):
            extension = "    " if is_last else "|   "
            _render(kid, prefix + extension, i == len(kids) - 1)

    roots = children.get(None, [])
    for i, root in enumerate(roots):
        # Top-level nodes start with no connector.
        topic_str = f" [{root.topic}]" if root.topic else ""
        click.echo(f"{root.content}{topic_str} ({root.level}) <{root.id}>")
        kids = children.get(root.id, [])
        for j, kid in enumerate(kids):
            _render(kid, "", j == len(kids) - 1)
        if i != len(roots) - 1:
            click.echo("")


@memory_group.command(name="recall")
@click.argument("query")
@click.option("--limit", default=5, show_default=True, help="Maximum results.")
@click.pass_context
def recall_cmd(ctx: click.Context, query: str, limit: int) -> None:
    """Recall memories matching a query."""
    output_json: bool = ctx.obj["output_json"]

    memory = get_memory(ctx)
    nodes = memory.recall(query, limit=limit)

    if output_json:
        click.echo(json.dumps({"status": "ok", "data": {"nodes": [_node_to_dict(n) for n in nodes]}}))
    elif not nodes:
        click.echo("(no results)")
    else:
        for n in nodes:
            topic_str = f" [{n.topic}]" if n.topic else ""
            click.echo(f"{n.content}{topic_str}")
