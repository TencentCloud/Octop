"""octop agent commands."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click

from octop.cli.support.errors import fail_octop
from octop.infra.errors import ErrorCode, OctopError


@click.group()
def agent() -> None:
    """Agent lifecycle commands."""


@agent.command("create")
@click.argument("name")
@click.option("--agent-id", "agent_id", default=None, help="Custom agent ID (short string, optional).")
@click.option("--persona-mbti", "persona_mbti", default=None)
@click.option("--default-model", "default_model", default=None)
@click.option("--template", "template_name", default=None, help="Agent template name.")
@click.option("--user", "as_user", default=None, help="Create for another user (admin)")
def create(
    name: str,
    agent_id: str | None,
    persona_mbti: str | None,
    default_model: str | None,
    template_name: str | None,
    as_user: str | None,
) -> None:
    """Create a new agent (boots embedded server)."""
    import asyncio

    from octop.cli.repl.embedded_session import embedded_runtime
    from octop.cli.support.acting import resolve_cli_acting_user_id
    from octop.infra.agents.manager import AgentCreateSpec

    try:
        uid = resolve_cli_acting_user_id(None, as_user)
    except OctopError as exc:
        fail_octop(exc)

    async def _run() -> Any:
        async with embedded_runtime() as server:
            assert server.app_runtime is not None
            spec = AgentCreateSpec(
                name=name,
                agent_id=agent_id,
                user_id=uid,
                persona_mbti=persona_mbti,
                default_model=default_model,
                template_name=template_name,
            )
            return await server.app_runtime.agent_registry.create(spec)

    try:
        row = asyncio.run(_run())
    except OctopError as exc:
        fail_octop(exc)
    click.echo(_json.dumps({"agent_id": row.agent_id, "name": row.name}, indent=2))


@agent.command("from-expert")
@click.argument("expert_id")
@click.option("--name", default=None)
@click.option("--agent-id", "agent_id", default=None, help="Custom agent ID (short string, optional).")
@click.option("--user", "as_user", default=None)
def from_expert(expert_id: str, name: str | None, agent_id: str | None, as_user: str | None) -> None:
    """Create an agent from a bundled expert template (embedded server)."""
    import asyncio

    from octop.cli.repl.embedded_session import embedded_runtime
    from octop.cli.support.acting import resolve_cli_acting_user_id
    from octop.infra.agents.experts.catalog import build_create_spec_from_expert
    from octop.infra.utils.locale import resolve_user_locale

    try:
        uid = resolve_cli_acting_user_id(None, as_user)
    except OctopError as exc:
        fail_octop(exc)

    async def _run() -> Any:
        async with embedded_runtime() as server:
            assert server.app_runtime is not None
            assert server.services is not None
            catalog = server.expert_catalog
            expert = None if catalog is None else catalog.get(expert_id)
            if expert is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"expert {expert_id!r} not found")
            locale = resolve_user_locale(user_repo=server.services.user_repo, user_id=uid)
            spec = build_create_spec_from_expert(
                expert_id=expert_id,
                expert=expert,
                user_id=uid,
                name=name,
                agent_id=agent_id,
                locale=locale,
            )
            return await server.app_runtime.agent_registry.create(spec, defer_bootstrap=True)

    try:
        row = asyncio.run(_run())
    except OctopError as exc:
        fail_octop(exc)
    click.echo(_json.dumps({"agent_id": row.agent_id, "name": row.name}, indent=2))


@agent.command("list")
@click.option("--user", "as_user", default=None)
def list_agents(as_user: str | None) -> None:
    """List agents from local DB."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled
    from octop.cli.support.db import list_agents_offline

    try:
        rows = list_agents_offline(as_user=as_user)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Agents")
    for col in ("id", "name", "template", "model", "state"):
        table.add_column(col)
    for a in rows:
        aid = a.get("agent_id") or a.get("id", "")
        table.add_row(
            str(aid),
            a.get("name", ""),
            a.get("template_name", "") or "",
            a.get("default_model", "") or "",
            a.get("state", "") or a.get("last_state", "") or "",
        )
    Console(file=sys.stdout).print(table)


@agent.command("use")
@click.argument("agent_id")
def use_agent(agent_id: str) -> None:
    """Pin default agent in CLI state (~/.octop/cli_state.json)."""
    from octop.cli.support.state import default_state_path, load, save

    path = default_state_path()
    state = load(path)
    state.default_agent = agent_id
    save(path, state)
    click.echo(f"default agent set to {agent_id}")


def _act(action: str, agent_id: str, as_user: str | None) -> None:
    from octop.cli.support.acting import resolve_cli_acting_user_id
    from octop.cli.support.embedded_ops import agent_action

    try:
        resolve_cli_acting_user_id(agent_id, as_user)
    except OctopError as exc:
        fail_octop(exc)
    if action == "delete":
        from octop.cli.support.offline_ops import delete_agent_offline

        try:
            delete_agent_offline(agent_id)
        except OctopError as exc:
            fail_octop(exc)
        click.echo("deleted")
        return
    try:
        agent_action(agent_id, action)
    except Exception as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from exc
    click.echo("ok")


@agent.command("start")
@click.argument("agent_id")
@click.option("--user", "as_user", default=None)
def start(agent_id: str, as_user: str | None) -> None:
    _act("start", agent_id, as_user)


@agent.command("stop")
@click.argument("agent_id")
@click.option("--user", "as_user", default=None)
def stop(agent_id: str, as_user: str | None) -> None:
    _act("stop", agent_id, as_user)


@agent.command("reload")
@click.argument("agent_id")
@click.option("--user", "as_user", default=None)
def reload(agent_id: str, as_user: str | None) -> None:
    _act("reload", agent_id, as_user)


@agent.command("delete")
@click.argument("agent_id")
@click.option("--user", "as_user", default=None)
@click.option("--yes", is_flag=True, default=False)
def delete(agent_id: str, as_user: str | None, yes: bool) -> None:
    if not yes:
        click.confirm(f"Really delete agent {agent_id}?", abort=True)
    _act("delete", agent_id, as_user)


@agent.command("experts")
def list_experts() -> None:
    """List bundled expert (scene) templates."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled
    from octop.cli.support.offline_ops import list_experts_offline

    rows = list_experts_offline()
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Expert templates")
    table.add_column("id")
    table.add_column("label (zh)")
    table.add_column("description (zh)")
    for e in rows:
        label = e.get("label") or {}
        desc = e.get("description") or {}
        table.add_row(
            e.get("id", ""),
            label.get("zh", "") if isinstance(label, dict) else str(label),
            (desc.get("zh", "") if isinstance(desc, dict) else str(desc))[:60],
        )
    Console(file=sys.stdout).print(table)
