"""octop channel commands (local DB + embedded runtime)."""

from __future__ import annotations

import json as _json
import sys
import time
from typing import Any

import click

from octop.cli.support.acting import resolve_cli_acting_user_id
from octop.cli.support.ctx import require_agent
from octop.infra.errors import OctopError


@click.group()
def channel() -> None:
    """Channel management commands."""


def _resolve_user(agent_id: str, as_user: str | None) -> int:
    try:
        return resolve_cli_acting_user_id(agent_id, as_user)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc


def _parse_json_object(label: str, raw: str) -> dict[str, Any]:
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise click.ClickException(f"{label} must be a JSON object")
    return parsed


@channel.command("list")
@click.option("--user", "as_user", default=None)
@click.option("--agent", "agent_id", default=None)
def list_channels(as_user: str | None, agent_id: str | None) -> None:
    """List channels for an agent."""
    from rich.console import Console
    from rich.table import Table

    from octop.cli.support.ctx import json_output_enabled

    aid = require_agent(agent_id)
    _resolve_user(aid, as_user)
    from octop.cli.support.offline_ops import list_channels_offline

    rows = list_channels_offline(aid)
    if json_output_enabled():
        click.echo(_json.dumps(rows, indent=2))
        return
    table = Table(title="Channels")
    for col in ("id", "name", "kind", "enabled"):
        table.add_column(col)
    for ch in rows:
        table.add_row(
            ch.get("id", ""),
            ch.get("name", "") or "",
            ch.get("kind", ""),
            str(bool(ch.get("enabled"))),
        )
    Console(file=sys.stdout).print(table)


@channel.command("get")
@click.option("--agent", "agent_id", default=None)
@click.argument("channel_id")
@click.option("--user", "as_user", default=None)
def get_channel(agent_id: str | None, channel_id: str, as_user: str | None) -> None:
    """Show channel details including config (secrets masked)."""
    from octop.cli.support.qr import mask_secret

    aid = require_agent(agent_id)
    _resolve_user(aid, as_user)
    from octop.cli.support.offline_ops import get_channel_offline
    from octop.infra.errors import OctopError

    try:
        row = get_channel_offline(aid, channel_id)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    cfg = row.get("config") or {}
    secret_keys = {"bot_token", "secret", "app_secret", "client_secret", "token"}
    for k, v in list(cfg.items()):
        if k in secret_keys and v:
            cfg[k] = mask_secret(str(v))
    click.echo(_json.dumps({**row, "config": cfg}, indent=2))


@channel.command("create")
@click.option("--agent", "agent_id", default=None)
@click.option("--kind", required=True)
@click.option("--name", default=None, help="Display name (defaults to kind).")
@click.option("--config", "config_json", default="{}", help="JSON config")
@click.option("--user", "as_user", default=None)
def create(
    agent_id: str | None,
    kind: str,
    name: str | None,
    config_json: str,
    as_user: str | None,
) -> None:
    """Create a channel."""
    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)
    from octop.cli.support.offline_ops import create_channel_offline
    from octop.infra.errors import OctopError

    try:
        data = create_channel_offline(
            agent_id=aid,
            user_id=user_id,
            kind=kind,
            name=name or kind,
            config=_parse_json_object("config", config_json),
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(data, indent=2))


@channel.command("patch")
@click.option("--agent", "agent_id", default=None)
@click.argument("channel_id")
@click.option("--name", default=None)
@click.option("--enabled/--disabled", default=None)
@click.option("--config", "config_json", default=None, help="JSON config patch")
@click.option("--user", "as_user", default=None)
def patch_channel(
    agent_id: str | None,
    channel_id: str,
    name: str | None,
    enabled: bool | None,
    config_json: str | None,
    as_user: str | None,
) -> None:
    """Update channel fields."""
    aid = require_agent(agent_id)
    _resolve_user(aid, as_user)
    if name is None and enabled is None and config_json is None:
        raise click.ClickException(
            "nothing to patch; pass --name, --enabled/--disabled, or --config"
        )
    from octop.cli.support.offline_ops import patch_channel_offline
    from octop.infra.errors import OctopError

    config = _parse_json_object("config", config_json) if config_json is not None else None
    try:
        data = patch_channel_offline(
            aid,
            channel_id,
            name=name,
            config=config,
            enabled=enabled,
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(data, indent=2))


