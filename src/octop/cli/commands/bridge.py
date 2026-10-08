"""octop bridge — manage Octop-to-Octop peer connections."""

from __future__ import annotations

import json as _json
import sys
from typing import Any

import click

from octop.cli.support.acting import resolve_cli_acting_user_id
from octop.cli.support.ctx import json_output_enabled
from octop.cli.support.errors import fail_octop
from octop.infra.errors import OctopError


@click.group()
def bridge() -> None:
    """Manage remote Octop bridge peers (add / edit / probe / connect)."""


def _resolve_owner(as_user: str | None) -> int:
    try:
        return resolve_cli_acting_user_id(None, as_user)
    except OctopError as exc:
        fail_octop(exc)


def _prompt_password(password: str | None) -> str:
    secret = (password or "").strip()
    if secret:
        return secret
    return str(click.prompt("Peer password", hide_input=True))


def _echo_json(payload: Any) -> None:
    click.echo(_json.dumps(payload, indent=2, ensure_ascii=False))


def _echo_connection_table(rows: list[dict[str, Any]]) -> None:
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Bridge connections")
    for col in ("id", "name", "peer", "user", "status", "auto"):
        table.add_column(col)
    for row in rows:
        table.add_row(
            row.get("connection_id", ""),
            row.get("display_name", "") or "",
            row.get("peer_base_url", "") or "",
            row.get("peer_username", "") or "",
            row.get("status", "") or "",
            str(bool(row.get("auto_reconnect"))),
        )
    Console(file=sys.stdout).print(table)


def _echo_probe(result: dict[str, Any]) -> None:
    from rich.console import Console
    from rich.table import Table

    name = str(result.get("peer_display_name") or "")
    count = int(result.get("agent_count") or 0)
    click.echo(f"peer: {name}  agents: {count}")
    agents = result.get("agents") or []
    if not isinstance(agents, list) or not agents:
        return
    table = Table(title="Peer experts")
    for col in ("agent_id", "name", "kind", "state"):
        table.add_column(col)
    for item in agents:
        if not isinstance(item, dict):
            continue
        table.add_row(
            str(item.get("agent_id") or ""),
            str(item.get("name") or ""),
            str(item.get("kind") or ""),
            str(item.get("state") or ""),
        )
    Console(file=sys.stdout).print(table)


def _echo_handshake_note(*, connect: bool) -> None:
    if json_output_enabled() or not connect:
        return
    click.echo(
        "Peer handshake verified; CLI closed the session. "
        "Start `octop run` to keep the bridge linked."
    )


@bridge.command("list")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def list_connections(as_user: str | None) -> None:
    """List saved bridge connections for the acting user."""
    from octop.cli.support.embedded_ops import list_bridge_connections

    uid = _resolve_owner(as_user)
    rows = list_bridge_connections(uid)
    if json_output_enabled():
        _echo_json(rows)
        return
    _echo_connection_table(rows)


@bridge.command("get")
@click.argument("connection_id")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def get_connection(connection_id: str, as_user: str | None) -> None:
    """Show one saved bridge connection."""
    from octop.cli.support.embedded_ops import get_bridge_connection

    uid = _resolve_owner(as_user)
    try:
        row = get_bridge_connection(connection_id, uid)
    except OctopError as exc:
        fail_octop(exc)
    _echo_json(row)


@bridge.command("probe")
@click.argument("connection_id", required=False)
@click.option("--url", "--peer-url", "peer_base_url", default=None, help="Remote Octop base URL.")
@click.option(
    "--peer-user",
    "--username",
    "peer_username",
    default=None,
    help="Remote username (not the local --user).",
)
@click.option(
    "--peer-password",
    "password",
    default=None,
    help="Remote password; prompted if omitted (ad-hoc probe).",
)
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def probe(
    connection_id: str | None,
    peer_base_url: str | None,
    peer_username: str | None,
    password: str | None,
    as_user: str | None,
) -> None:
    """Test peer credentials (login + list experts). Does not open Bridge WS."""
    from octop.cli.support.embedded_ops import probe_bridge_connection, probe_bridge_peer

    try:
        if connection_id:
            uid = _resolve_owner(as_user)
            result = probe_bridge_connection(
                connection_id,
                uid,
                peer_base_url=peer_base_url,
                peer_username=peer_username,
                password=password,
            )
        else:
            if not (peer_base_url or "").strip() or not (peer_username or "").strip():
                raise click.UsageError(
                    "--url and --peer-user are required when CONNECTION_ID is omitted"
                )
            result = probe_bridge_peer(
                peer_base_url=peer_base_url or "",
                peer_username=peer_username or "",
                password=_prompt_password(password),
            )
    except OctopError as exc:
        fail_octop(exc)
    if json_output_enabled():
        _echo_json(result)
        return
    _echo_probe(result)


