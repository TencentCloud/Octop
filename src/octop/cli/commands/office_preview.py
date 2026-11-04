"""``octop office-preview`` — install and probe the LibreOffice Kit runtime."""

from __future__ import annotations

import json

import click

from octop.infra.office_preview.runtime import install_runtime, probe_status_payload
from octop.infra.utils.paths import PathLayout


@click.group("office-preview")
def office_preview() -> None:
    """Install and probe the optional Office-to-PDF preview runtime."""


@office_preview.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Show whether the LibreOffice Kit helper is installed and usable."""
    payload = probe_status_payload(PathLayout.from_env())
    if ctx.obj and ctx.obj.get("json_out"):
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload["available"]:
        click.echo(
            f"Office preview runtime is available "
            f"(Node {payload.get('node_version')}, kit {payload.get('kit_version')})."
        )
        return
    reason = payload.get("reason") or "unavailable"
    click.echo(f"Office preview runtime is not available ({reason}).")
    click.echo("Install with: octop office-preview install")
    raise SystemExit(1)


@office_preview.command("install")
def install_cmd() -> None:
    """Copy the helper and install the pinned LibreOffice Kit (needs Node >= 22.19)."""
    paths = PathLayout.from_env()
    paths.ensure_root()
    try:
        dest = install_runtime(paths=paths)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Installed Office preview runtime at {dest}")
    click.echo("Refresh open previews after installation completes.")
