"""octop skills — per-agent skill library."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click

from octop.cli.support.ctx import json_output_enabled, require_agent


@click.group("skills")
def skills() -> None:
    """Manage agent skills (enable / disable / list)."""


def _skill_source(skill: dict[str, Any]) -> str:
    return str(skill.get("source") or skill.get("kind") or "")


@skills.command("list")
@click.option("--agent", "agent_id", default=None)
def list_skills(agent_id: str | None) -> None:
    """List skills for an agent."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.skills import list_skills_offline
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        rows = list_skills_offline(aid)
    except OctopError as exc:
        click.echo(f"error: {exc.message}", err=True)
        raise SystemExit(1) from exc
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title=f"Skills ({aid})")
    for col in ("name", "enabled", "source"):
        table.add_column(col)
    for s in rows:
        table.add_row(
            str(s.get("name") or s.get("slug") or ""),
            str(bool(s.get("enabled", True))),
            _skill_source(s),
        )
    Console(file=sys.stdout).print(table)


@skills.command("enable")
@click.argument("name")
@click.option("--agent", "agent_id", default=None)
def enable_skill(name: str, agent_id: str | None) -> None:
    """Enable a skill."""
    from octop.cli.support.skills import set_skill_enabled
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        set_skill_enabled(aid, name, enabled=True)
    except OctopError as exc:
        click.echo(f"error: {exc.message}", err=True)
        raise SystemExit(1) from exc
    click.echo(f"enabled: {name}")


@skills.command("disable")
@click.argument("name")
@click.option("--agent", "agent_id", default=None)
def disable_skill(name: str, agent_id: str | None) -> None:
    """Disable a skill."""
    from octop.cli.support.skills import set_skill_enabled
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        set_skill_enabled(aid, name, enabled=False)
    except OctopError as exc:
        click.echo(f"error: {exc.message}", err=True)
        raise SystemExit(1) from exc
    click.echo(f"disabled: {name}")


@skills.command("config")
@click.option("--agent", "agent_id", default=None)
def config_skills(agent_id: str | None) -> None:
    """Interactively toggle which skills are enabled."""
    from octop.cli.support import prompts as _prompts
    from octop.cli.support.skills import list_skills_offline, set_skill_enabled
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    try:
        all_skills = list_skills_offline(aid)
    except OctopError as exc:
        click.echo(f"error: {exc.message}", err=True)
        raise SystemExit(1) from exc
    if not all_skills:
        click.echo("No skills found.")
        return

    labels = []
    label_to_name: dict[str, str] = {}
    defaults: list[str] = []
    for s in sorted(all_skills, key=lambda x: str(x.get("name") or x.get("slug") or "")):
        n = str(s.get("slug") or s.get("name") or "")
        mark = "✓" if s.get("enabled", True) else "✗"
        label = f"{n} [{mark}] ({_skill_source(s)})"
        labels.append(label)
        label_to_name[label] = n
        if s.get("enabled", True):
            defaults.append(label)

    click.echo("\n=== Skills ===")
    selected = _prompts.checkbox("Select skills to enable:", choices=labels, defaults=defaults)
    selected_set = {label_to_name[label] for label in selected if label in label_to_name}

    for s in all_skills:
        n = str(s.get("slug") or s.get("name") or "")
        want = n in selected_set
        have = bool(s.get("enabled", True))
        if want == have:
            continue
        try:
            set_skill_enabled(aid, n, enabled=want)
        except OctopError as exc:
            click.echo(f"failed to {'enable' if want else 'disable'} {n}: {exc.message}", err=True)
        else:
            click.echo(f"  {'enable' if want else 'disable'}d {n}")
    click.echo("done")