@bridge.command("create")
@click.option("--url", "--peer-url", "peer_base_url", required=True, help="Remote Octop base URL.")
@click.option(
    "--peer-user",
    "--username",
    "peer_username",
    required=True,
    help="Remote username (not the local --user).",
)
@click.option(
    "--peer-password",
    "password",
    prompt="Peer password",
    hide_input=True,
    confirmation_prompt=False,
    help="Remote password (hidden prompt if omitted).",
)
@click.option("--name", "display_name", required=True, help="Local display name (unique per user).")
@click.option("--notes", default=None, help="Optional local notes.")
@click.option("--icon", "icon_name", default=None, help="Optional Lucide icon key.")
@click.option(
    "--connect/--no-connect",
    default=True,
    help="Verify Bridge WS after login (default: connect).",
)
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def create(
    peer_base_url: str,
    peer_username: str,
    password: str,
    display_name: str,
    notes: str | None,
    icon_name: str | None,
    connect: bool,
    as_user: str | None,
) -> None:
    """Add a bridge peer. With --connect, keep the row only if handshake succeeds."""
    from octop.cli.support.embedded_ops import create_bridge_connection

    uid = _resolve_owner(as_user)
    secret = password.strip()
    if not secret:
        raise click.UsageError("--peer-password is required")
    try:
        row = create_bridge_connection(
            uid,
            peer_base_url=peer_base_url,
            peer_username=peer_username,
            password=secret,
            display_name=display_name,
            notes=notes,
            icon_name=icon_name,
            connect=connect,
        )
    except OctopError as exc:
        fail_octop(exc)
    _echo_json(row)
    _echo_handshake_note(connect=connect)


@bridge.command("patch")
@click.argument("connection_id")
@click.option("--name", "display_name", default=None, help="Local display name.")
@click.option("--notes", default=None, help="Local notes; pass empty string to clear.")
@click.option("--icon", "icon_name", default=None, help="Lucide icon key; empty to clear.")
@click.option("--url", "--peer-url", "peer_base_url", default=None, help="Remote Octop base URL.")
@click.option(
    "--peer-user",
    "--username",
    "peer_username",
    default=None,
    help="Remote username.",
)
@click.option(
    "--peer-password",
    "password",
    default=None,
    help="New remote password; omit to keep the stored secret.",
)
@click.option(
    "--auto-reconnect/--no-auto-reconnect",
    "auto_reconnect",
    default=None,
    help="Dial again after unexpected disconnect.",
)
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def patch_connection(
    connection_id: str,
    display_name: str | None,
    notes: str | None,
    icon_name: str | None,
    peer_base_url: str | None,
    peer_username: str | None,
    password: str | None,
    auto_reconnect: bool | None,
    as_user: str | None,
) -> None:
    """Update display name, notes, icon, peer credentials, or auto-reconnect."""
    from octop.cli.support.embedded_ops import patch_bridge_connection

    if (
        display_name is None
        and notes is None
        and icon_name is None
        and peer_base_url is None
        and peer_username is None
        and password is None
        and auto_reconnect is None
    ):
        raise click.UsageError(
            "nothing to patch; pass --name, --notes, --icon, --url, "
            "--peer-user, --peer-password, or --auto-reconnect/--no-auto-reconnect"
        )
    uid = _resolve_owner(as_user)
    try:
        row = patch_bridge_connection(
            connection_id,
            uid,
            display_name=display_name,
            notes=notes,
            update_notes=notes is not None,
            icon_name=icon_name,
            update_icon=icon_name is not None,
            peer_base_url=peer_base_url,
            peer_username=peer_username,
            password=password,
            auto_reconnect=auto_reconnect,
        )
    except OctopError as exc:
        fail_octop(exc)
    _echo_json(row)


@bridge.command("delete")
@click.argument("connection_id")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def delete_connection(connection_id: str, yes: bool, as_user: str | None) -> None:
    """Delete a saved bridge connection."""
    from octop.cli.support.embedded_ops import delete_bridge_connection

    uid = _resolve_owner(as_user)
    if not yes:
        click.confirm(f"Delete bridge connection {connection_id}?", abort=True)
    try:
        delete_bridge_connection(connection_id, uid)
    except OctopError as exc:
        fail_octop(exc)
    click.echo("deleted")


@bridge.command("connect")
@click.argument("connection_id")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def connect_connection(connection_id: str, as_user: str | None) -> None:
    """Dial the peer and verify Bridge WS, then close the CLI session."""
    from octop.cli.support.embedded_ops import connect_bridge_connection

    uid = _resolve_owner(as_user)
    try:
        row = connect_bridge_connection(connection_id, uid)
    except OctopError as exc:
        fail_octop(exc)
    _echo_json(row)
    _echo_handshake_note(connect=True)


@bridge.command("disconnect")
@click.argument("connection_id")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def disconnect_connection(connection_id: str, as_user: str | None) -> None:
    """Mark a connection disconnected in the local DB."""
    from octop.cli.support.embedded_ops import disconnect_bridge_connection

    uid = _resolve_owner(as_user)
    try:
        row = disconnect_bridge_connection(connection_id, uid)
    except OctopError as exc:
        fail_octop(exc)
    _echo_json(row)


@bridge.command("agents")
@click.argument("connection_id")
@click.option("--user", "as_user", default=None, help="Local owner (username).")
def list_agents(connection_id: str, as_user: str | None) -> None:
    """Dial the peer, list remote experts via the tunnel, then close."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.embedded_ops import list_bridge_remote_agents

    uid = _resolve_owner(as_user)
    try:
        agents = list_bridge_remote_agents(connection_id, uid)
    except OctopError as exc:
        fail_octop(exc)
    if json_output_enabled():
        _echo_json(agents)
        return
    table = Table(title="Remote experts")
    for col in ("id", "name", "kind", "state"):
        table.add_column(col)
    for item in agents:
        table.add_row(
            str(item.get("agent_id") or item.get("id") or ""),
            str(item.get("name") or ""),
            str(item.get("kind") or ""),
            str(item.get("state") or ""),
        )
    Console(file=sys.stdout).print(table)
    _echo_handshake_note(connect=True)