@channel.command("delete")
@click.option("--agent", "agent_id", default=None)
@click.argument("channel_id")
@click.option("--user", "as_user", default=None)
def delete(agent_id: str | None, channel_id: str, as_user: str | None) -> None:
    """Delete a channel."""
    aid = require_agent(agent_id)
    _resolve_user(aid, as_user)
    from octop.cli.support.offline_ops import delete_channel_offline
    from octop.infra.errors import OctopError

    try:
        delete_channel_offline(aid, channel_id)
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo("deleted")


@channel.command("test")
@click.option("--agent", "agent_id", default=None)
@click.argument("channel_id")
@click.option("--user", "as_user", default=None)
def test(agent_id: str | None, channel_id: str, as_user: str | None) -> None:
    """Probe a channel: instantiate, start(), then stop()."""
    from octop.cli.support.db import resolve_cli_locale
    from octop.cli.support.embedded_ops import test_channel
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    _resolve_user(aid, as_user)
    try:
        body = test_channel(aid, channel_id, locale=resolve_cli_locale())
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    if body.get("ok"):
        click.echo("ok")
        return
    click.echo(f"failed: {body.get('error', 'unknown error')}", err=True)
    raise SystemExit(1)


@channel.group("bind")
def bind_group() -> None:
    """QR-based channel binding (QQ / WeCom / WeChat)."""


@bind_group.command("qq")
@click.option("--agent", "agent_id", default=None)
@click.option("--channel-id", default=None, help="Existing channel to update (optional).")
@click.option("--user", "as_user", default=None)
def bind_qq(agent_id: str | None, channel_id: str | None, as_user: str | None) -> None:
    """Scan with mobile QQ and save QQ Bot application credentials."""
    import asyncio

    from octop.cli.support.offline_ops import (
        create_channel_offline,
        get_channel_offline,
        patch_channel_offline,
    )
    from octop.cli.support.qr import render_qrcode_terminal
    from octop.infra.gateway.channels import qr_bind

    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)
    session_id = f"cli:{aid}"
    try:
        data = asyncio.run(qr_bind.qq_qr_generate(session_id))
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    token = data.get("qrcode_token")
    qr_url = data.get("qrcode_url")
    if not token or not qr_url:
        raise click.ClickException("unexpected QQ QR response")

    click.echo("Scan with mobile QQ:")
    render_qrcode_terminal(qr_url)
    click.echo("Waiting for scan confirmation…")
    deadline = time.time() + 180
    credentials: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            result = asyncio.run(qr_bind.qq_qr_poll(session_id, token))
        except Exception:
            time.sleep(2)
            continue
        status = result.get("status")
        if status == "success" and result.get("app_id") and result.get("secret"):
            credentials = result
            break
        if status in {"error", "expired"}:
            raise click.ClickException(result.get("message") or "QQ QR binding failed")
        time.sleep(2)

    if credentials is None:
        raise click.ClickException("QQ QR scan timed out")
    click.echo(click.style("QQ Bot binding successful.", fg="green"))
    cfg = {
        "app_id": credentials["app_id"],
        "secret": credentials["secret"],
        "enabled": True,
    }
    try:
        if channel_id:
            existing = get_channel_offline(aid, channel_id)
            cfg = {**existing.get("config", {}), **cfg}
            row = patch_channel_offline(aid, channel_id, config=cfg, enabled=True)
        else:
            row = create_channel_offline(
                agent_id=aid,
                user_id=user_id,
                kind="qq",
                name="qq",
                config=cfg,
            )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(row, indent=2))


