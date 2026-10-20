"""Memory CLI: ``page`` subcommand group for L3 entity pages (M3).

Subcommands:

- ``memory page show <entity_id>`` — display the current page (markdown + meta).
- ``memory page regen --dirty [--limit N]`` — drive the D33-B async cron
  worker; pulls dirty pages and regenerates them via the host LLM.
- ``memory page regen <entity_id>`` — force a single regen.
- ``memory page edit <entity_id>`` — open the markdown body in $EDITOR
  and persist the user's changes (D34-A — preserves ``## My Notes``).
- ``memory page list-dirty`` — read-only view of pending regenerations.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from octop_memory.adapters.cli.candidate_cmd import _parse_dev_llm
from octop_memory.adapters.cli.config import get_memory
from octop_memory.pipeline.page import (
    PageRegenResult,
    regenerate_dirty,
    regenerate_page,
)
from octop_memory.ports.llm._protocol import LLMClient, NoopLLMClient
from octop_memory.types import EntityPage, JournalEntry


def _page_to_dict(p: EntityPage) -> dict[str, Any]:
    return {
        "id": p.id,
        "entity_id": p.entity_id,
        "headline": p.headline,
        "topics": p.topics,
        "dirty": p.dirty,
        "summary_version": p.summary_version,
        "regen_attempt_count": p.regen_attempt_count,
        "last_regen_at": p.last_regen_at.isoformat() if p.last_regen_at else None,
        "last_user_edit_at": p.last_user_edit_at.isoformat() if p.last_user_edit_at else None,
        "summary_markdown": p.summary_markdown,
    }


def _resolve_llm(dev_llm: str | None) -> LLMClient:
    """Pick the LLM client for an interactive ``page regen`` session.

    Reuses the candidate-CLI ``--dev-llm`` syntax so dogfood can run with
    the same DeepSeek / Ollama setup the candidate extractor uses.
    Production callers will inject the host's adapter in M3.6+.

    ``dev_llm`` accepts:
    - ``None`` → :class:`NoopLLMClient` (regen records failure)
    - ``"ollama:<model>"`` → local Ollama
    - ``"remote:<base_url>:<model>"`` → OpenAI-compatible remote
    """
    if dev_llm is None:
        return NoopLLMClient()
    return _parse_dev_llm(dev_llm)


@click.group(name="page")
def page_group() -> None:
    """Inspect and regenerate L3 entity pages."""


@page_group.command(name="show")
@click.argument("entity_id")
@click.pass_context
def show_cmd(ctx: click.Context, entity_id: str) -> None:
    """Show the entity page (markdown + meta)."""
    memory = get_memory(ctx)
    page = memory.get_entity_page(entity_id)
    if page is None:
        click.echo(f"No page for entity {entity_id}.", err=True)
        sys.exit(1)

    if ctx.obj.get("output_json"):
        click.echo(json.dumps(_page_to_dict(page), ensure_ascii=False, indent=2))
        return

    entity = memory.get_entity(entity_id)
    name = entity.canonical_name if entity else "(unknown entity)"

    click.echo(f"entity         : {name}  [{entity_id}]")
    click.echo(f"headline       : {page.headline}")
    click.echo(f"topics         : {', '.join(page.topics) if page.topics else '-'}")
    click.echo(f"dirty          : {page.dirty}  (attempts={page.regen_attempt_count})")
    click.echo(f"summary_version: {page.summary_version}")
    click.echo(f"last_regen_at  : {page.last_regen_at.isoformat() if page.last_regen_at else '-'}")
    click.echo(f"last_user_edit : {page.last_user_edit_at.isoformat() if page.last_user_edit_at else '-'}")
    click.echo("")
    click.echo("--- summary_markdown ---")
    click.echo(page.summary_markdown or "(empty)")


@page_group.command(name="list-dirty")
@click.option("--limit", default=50, show_default=True, type=int)
@click.pass_context
def list_dirty_cmd(ctx: click.Context, limit: int) -> None:
    """List pages awaiting regeneration."""
    memory = get_memory(ctx)
    pages = memory.list_dirty_entity_pages(limit=limit)
    if ctx.obj.get("output_json"):
        click.echo(json.dumps([_page_to_dict(p) for p in pages], ensure_ascii=False, indent=2))
        return
    if not pages:
        click.echo("No dirty pages.")
        return
    for p in pages:
        last = p.last_regen_at.isoformat() if p.last_regen_at else "never"
        click.echo(
            f"{p.entity_id[:8]}  v{p.summary_version}  attempts={p.regen_attempt_count}  "
            f"last_regen={last}  headline={p.headline[:30]!r}"
        )


@page_group.command(name="regen")
@click.argument("entity_id", required=False)
@click.option("--dirty", "all_dirty", is_flag=True, default=False, help="Regenerate all dirty pages instead of one.")
@click.option("--limit", default=20, show_default=True, type=int, help="Max pages to regen when --dirty is set.")
@click.option(
    "--dev-llm",
    "dev_llm",
    default=None,
    help=(
        "Dev-only LLM client for the regen step. "
        "Format: 'ollama:<model>' or 'remote:<base_url>:<model>'. "
        "Without this flag the CLI uses a no-op client (regen will record failure)."
    ),
)
@click.pass_context
def regen_cmd(
    ctx: click.Context,
    entity_id: str | None,
    all_dirty: bool,
    limit: int,
    dev_llm: str | None,
) -> None:
    """Drive the LLM page regenerator (D33-B async cron entry point)."""
    if not all_dirty and not entity_id:
        raise click.UsageError("Provide ENTITY_ID or use --dirty to process all dirty pages.")
    if all_dirty and entity_id:
        raise click.UsageError("--dirty and ENTITY_ID are mutually exclusive.")

    memory = get_memory(ctx)
    llm = _resolve_llm(dev_llm)

    if all_dirty:
        batch = regenerate_dirty(memory, llm=llm, limit=limit)
        if ctx.obj.get("output_json"):
            click.echo(
                json.dumps(
                    {
                        "success_count": batch.success_count,
                        "failure_count": batch.failure_count,
                        "llm_calls": batch.llm_calls,
                        "results": [_result_to_dict(r) for r in batch.results],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        click.echo(f"Processed {len(batch.results)} pages: ok={batch.success_count} fail={batch.failure_count}")
        for r in batch.results:
            tag = "ok " if r.success else "FAIL"
            click.echo(f"  [{tag}] {r.entity_id[:8]}  {r.reason}")
        return

    assert entity_id is not None
    result = regenerate_page(memory, entity_id, llm=llm)
    if ctx.obj.get("output_json"):
        click.echo(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2))
        return
    click.echo(f"entity_id : {result.entity_id}")
    click.echo(f"success   : {result.success}")
    click.echo(f"reason    : {result.reason}")
    if result.success:
        click.echo(f"headline  : {result.headline}")
        click.echo(f"topics    : {', '.join(result.topics)}")
        click.echo("")
        click.echo("--- summary_markdown ---")
        click.echo(result.summary_markdown)


@page_group.command(name="edit")
@click.argument("entity_id")
@click.pass_context
def edit_cmd(ctx: click.Context, entity_id: str) -> None:
    """Open the page summary in $EDITOR; save → apply user edit (D34-A)."""
    memory = get_memory(ctx)
    page = memory.get_entity_page(entity_id)
    if page is None:
        click.echo(f"No page for entity {entity_id}; run `memory page regen {entity_id}` first.", err=True)
        sys.exit(1)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    # Resolve $EDITOR to an executable path to avoid command injection.
    # Only keep the first token and confirm it is available via shutil.which.
    editor_cmd = shlex.split(editor)[0]
    editor_resolved = shutil.which(editor_cmd)
    if not editor_resolved:
        click.echo(f"Editor {editor_cmd!r} not found in PATH; aborting.", err=True)
        sys.exit(1)
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w+", delete=False, encoding="utf-8") as tmp:
        tmp.write(page.summary_markdown)
        tmp.flush()  # Flush content before opening the temp file in the editor.
        tmp_path = Path(tmp.name)

    try:
        completed = subprocess.run([editor_resolved, str(tmp_path)], check=False)
        if completed.returncode != 0:
            click.echo(f"Editor exited with status {completed.returncode}; not saving.", err=True)
            sys.exit(completed.returncode)

        new_body = tmp_path.read_text(encoding="utf-8")
    finally:
        with contextlib.suppress(OSError):
            tmp_path.unlink()

    if new_body == page.summary_markdown:
        click.echo("No changes.")
        return

    ok = memory.apply_entity_page_user_edit(entity_id, summary_markdown=new_body)
    if not ok:
        click.echo("Edit failed: page row missing.", err=True)
        sys.exit(1)

    memory.append_journal(
        JournalEntry(
            id=f"page_edit_{entity_id}_{datetime.now(UTC).isoformat()}",
            timestamp=datetime.now(UTC),
            action="page_user_edit",
            actor="user",
            target_entity_id=entity_id,
            note="user edit applied via `memory page edit`",
        )
    )
    click.echo(f"Saved {len(new_body)} chars; summary_version bumped.")


def _result_to_dict(r: PageRegenResult) -> dict[str, Any]:
    return {
        "entity_id": r.entity_id,
        "success": r.success,
        "reason": r.reason,
        "headline": r.headline,
        "topics": r.topics,
        "summary_markdown": r.summary_markdown,
        "llm_calls": r.llm_calls,
    }


__all__ = ["page_group"]
