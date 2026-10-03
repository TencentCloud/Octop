"""octop admin commands."""

from __future__ import annotations

import json as _json
import os
import sys

import click

from octop.cli.support.errors import fail_octop
from octop.infra.errors import OctopError


@click.group()
def admin() -> None:
    """Admin commands (local DB)."""


@admin.command("overview")
def overview() -> None:
    """Show admin overview (user count, agent state distribution)."""
    from octop.cli.support.offline_ops import admin_overview_offline

    click.echo(_json.dumps(admin_overview_offline(), indent=2))


@admin.command("audit")
@click.option("--actor", default=None)
@click.option("--action", default=None)
@click.option("--limit", default=50, type=int)
def audit(actor: str | None, action: str | None, limit: int) -> None:
    """Show audit log entries."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled
    from octop.cli.support.offline_ops import admin_audit_offline

    rows = admin_audit_offline(actor=actor, action=action, limit=limit)
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Audit Log")
    for col in ("id", "ts", "actor", "action", "target"):
        table.add_column(col)
    for e in rows:
        table.add_row(
            str(e.get("id", "")),
            str(e.get("ts", "")),
            e.get("actor", "") or "",
            e.get("action", "") or "",
            e.get("target", "") or "",
        )
    Console(file=sys.stdout).print(table)


@admin.group("providers")
def admin_providers() -> None:
    """Global (admin) providers."""


@admin_providers.command("list")
def list_admin_providers() -> None:
    from octop.cli.support.offline_ops import list_providers_offline

    click.echo(_json.dumps(list_providers_offline(), indent=2))


@admin_providers.command("create")
@click.option("--name", required=True)
@click.option("--kind", required=True)
@click.option("--config", "config_json", default="{}")
def create_admin_provider(name: str, kind: str, config_json: str) -> None:
    cfg = _json.loads(config_json)
    if not isinstance(cfg, dict):
        raise click.ClickException("config must be a JSON object")
    from octop.cli.support.offline_ops import create_provider_offline

    try:
        row = create_provider_offline(
            name=name,
            kind=kind,
            base_url=cfg.get("base_url"),
            api_key=cfg.get("api_key"),
            models=cfg.get("models"),
        )
    except OctopError as exc:
        fail_octop(exc)
    click.echo(_json.dumps(row, indent=2))


@admin_providers.command("delete")
@click.argument("provider_id", type=int)
def delete_admin_provider(provider_id: int) -> None:
    from octop.cli.support.offline_ops import delete_provider_offline

    try:
        delete_provider_offline(provider_id)
    except OctopError as exc:
        fail_octop(exc)
    click.echo("deleted")


@admin.command("rotate-jwt-secret")
def rotate_jwt_secret() -> None:
    """Rotate the JWT secret directly via the local DB."""
    from octop.config import load_config
    from octop.infra.db.factory import open_database
    from octop.infra.db.migrate import run_migrations
    from octop.infra.db.repos.secrets import SecretRepo
    from octop.infra.utils.env_file import apply_env_file, env_file_path
    from octop.infra.utils.paths import PathLayout

    paths = PathLayout.from_env()
    paths.ensure_root()
    apply_env_file(env_file_path(paths.root))
    config = load_config(paths.config)
    db = open_database(config, paths)
    run_migrations(db)
    SecretRepo(db).rotate("jwt", os.urandom(32))
    click.echo("jwt secret rotated. Restart octop-server for new sessions.")
