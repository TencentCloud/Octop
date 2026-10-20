"""CLI commands for Episodes (M5 user-diary layer) and Digests."""

from __future__ import annotations

import json
import logging
from datetime import UTC
from pathlib import Path

import click

from octop_memory.adapters.cli.config import get_memory
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

logger = logging.getLogger(__name__)


@click.group("episode")
def episode_group() -> None:
    """Inspect and manage user-diary Episodes (M5)."""


@episode_group.command("list")
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--emotion", type=str, default=None, help="Filter by emotion (happy/sad/...).")
@click.option("--session", "session_id", type=str, default=None)
@click.pass_context
def episode_list(
    ctx: click.Context,
    limit: int,
    emotion: str | None,
    session_id: str | None,
) -> None:
    """List recent episodes ordered by occurred_at DESC."""
    memory = get_memory(ctx)
    episodes = memory.list_episodes(
        session_id=session_id,
        emotion=emotion,
        limit=limit,
    )
    if ctx.obj.get("output_json"):
        click.echo(
            json.dumps(
                [
                    {
                        "id": ep.id,
                        "occurred_at": ep.occurred_at.isoformat(),
                        "summary": ep.summary,
                        "verbatim_quote": ep.verbatim_quote,
                        "emotion": ep.emotion,
                        "intensity": ep.intensity,
                        "people": ep.people,
                        "topics": ep.topics,
                        "session_id": ep.session_id,
                    }
                    for ep in episodes
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if not episodes:
        click.echo("No episodes found.")
        return
    for ep in episodes:
        when = ep.occurred_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        people = f" 👥{','.join(ep.people)}" if ep.people else ""
        topics = f" #{','.join(ep.topics)}" if ep.topics else ""
        click.echo(
            f"[{when}] {ep.emotion}({ep.intensity}){people}{topics}\n    {ep.summary}\n    > {ep.verbatim_quote}\n"
        )


@episode_group.command("get")
@click.argument("episode_id")
@click.pass_context
def episode_get(ctx: click.Context, episode_id: str) -> None:
    """Show one episode in full."""
    memory = get_memory(ctx)
    ep = memory.get_episode(episode_id)
    if ep is None:
        click.echo(f"Episode {episode_id!r} not found.", err=True)
        ctx.exit(1)
        return
    payload = {
        "id": ep.id,
        "occurred_at": ep.occurred_at.isoformat(),
        "summary": ep.summary,
        "verbatim_quote": ep.verbatim_quote,
        "quote_event_id": ep.quote_event_id,
        "raw_event_ids": ep.raw_event_ids,
        "emotion": ep.emotion,
        "intensity": ep.intensity,
        "people": ep.people,
        "topics": ep.topics,
        "session_id": ep.session_id,
        "extractor_version": ep.extractor_version,
        "created_at": ep.created_at.isoformat(),
    }
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@episode_group.command("search")
@click.argument("query")
@click.option("--limit", type=int, default=10, show_default=True)
@click.pass_context
def episode_search(ctx: click.Context, query: str, limit: int) -> None:
    """FTS search over episodes (summary + quote + people + topics)."""
    memory = get_memory(ctx)
    episodes = memory.search_episodes(query, limit=limit)
    if not episodes:
        click.echo("No matching episodes.")
        return
    for ep in episodes:
        when = ep.occurred_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        click.echo(f"[{when}] {ep.emotion}({ep.intensity}) {ep.summary}")


@click.group("digest")
def digest_group() -> None:
    """Generate and inspect daily/weekly/monthly Episode digests."""


@digest_group.command("generate")
@click.option(
    "--kind",
    "period_kind",
    type=click.Choice(["daily", "weekly", "monthly"]),
    default="daily",
    show_default=True,
)
@click.option("--key", "period_key", type=str, default=None, help="Period key (e.g. 2026-06-26, 2026-W26, or 2026-06).")
@click.option(
    "--out",
    "output_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Directory to write the markdown file (default: don't write file).",
)
@click.option("--use-llm/--no-llm", default=True, show_default=True)
@click.pass_context
def digest_generate(
    ctx: click.Context,
    period_kind: str,
    period_key: str | None,
    output_dir: str | None,
    use_llm: bool,
) -> None:
    """Generate (or regenerate) a daily/weekly/monthly digest."""
    memory = get_memory(ctx)
    from octop_memory.pipeline.episode.digest import generate_digest

    llm = None
    if use_llm:
        # Try to find a configured LLM via the same config helper the
        # extractor uses; if missing, fall back to deterministic.
        try:
            from octop_memory.adapters.cli.config import load_config
            from octop_memory.application.runtime import _build_llm_client as build_llm_client

            cfg = load_config()
            llm_cfg = cfg.get("llm")
            if llm_cfg:
                llm = build_llm_client(llm_cfg)
        except REPORTABLE_ERRORS:
            logger.warning("digest LLM client setup failed; using deterministic digest", exc_info=True)
            llm = None

    out_dir = Path(output_dir).expanduser() if output_dir else None
    result = generate_digest(
        memory,
        period_kind=period_kind,  # type: ignore[arg-type]
        period_key=period_key,
        llm=llm,
        output_dir=out_dir,
    )

    payload = {
        "period_kind": result.digest.period_kind,
        "period_key": result.digest.period_key,
        "episode_count": result.episode_count,
        "used_llm": result.used_llm,
        "file_path": str(result.file_path) if result.file_path else None,
    }
    if ctx.obj.get("output_json"):
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(f"Digest generated: {payload}")
    click.echo("─" * 60)
    click.echo(result.digest.markdown)


@digest_group.command("list")
@click.option(
    "--kind",
    "period_kind",
    type=click.Choice(["daily", "weekly", "monthly"]),
    default=None,
)
@click.option("--limit", type=int, default=20, show_default=True)
@click.pass_context
def digest_list(ctx: click.Context, period_kind: str | None, limit: int) -> None:
    """List existing digests, newest first."""
    memory = get_memory(ctx)
    digests = memory.list_digests(period_kind=period_kind, limit=limit)  # type: ignore[arg-type]
    if not digests:
        click.echo("No digests yet.")
        return
    for d in digests:
        click.echo(
            f"{d.period_kind:7s} {d.period_key:10s} "
            f"episodes={len(d.episode_ids):3d} updated={d.updated_at.astimezone(UTC).isoformat()}"
        )


@digest_group.command("show")
@click.option(
    "--kind",
    "period_kind",
    type=click.Choice(["daily", "weekly", "monthly"]),
    default="daily",
    show_default=True,
)
@click.argument("period_key")
@click.pass_context
def digest_show(ctx: click.Context, period_kind: str, period_key: str) -> None:
    """Print the markdown of one digest."""
    memory = get_memory(ctx)
    digest = memory.get_digest(period_kind, period_key)  # type: ignore[arg-type]
    if digest is None:
        click.echo(f"Digest {period_kind} {period_key!r} not found.", err=True)
        ctx.exit(1)
        return
    click.echo(digest.markdown)


__all__ = ["digest_group", "episode_group"]