@bind_group.command("wecom")
@click.option("--agent", "agent_id", default=None)
@click.option("--channel-id", default=None, help="Existing channel to update (optional).")
@click.option("--user", "as_user", default=None)
def bind_wecom(agent_id: str | None, channel_id: str | None, as_user: str | None) -> None:
    """Scan WeCom QR code and save bot credentials."""
    import asyncio

    from octop.cli.support.offline_ops import create_channel_offline, patch_channel_offline
    from octop.cli.support.qr import render_qrcode_terminal
    from octop.infra.gateway.channels import qr_bind

    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)
    try:
        data = asyncio.run(qr_bind.wecom_qr_generate())
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    scode = data.get("scode")
    auth_url = data.get("auth_url")
    if not scode or not auth_url:
        raise click.ClickException("unexpected QR response")
    click.echo("Scan with WeCom:")
    render_qrcode_terminal(auth_url)
    click.echo("Waiting for scan…")
    deadline = time.time() + 180
    bot_id = secret = None
    while time.time() < deadline:
        try:
            result = asyncio.run(qr_bind.wecom_qr_poll(scode))
        except Exception:
            time.sleep(3)
            continue
        if result.get("status") == "success":
            bot_id = result.get("bot_id")
            secret = result.get("secret")
            if bot_id and secret:
                break
        time.sleep(3)
    if not bot_id or not secret:
        raise click.ClickException("QR scan timed out or failed")
    click.echo(click.style("Scan successful.", fg="green"))
    cfg = {"bot_id": bot_id, "secret": secret, "enabled": True}
    try:
        if channel_id:
            row = patch_channel_offline(aid, channel_id, config=cfg, enabled=True)
        else:
            row = create_channel_offline(
                agent_id=aid,
                user_id=user_id,
                kind="wecom",
                name="wecom",
                config=cfg,
            )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(_json.dumps(row, indent=2))


@bind_group.command("weixin")
@click.option("--agent", "agent_id", default=None)
@click.option("--channel-id", default=None)
@click.option("--user", "as_user", default=None)
def bind_weixin(agent_id: str | None, channel_id: str | None, as_user: str | None) -> None:
    """Scan WeChat QR code and save account credentials."""
    import asyncio

    from octop.cli.support.offline_ops import create_channel_offline, patch_channel_offline
    from octop.cli.support.qr import render_qrcode_terminal
    from octop.infra.gateway.channels import qr_bind

    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)
    try:
        data = asyncio.run(qr_bind.weixin_qr_generate())
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    token = data.get("qrcode_token")
    qr_url = data.get("qrcode_url")
    if not token or not qr_url:
        raise click.ClickException("unexpected QR response")
    click.echo("Scan with WeChat:")
    render_qrcode_terminal(qr_url)
    click.echo("Waiting for scan confirmation…")
    deadline = time.time() + 120
    account = None
    while time.time() < deadline:
        try:
            result = asyncio.run(qr_bind.weixin_qr_poll(str(token)))
        except Exception:
            time.sleep(3)
            continue
        status = result.get("status")
        if status == "success":
            account = {
                "account_id": result.get("account_id") or "weixin",
                "token": result.get("token") or "",
                "base_url": result.get("base_url") or "https://ilink.b.qq.com",
                "bot_uin": result.get("account_id") or "",
                "configured": True,
            }
            break
        if status == "error":
            raise click.ClickException(result.get("message") or "scan failed")
        time.sleep(3)
    if account is None:
        raise click.ClickException("QR scan timed out or failed")
    click.echo(click.style("Scan successful.", fg="green"))
    cfg = {"accounts": [account], "enabled": True}
    try:
        if channel_id:
            row = patch_channel_offline(aid, channel_id, config=cfg, enabled=True)
        else:
            row = create_channel_offline(
                agent_id=aid,
                user_id=user_id,
                kind="weixin",
                name="weixin",
                config=cfg,
            )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(click.style("WeChat account linked.", fg="green"))
    click.echo(_json.dumps(row, indent=2))


