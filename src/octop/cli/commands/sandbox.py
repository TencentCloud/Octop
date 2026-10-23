"""octop sandbox — sandbox container ledger, drift, and recreate."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click

from octop.cli.support.ctx import json_output_enabled
from octop.cli.support.errors import fail_octop
from octop.infra.errors import OctopError


@click.group()
def sandbox() -> None:
    """Manage sandbox containers (list / recreate / images / backups)."""


def _echo_json(payload: Any) -> None:
    click.echo(_json.dumps(payload, indent=2, ensure_ascii=False))


def _service(server: Any) -> Any:
    from octop.infra.backend.sandbox_admin import SandboxAdminService

    assert server.app_runtime is not None
    return SandboxAdminService(services=server.services, app_runtime=server.app_runtime)


def _entry_row(entry: Any) -> dict[str, Any]:
    return {
        "container": entry.container_name,
        "scope": entry.scope,
        "agent_id": entry.agent_id,
        "status": entry.status,
        "image": entry.image,
        "expected_image": entry.expected_image,
        "drift": entry.drift,
        "network_offline": entry.network_offline,
        "expected_allow_network": entry.expected_allow_network,
        "network_drift": entry.network_drift,
        "affected_agents": entry.affected_agents,
    }


def _echo_table(rows: list[dict[str, Any]]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Sandbox containers")
    for col in (
        "container",
        "scope",
        "status",
        "image",
        "drift",
        "network",
        "network_drift",
    ):
        table.add_column(col)
    for row in rows:
        offline = row.get("network_offline")
        network = "offline" if offline is True else ("online" if offline is False else "?")
        ndrift = row.get("network_drift")
        table.add_row(
            str(row.get("container") or ""),
            str(row.get("scope") or ""),
            str(row.get("status") or ""),
            str(row.get("image") or ""),
            "DRIFT" if row.get("drift") else "",
            network,
            "NETWORK-DRIFT" if ndrift else "",
        )
    Console(file=sys.stdout).print(table)


async def _list_async() -> list[dict[str, Any]]:
    from octop.cli.repl.embedded_session import embedded_runtime

    async with embedded_runtime() as server:
        entries = _service(server).list_sandboxes()
        return [_entry_row(e) for e in entries]


@sandbox.command("list")
@click.option("--drift-only", is_flag=True, help="Show only rows with drift.")
def list_sandboxes(drift_only: bool) -> None:
    """List sandbox containers with image/network drift."""
    import asyncio

    try:
        rows = asyncio.run(_list_async())
    except OctopError as exc:
        fail_octop(exc)
    if drift_only:
        rows = [r for r in rows if r.get("drift") or r.get("network_drift")]
    if json_output_enabled():
        _echo_json(rows)
    elif rows:
        _echo_table(rows)


async def _recreate_async(container: str) -> dict[str, Any]:
    from octop.cli.repl.embedded_session import embedded_runtime

    async with embedded_runtime() as server:
        result: dict[str, Any] = _service(server).recreate(container)
        return result


@sandbox.command("recreate")
@click.argument("container")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def recreate(container: str, yes: bool) -> None:
    """Recreate one sandbox container (backup → verify image → remove)."""
    import asyncio

    if not json_output_enabled() and not yes:
        click.confirm(
            f"Back up and remove sandbox container {container!r}? "
            "The next conversation recreates it with the configured image/network.",
            abort=True,
        )
    try:
        result = asyncio.run(_recreate_async(container))
    except OctopError as exc:
        fail_octop(exc)
    if json_output_enabled():
        _echo_json(result)
        return
    click.echo(
        f"removed: {result['container_name']}\n"
        f"backup: {result['backup_path']}\n"
        f"old image: {result.get('old_image') or '?'} → "
        f"expected: {result.get('expected_image') or '(unchanged)'}\n"
        "The container is rebuilt on the next conversation."
    )


async def _images_async() -> list[dict[str, Any]]:
    from octop.cli.repl.embedded_session import embedded_runtime

    async with embedded_runtime() as server:
        rows: list[dict[str, Any]] = _service(server).list_images()
        return rows


@sandbox.command("images")
def images() -> None:
    """List local Docker images with sandbox-reference flags."""
    import asyncio

    try:
        rows = asyncio.run(_images_async())
    except OctopError as exc:
        fail_octop(exc)
    if json_output_enabled():
        _echo_json(rows)
        return
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Local images")
    for col in ("tag", "id", "size_mb", "referenced"):
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row.get("tag") or "<none>"),
            str(row.get("id") or ""),
            f"{int(row.get('size') or 0) / 1_000_000:.1f}",
            "yes" if row.get("referenced") else "",
        )
    Console(file=sys.stdout).print(table)


async def _backups_async(container: str) -> list[dict[str, Any]]:
    from octop.cli.repl.embedded_session import embedded_runtime

    async with embedded_runtime() as server:
        rows: list[dict[str, Any]] = _service(server).list_backups(container)
        return rows


@sandbox.command("backups")
@click.argument("container")
def backups(container: str) -> None:
    """List workspace backups for one sandbox container."""
    import asyncio

    try:
        rows = asyncio.run(_backups_async(container))
    except OctopError as exc:
        fail_octop(exc)
    if json_output_enabled():
        _echo_json(rows)
        return
    for row in rows:
        meta = row.get("meta") or {}
        click.echo(f"{row['stamp']}  image={meta.get('image') or '?'}  {row['path']}")
