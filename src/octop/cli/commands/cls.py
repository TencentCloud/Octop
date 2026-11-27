"""Manage a running server's Tencent Cloud CLS tracing configuration."""

from __future__ import annotations

import json
import locale
import os
import sys
from typing import Any

import click
import httpx

from octop.cli.support.ctx import json_output_enabled
from octop.i18n import lookup, normalize_locale, tr


def _locale() -> str:
    return normalize_locale(locale.getlocale()[0])


def _msg(key: str, **values: object) -> str:
    return tr(f"cls_cli.{key}", _locale(), **values)


@click.group("cls")
@click.option(
    "--server-url",
    envvar="OCTOP_SERVER_URL",
    default="http://127.0.0.1:8088",
    show_default=True,
    help="Octop server URL (OCTOP_SERVER_URL).",
)
@click.pass_context
def cls_group(ctx: click.Context, server_url: str) -> None:
    """Manage Tencent Cloud CLS tracing on a running Octop server."""
    ctx.obj = ctx.with_resource(
        httpx.Client(base_url=server_url, timeout=60.0, headers={"Accept-Language": _locale()})
    )


def _request(
    client: httpx.Client, method: str, suffix: str = "", body: dict[str, Any] | None = None
) -> dict[str, Any]:
    if "Authorization" not in client.headers:
        token = os.environ.get("OCTOP_ACCESS_TOKEN", "").strip()
        if not token:
            if not sys.stdin.isatty():
                raise click.ClickException(_msg("token_required"))
            token = click.prompt(_msg("token"), hide_input=True, err=True)
        client.headers["Authorization"] = f"Bearer {token}"
    try:
        resp = client.request(method, f"api/admin/observability/cls{suffix}", json=body)
    except httpx.RequestError as exc:
        raise click.ClickException(_msg("connection", reason=str(exc))) from exc
    try:
        data = resp.json()
    except ValueError:
        data = None
    if not resp.is_success:
        error = data.get("error") if isinstance(data, dict) else None
        message = error.get("message") if isinstance(error, dict) else resp.reason_phrase
        raise click.ClickException(f"HTTP {resp.status_code}: {message}")
    if not isinstance(data, dict):
        raise click.ClickException(_msg("invalid_response"))
    return data


def _display(data: dict[str, Any]) -> None:
    if json_output_enabled():
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for field, value in data.items():
        if value is None:
            value = _msg("unchecked")
        elif isinstance(value, bool):
            value = _msg("yes" if value else "no")
        label = lookup(f"cls_cli.{field}", _locale()) or field
        click.echo(f"{label}: {value}")


@cls_group.command("show")
@click.pass_obj
def show(client: httpx.Client) -> None:
    """Show effective CLS settings, including environment-based deployments."""
    cfg = _request(client, "GET", "/effective")
    cfg.pop("application_created", None)
    cfg["source"] = "environment" if cfg["active_backend"] == "cls_env" else "database"
    _display(cfg)


@cls_group.command("test")
@click.pass_obj
def test_connection(client: httpx.Client) -> None:
    """Check the management API and probe the configured OTLP trace endpoint."""
    result = _request(client, "POST", "/effective/test")
    _display(result)
    if not result["ok"]:
        raise click.exceptions.Exit(1)


def _credentials(current: dict[str, Any], wizard: bool) -> dict[str, str]:
    sid = os.environ.get("TENCENTCLOUD_SECRET_ID", "").strip()
    key = os.environ.get("TENCENTCLOUD_SECRET_KEY", "").strip()
    if sid or key:
        if not sid or not key:
            raise click.UsageError(_msg("pair_required"))
        if os.environ.get("TENCENTCLOUD_TOKEN", "").strip():
            raise click.UsageError(_msg("sts"))
        return {"secret_id": sid, "secret_key": key}
    saved_pair = current["secret_id_set"] and current["secret_key_set"]
    if saved_pair and not wizard:
        return {}
    if saved_pair and not click.confirm(
        _msg("replace_keys", masked=current["secret_id_masked"]), default=False, err=True
    ):
        return {}
    if not wizard and not sys.stdin.isatty():
        raise click.UsageError(_msg("pair_required"))
    return {
        "secret_id": click.prompt("SecretId", hide_input=True, err=True),
        "secret_key": click.prompt("SecretKey", hide_input=True, err=True),
    }


