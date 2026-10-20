"""Memory CLI: ``recall`` subcommand for M4 v2 pipeline.

Lets you preview the recall pipeline for a given query without
running it through the host LLM. Useful for:

- Eyeballing what the prompt would receive.
- Tuning rerank weights via ``--weights``.
- Testing co-reference: pass ``--thread-id`` so the active stack is
  consulted (and updated).

Output modes:
- text (default): rendered markdown block + per-snippet metadata.
- ``--json``: machine-readable for piping into downstream tools.
"""

from __future__ import annotations

import json
from typing import Any

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.pipeline.recall import recall_for_prompt

RECALL_WEIGHT_COUNT = 5
"""Number of rerank weight factors expected by --weights option."""


def _parse_weights(spec: str | None) -> tuple[float, float, float, float, float] | None:
    """Parse ``--weights w1,w2,w3,w4,w5`` into a 5-tuple of floats."""
    if not spec:
        return None
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != RECALL_WEIGHT_COUNT:
        raise click.BadParameter(
            f"--weights expects {RECALL_WEIGHT_COUNT} comma-separated floats "
            f"(got {len(parts)}); e.g. '0.4,0.2,0.15,0.15,0.1'"
        )
    try:
        floats = tuple(float(p) for p in parts)
    except ValueError as exc:
        raise click.BadParameter(f"--weights values must be floats: {exc}") from exc
    return (floats[0], floats[1], floats[2], floats[3], floats[4])


@click.command(name="recall")
@click.argument("query", required=True)
@click.option("--thread-id", default=None, help="Thread id for co-reference + active-entity stack.")
@click.option("--limit", default=5, show_default=True, type=int, help="Max snippets returned.")
@click.option(
    "--weights",
    default=None,
    help="Override rerank weights as 'bm25,importance,confidence,recency,layer'. "
    "Default: 0.40,0.20,0.15,0.15,0.10 (D38-A).",
)
@click.option("--per-entity-cap", default=3, show_default=True, type=int, help="Diversifier cap.")
@click.option(
    "--budget-tokens",
    default=1500,
    show_default=True,
    type=int,
    help="Token budget for the recall block (D45-A static char proxy).",
)
@click.option("--budget-ms", default=200, show_default=True, type=int, help="Total recall hard timeout.")
@click.pass_context
def recall_cmd(
    ctx: click.Context,
    query: str,
    thread_id: str | None,
    limit: int,
    weights: str | None,
    per_entity_cap: int,
    budget_tokens: int,
    budget_ms: int,
) -> None:
    """Run the M4 recall pipeline for QUERY."""
    memory = get_memory(ctx)
    parsed_weights = _parse_weights(weights)
    result = recall_for_prompt(
        memory,
        query,
        thread_id=thread_id,
        limit=limit,
        weights=parsed_weights,
        per_entity_cap=per_entity_cap,
        total_budget_tokens=budget_tokens,
        total_budget_ms=budget_ms,
    )

    if ctx.obj.get("output_json"):
        payload: dict[str, Any] = {
            "query": query,
            "thread_id": thread_id,
            "snippets": [
                {
                    "source_id": s.source_id,
                    "layer": s.layer,
                    "role_hint": s.role_hint,
                    "timestamp_iso": s.timestamp_iso,
                    "text": s.text,
                }
                for s in result.snippets
            ],
            "rendered": result.rendered,
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not result.snippets:
        click.echo("(no snippets matched)")
        return

    click.echo(f"query     : {query}")
    if thread_id:
        click.echo(f"thread_id : {thread_id}")
    click.echo(f"snippets  : {len(result.snippets)}")
    click.echo("")
    for idx, s in enumerate(result.snippets, 1):
        click.echo(f"{idx}. [{s.layer}] {s.role_hint}  @ {s.timestamp_iso}")
        click.echo(f"   {s.text}")
    click.echo("")
    click.echo("--- rendered block ---")
    click.echo(result.rendered)


__all__ = ["recall_cmd"]
