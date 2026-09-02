"""Run Feishu bot-creator subprocess locally (no HTTP)."""

from __future__ import annotations

import contextlib
import time
from typing import Any

import click

from octop.cli.support.qr import render_qrcode_terminal
from octop.infra.gateway.bot_creators.feishu_runner import (
    poll_feishu_creator,
    start_feishu_creator,
    stop_feishu_creator,
)


def dry_run_feishu_setup(*, agent_id: str, platform: str, channel_id: str | None) -> None:
    """Print what ``feishu-setup`` would do without starting the scan-to-create flow."""
    click.echo("Dry run — no subprocess or channel writes.")
    click.echo(f"  agent:      {agent_id}")
    click.echo(f"  platform:   {platform}")
    click.echo(f"  channel_id: {channel_id or '(create new feishu channel)'}")
    click.echo("  steps:")
    click.echo("    1. Start feishu_bot_creator.py subprocess (lark-oapi register_app)")
    click.echo("    2. Poll stdout until app_id + app_secret")
    click.echo("    3. Render QR in terminal when qr_url appears")
    click.echo("    4. Stop subprocess")
    click.echo("    5. PATCH or POST channel with app_id / app_secret")


def run_feishu_bot_creator(
    *,
    platform: str = "feishu",
    timeout_sec: int = 300,
) -> tuple[str, str]:
    """Start creator, poll until credentials ready. Returns (app_id, app_secret)."""
    proc = start_feishu_creator(platform=platform)
    click.echo("Feishu bot creator started — scan QR in Feishu App when it appears.")
    shown_qr = False
    app_id = app_secret = None
    deadline = time.time() + timeout_sec
    lines: list[dict[str, Any]] = []
    try:
        while time.time() < deadline:
            poll = poll_feishu_creator(proc, lines)
            for ev in poll.get("events") or []:
                level = ev.get("level", "")
                message = ev.get("message") or ev.get("step") or ""
                if message and level in ("info", "success", ""):
                    click.echo(f"  {message}")
            qr_url = poll.get("qr_url")
            if qr_url and not shown_qr:
                render_qrcode_terminal(str(qr_url))
                shown_qr = True
            app_id = poll.get("app_id") or app_id
            app_secret = poll.get("app_secret") or app_secret
            status = poll.get("status")
            if app_id and app_secret:
                return str(app_id), str(app_secret)
            if status == "failed":
                raise click.ClickException(f"bot creator failed (code={poll.get('return_code')})")
            if status == "finished" and not (app_id and app_secret):
                raise click.ClickException("bot creator finished without credentials")
            if proc.poll() is not None and status != "running":
                break
            time.sleep(2)
    finally:
        with contextlib.suppress(Exception):
            stop_feishu_creator(proc)

    raise click.ClickException("timed out waiting for Feishu credentials")