def _choose_application(
    client: httpx.Client, region: str, credentials: dict[str, str], access_type: str | None
) -> dict[str, Any]:
    result = _request(
        client,
        "POST",
        "/applications/list",
        {"region": region, "access_type": access_type, **credentials},
    )
    apps = [app for app in result["applications"] if app["topic_id"]]
    if not apps:
        raise click.ClickException(_msg("no_apps"))
    for index, app in enumerate(apps, 1):
        click.echo(
            f"{index}. {app['application_name']} ({app['access_type']}, {app['topic_id']})",
            err=True,
        )
    index = click.prompt(_msg("select_app"), type=click.IntRange(1, len(apps)), err=True)
    return dict(apps[index - 1])


@cls_group.command("configure")
@click.option(
    "--new", "new_app", is_flag=True, help="Create or reuse a matching AgentObs application."
)
@click.option("--existing", is_flag=True, help="Bind an existing Trace Topic.")
@click.option("--region", help="Tencent Cloud region.")
@click.option("--app-name", help="AgentObs application / service name.")
@click.option("--topic-id", help="Trace Topic ID for --existing.")
@click.option("--access-type", type=click.Choice(["Agent", "Langfuse"]))
@click.option("--internal/--public", default=None, help="Use the internal or public endpoint.")
@click.option("--mask-content/--no-mask-content", default=None, help="Mask trace content.")
@click.pass_obj
def configure(
    client: httpx.Client,
    new_app: bool,
    existing: bool,
    region: str | None,
    app_name: str | None,
    topic_id: str | None,
    access_type: str | None,
    internal: bool | None,
    mask_content: bool | None,
) -> None:
    """Enable CLS tracing. Omit the mode to use the interactive wizard."""
    if new_app and existing:
        raise click.UsageError(_msg("mode_conflict"))
    if new_app and topic_id is not None:
        raise click.UsageError(_msg("topic_conflict"))
    wizard = not (new_app or existing or topic_id is not None)
    stored = _request(client, "GET")
    current = (
        _request(client, "GET", "/effective") if stored["active_backend"] == "cls_env" else stored
    )
    if wizard:
        mode = click.prompt(
            _msg("mode"),
            type=click.Choice(["new", "existing"]),
            default="existing" if current["topic_id"] else "new",
            err=True,
        )
        new_app = mode == "new"
    default_region = current["region"] or "ap-guangzhou"
    if wizard and region is None:
        region = click.prompt(_msg("region"), default=default_region, err=True)
    region = (region or default_region).strip().lower()
    credentials = _credentials(stored, wizard)
    default_name = current["application_name"]
    if new_app and wizard and app_name is None:
        app_name = click.prompt(_msg("application_name"), default=default_name, err=True)

    app_id = ""
    if not new_app:
        old_topic = current["topic_id"] if region == current["region"] else ""
        if topic_id is None and (wizard or sys.stdin.isatty()):
            method = click.prompt(
                _msg("binding"), type=click.Choice(["topic", "list"]), default="topic", err=True
            )
            if method == "list":
                app = _choose_application(client, region, credentials, access_type)
                app_id, topic_id = app["application_id"], app["topic_id"]
                app_name, access_type = app["application_name"], app["access_type"]
            else:
                topic_id = click.prompt("Trace Topic ID", default=old_topic or None, err=True)
        if not topic_id or not topic_id.strip():
            raise click.UsageError(_msg("topic_required"))
        topic_id = topic_id.strip()
        if not app_id and topic_id == old_topic:
            app_id = current["application_id"]

    if current["active_backend"] == "langfuse":
        click.echo(_msg("switch_backend"), err=True)
    saved = _request(
        client,
        "PUT",
        body={
            "enabled": True,
            "region": region,
            "application_name": app_name or default_name,
            "application_id": app_id,
            "topic_id": topic_id or "",
            "auto_create_app": new_app,
            "access_type": access_type or current["access_type"],
            "use_internal_endpoint": current["use_internal_endpoint"]
            if internal is None
            else internal,
            "mask_content": current["mask_content"] if mask_content is None else mask_content,
            **credentials,
        },
    )
    action = "bound"
    if new_app:
        action = "created" if saved["application_created"] else "reused"
    if json_output_enabled():
        click.echo(json.dumps({"action": action, **saved}, ensure_ascii=False, indent=2))
    else:
        click.echo(
            _msg(
                action,
                name=saved["application_name"],
                region=saved["region"],
                topic=saved["topic_id"],
            )
        )
