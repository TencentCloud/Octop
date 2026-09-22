"""Manual memory maintenance coordinated by the running Octop process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from octop.cli.support.ctx import json_output_enabled, resolve_agent
from octop.cli.support.db import resolve_cli_locale
from octop.i18n import tr
from octop.infra.agents.memory_slim_control import list_memory_slim_agents, request_memory_slim
from octop.infra.utils.paths import PathLayout


@click.group()
def memory() -> None:
    """Memory maintenance through the running local Octop server."""


def _print_agents(agents: list[dict[str, str]], locale: str) -> None:
    click.echo(tr("memory_slim.agents", locale))
    for number, agent in enumerate(agents, 1):
        click.echo(f"  {number}. {agent['name']}  [{agent['agent_id']}]")
    if not agents:
        click.echo(tr("memory_slim.no_agents", locale))


@memory.command(name="list")
def list_agents() -> None:
    """List eligible running agents without starting maintenance."""
    locale = resolve_cli_locale()
    try:
        agents = list_memory_slim_agents(PathLayout.from_env().root, locale=locale)
    except (OSError, ValueError, RuntimeError) as exc:
        raise click.ClickException(tr("memory_slim.unavailable", locale, detail=str(exc))) from exc
    if json_output_enabled():
        click.echo(json.dumps({"agents": agents}, ensure_ascii=False))
    else:
        _print_agents(agents, locale)


class _Progress:
    def __init__(self, locale: str) -> None:
        self.locale = locale
        self.terminal = click.get_text_stream("stdout").isatty()
        self.phase = ""
        self.elapsed = -5
        self.scanned: object = None
        self.width = 0

    def close(self) -> None:
        if self.width:
            click.echo()
            self.width = 0

    def show(self, status: dict[str, Any]) -> None:
        phase = str(status.get("phase", "waiting"))
        elapsed = int(status.get("elapsed_seconds", 0))
        scanned = status.get("scanned") if phase == "deduplicating" else None
        changed = phase != self.phase or scanned != self.scanned
        if not changed and elapsed < self.elapsed + (1 if self.terminal else 5):
            return
        if phase != self.phase:
            self.close()
        line = tr(f"memory_slim.{phase}", self.locale)
        line += " " + tr("memory_slim.elapsed", self.locale, seconds=elapsed)
        if scanned is not None and status.get("total") is not None:
            line += " " + tr(
                "memory_slim.scanned", self.locale, scanned=scanned, total=status["total"]
            )
        if self.terminal and phase not in {"done", "failed"}:
            click.echo("\r" + line.ljust(self.width), nl=False)
            self.width = len(line)
        else:
            click.echo(line)
        self.phase, self.elapsed, self.scanned = phase, elapsed, scanned


def _slim_agent(root: Path, agent_id: str, locale: str, *, index: int, total: int) -> None:
    progress = _Progress(locale)
    try:
        for status in request_memory_slim(root, agent_id, locale=locale):
            if json_output_enabled():
                click.echo(
                    json.dumps(
                        {**status, "agent_id": agent_id, "index": index, "total_agents": total},
                        ensure_ascii=False,
                    )
                )
            else:
                progress.show(status)
                if status.get("phase") == "done":
                    report = status["report"]
                    click.echo(
                        tr(
                            "memory_slim.result",
                            locale,
                            before=f"{report['before']['file_bytes'] / 1048576:.2f}",
                            after=f"{report['after']['file_bytes'] / 1048576:.2f}",
                            backup=report["backup_path"],
                        )
                    )
            if status.get("phase") == "failed":
                raise click.ClickException(str(status.get("error", "Maintenance failed")))
    finally:
        progress.close()


@memory.command()
@click.option(
    "--agent",
    "agent_id",
    default=None,
    help="Agent ID; uses the selected agent or prompts from a list.",
)
@click.option(
    "--all", "all_agents", is_flag=True, help="Sequentially slim all eligible running agents."
)
def slim(agent_id: str | None, all_agents: bool) -> None:
    """Back up and slim memory, pausing new turns until completion. Keeps all history."""
    locale = resolve_cli_locale()
    root = PathLayout.from_env().root
    root_agent = (click.get_current_context().find_root().obj or {}).get("agent_id")
    if all_agents and (agent_id is not None or root_agent):
        raise click.UsageError(tr("memory_slim.all_conflict", locale))
    try:
        if all_agents:
            targets = list_memory_slim_agents(root, locale=locale)
            if not targets:
                raise click.ClickException(tr("memory_slim.no_agents", locale))
        else:
            agent_id = resolve_agent(agent_id)
            if agent_id is None:
                agents = list_memory_slim_agents(root, locale=locale)
                if json_output_enabled():
                    click.echo(json.dumps({"agents": agents}, ensure_ascii=False))
                    raise click.ClickException(tr("memory_slim.agent_required", locale))
                if not agents:
                    raise click.ClickException(tr("memory_slim.no_agents", locale))
                _print_agents(agents, locale)
                number = click.prompt(
                    tr("memory_slim.choose", locale), type=click.IntRange(1, len(agents))
                )
                agent_id = agents[number - 1]["agent_id"]
            targets = [{"agent_id": agent_id, "name": agent_id}]
        total = len(targets)
        for index, target in enumerate(targets, 1):
            target_id = target["agent_id"]
            if all_agents:
                if json_output_enabled():
                    click.echo(
                        json.dumps(
                            {
                                "phase": "batch_agent",
                                **target,
                                "index": index,
                                "total_agents": total,
                            },
                            ensure_ascii=False,
                        )
                    )
                else:
                    click.echo(
                        tr(
                            "memory_slim.batch_target",
                            locale,
                            index=index,
                            total=total,
                            name=target["name"],
                            agent_id=target_id,
                        )
                    )
            elif not json_output_enabled():
                click.echo(tr("memory_slim.target", locale, agent_id=target_id))
            try:
                _slim_agent(root, target_id, locale, index=index, total=total)
            except (click.ClickException, OSError, ValueError, RuntimeError) as exc:
                if not all_agents:
                    raise
                message = tr(
                    "memory_slim.batch_stopped",
                    locale,
                    agent_id=target_id,
                    completed=index - 1,
                    remaining=total - index,
                    detail=str(exc),
                )
                if json_output_enabled():
                    click.echo(
                        json.dumps(
                            {
                                "phase": "batch_failed",
                                "agent_id": target_id,
                                "completed": index - 1,
                                "remaining": total - index,
                                "total_agents": total,
                                "error": message,
                            },
                            ensure_ascii=False,
                        )
                    )
                raise click.ClickException(message) from exc
        if all_agents:
            if json_output_enabled():
                click.echo(
                    json.dumps({"phase": "batch_done", "completed": total, "total_agents": total})
                )
            else:
                click.echo(tr("memory_slim.batch_done", locale, total=total))
    except (OSError, ValueError, RuntimeError) as exc:
        raise click.ClickException(tr("memory_slim.unavailable", locale, detail=str(exc))) from exc