@channel.command("config")
@click.option("--agent", "agent_id", default=None)
@click.option("--user", "as_user", default=None)
def config_channels(agent_id: str | None, as_user: str | None) -> None:
    """Interactively create or configure a channel."""
    from octop.cli.support import prompts as _prompts

    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)
    from octop.cli.support.offline_ops import create_channel_offline, patch_channel_offline
    from octop.infra.errors import OctopError

    kinds = ["feishu", "wecom", "weixin", "qq", "dingtalk", "telegram", "yuanbao"]
    kind = _prompts.select("Channel kind:", choices=kinds)
    name = _prompts.text("Channel name:", default=kind)
    try:
        row = create_channel_offline(
            agent_id=aid,
            user_id=user_id,
            kind=kind,
            name=name,
            config={"enabled": False},
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    cid = row.get("id") or row.get("channel_id")
    click.echo(f"Created channel {cid} ({kind})")

    if kind in ("qq", "wecom", "weixin"):
        if _prompts.confirm(f"Run QR bind for {kind} now?", default=True):
            ctx = click.get_current_context()
            if kind == "qq":
                ctx.invoke(bind_qq, agent_id=aid, channel_id=cid, as_user=as_user)
            elif kind == "wecom":
                ctx.invoke(bind_wecom, agent_id=aid, channel_id=cid, as_user=as_user)
            else:
                ctx.invoke(bind_weixin, agent_id=aid, channel_id=cid, as_user=as_user)
        return

    if kind == "feishu":
        if _prompts.confirm("Run Feishu bot-creator (QR) instead of manual entry?", default=True):
            ctx = click.get_current_context()
            ctx.invoke(
                feishu_setup,
                agent_id=aid,
                channel_id=cid,
                platform="feishu",
                as_user=as_user,
            )
            return
        app_id = _prompts.text("Feishu App ID:")
        app_secret = _prompts.password("Feishu App Secret:")
        cfg = {"app_id": app_id, "app_secret": app_secret, "enabled": True}
    elif kind == "qq":
        app_id = _prompts.text("QQ App ID:")
        secret = _prompts.password("QQ Client Secret:")
        visibility = _prompts.select(
            "QQ group message visibility granted by group owners:",
            choices=["auto", "all", "mention_recent", "mention_only"],
        )
        activation = "mention"
        if visibility == "all":
            activation = _prompts.select(
                "When should the agent reply in groups?",
                choices=["mention", "always"],
            )
        history = "none" if visibility == "mention_only" else "recent"
        cfg = {
            "app_id": app_id,
            "client_secret": secret,
            "enabled": True,
            "group_context": {
                "enabled": True,
                "visibility": visibility,
                "activation": activation,
                "history": history,
                "history_limit": 10,
            },
        }
    else:
        cfg = {"enabled": _prompts.confirm("Enable channel?", default=True)}

    prefix = _prompts.text("Bot prefix (optional):", default="")
    if prefix:
        cfg["bot_prefix"] = prefix

    try:
        patch_channel_offline(
            aid,
            str(cid),
            config=cfg,
            enabled=bool(cfg.get("enabled", True)),
        )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo("Channel configured.")


@channel.command("feishu-setup")
@click.option("--agent", "agent_id", default=None)
@click.option("--channel-id", default=None, help="Update existing feishu channel.")
@click.option("--platform", default="feishu", type=click.Choice(["feishu", "lark"]))
@click.option("--user", "as_user", default=None)
@click.option("--dry-run", is_flag=True, help="Print steps without starting bot-creator.")
@click.option("--retries", default=1, show_default=True, help="Restart bot-creator on failure.")
def feishu_setup(
    agent_id: str | None,
    channel_id: str | None,
    platform: str,
    as_user: str | None,
    dry_run: bool,
    retries: int,
) -> None:
    """Run Feishu scan-to-create (lark-oapi QR) and save app credentials."""
    from octop.cli.support.feishu_creator import dry_run_feishu_setup, run_feishu_bot_creator
    from octop.cli.support.offline_ops import create_channel_offline, patch_channel_offline
    from octop.infra.errors import OctopError

    aid = require_agent(agent_id)
    user_id = _resolve_user(aid, as_user)

    if dry_run:
        dry_run_feishu_setup(agent_id=aid, platform=platform, channel_id=channel_id)
        return

    if retries < 1:
        raise click.ClickException("--retries must be >= 1")

    app_id = app_secret = None
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        if attempt > 1:
            click.echo(click.style(f"Retry {attempt}/{retries}…", fg="yellow"))
        try:
            app_id, app_secret = run_feishu_bot_creator(platform=platform)
            break
        except click.ClickException as exc:
            last_err = exc
            if attempt >= retries:
                raise
    else:
        if last_err:
            raise last_err
        raise click.ClickException("Feishu bot-creator failed")

    cfg = {"app_id": app_id, "app_secret": app_secret, "enabled": True}
    try:
        if channel_id:
            row = patch_channel_offline(aid, channel_id, config=cfg, enabled=True)
        else:
            row = create_channel_offline(
                agent_id=aid,
                user_id=user_id,
                kind="feishu",
                name="feishu",
                config=cfg,
            )
    except OctopError as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(click.style("Feishu channel configured.", fg="green"))
    click.echo(_json.dumps(row, indent=2))
