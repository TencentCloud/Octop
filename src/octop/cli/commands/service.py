"""`octop service` — install and manage the Octop system service."""

from __future__ import annotations

import click

from octop.infra.setup.service import (
    DEFAULT_HEALTH_ATTEMPTS,
    DEFAULT_HEALTH_DELAY_SECONDS,
    ServiceRuntime,
    ServiceScope,
    ServiceStatus,
    build_runtime,
    collect_service_status,
    install_service,
    launchd_domain,
    persist_bind_options,
    restart_service,
    start_service,
    stop_service,
    unit_path,
)


@click.group()
def service() -> None:
    """Manage the Octop system service (systemd on Linux, launchd on macOS)."""


def _runtime(host: str | None, port: int | None, scope: ServiceScope | None) -> ServiceRuntime:
    try:
        return build_runtime(host=host, port=port, scope=scope)
    except (FileNotFoundError, RuntimeError) as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from exc


def _fail(exc: Exception) -> None:
    click.echo(f"error: {exc}", err=True)
    raise SystemExit(1) from exc


def _resolve_scope(value: str) -> ServiceScope | None:
    """Convert a `--scope` CLI value into the value `build_runtime` expects.

    Returns ``None`` to mean "auto-detect"; ``"user"`` / ``"system"`` for
    explicit scopes.  Click-level validation already filters out anything
    other than these three tokens, so this raises on a programming error.
    """
    if value == "auto":
        return None
    if value not in ("user", "system"):
        raise click.BadParameter(f"scope must be 'user', 'system', or 'auto' (got {value!r})")
    return value  # type: ignore[return-value]


def _health_failure_hint(runtime: ServiceRuntime) -> str:
    log_path = runtime.home / "logs" / "octop.log"
    if runtime.mode == "systemd":
        journal = (
            "journalctl --user -u octop -n 80 --no-pager"
            if runtime.scope == "user"
            else "journalctl -u octop -n 80 --no-pager"
        )
        return f"hint: inspect logs with `{journal}` or `tail -n 80 {log_path}`"
    return (
        f"hint: inspect logs with `tail -n 80 {log_path}` "
        f"or `launchctl print {launchd_domain(runtime.scope)}`"
    )


def _describe_runtime(runtime: ServiceRuntime) -> str:
    path = unit_path(runtime.mode, scope=runtime.scope, run_as_user=runtime.run_as_user)
    if runtime.mode == "systemd":
        return f"scope: {runtime.scope}, unit: {path}"
    return f"scope: {runtime.scope}, plist: {path}, domain: {launchd_domain(runtime.scope)}"


def _echo_health(status: ServiceStatus, *, warn_only: bool, runtime: ServiceRuntime) -> None:
    if status.health_ok:
        click.echo(f"health: OK {status.health_detail}")
        return
    if status.health_detail is None:
        return
    click.echo(f"health: unreachable ({status.health_detail})", err=True)
    click.echo(_health_failure_hint(runtime), err=True)
    if not warn_only:
        raise SystemExit(1)


def _echo_summary_for(runtime: ServiceRuntime, *, warn_health: bool) -> None:
    info = collect_service_status(
        runtime,
        check_health=True,
        health_retries=DEFAULT_HEALTH_ATTEMPTS,
        health_delay_seconds=DEFAULT_HEALTH_DELAY_SECONDS,
    )
    click.echo(_describe_runtime(runtime))
    click.echo(f"service: {info.mode} active={info.active}")
    _echo_health(info, warn_only=warn_health, runtime=runtime)


@service.command("start")
@click.option("--host", default=None, help="Bind host saved to config.json before install.")
@click.option(
    "--port", default=None, type=int, help="Bind port saved to config.json before install."
)
@click.option("--force-install", is_flag=True, default=False, help="Rewrite the unit file.")
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help=(
        "Install scope.  Like LightClaw: root → system unit (/etc/systemd/system); "
        "other users → user unit (~/.config/systemd/user).  ``sudo`` from a normal "
        "user still installs a user unit for that user."
    ),
)
def start(host: str | None, port: int | None, force_install: bool, scope: str) -> None:
    """Install (if needed) and start the system service."""
    runtime = _runtime(host, port, _resolve_scope(scope))
    if host is not None or port is not None:
        persist_bind_options(runtime.home, host=host, port=port)
        runtime = _runtime(host, port, _resolve_scope(scope))
    try:
        install_service(runtime, force=force_install)
        start_service(runtime)
    except RuntimeError as exc:
        _fail(exc)
    _echo_summary_for(runtime, warn_health=True)


@service.command("stop")
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Stop scope.  Must match the scope the service was installed under.",
)
def stop(scope: str) -> None:
    """Stop the system service."""
    runtime = _runtime(None, None, _resolve_scope(scope))
    try:
        stop_service(runtime)
    except RuntimeError as exc:
        _fail(exc)
    info = collect_service_status(runtime, check_health=False)
    click.echo(_describe_runtime(runtime))
    click.echo(f"service: {info.mode} active={info.active}")


@service.command("restart")
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Restart scope.  Must match the scope the service was installed under.",
)
def restart(scope: str) -> None:
    """Restart the system service."""
    runtime = _runtime(None, None, _resolve_scope(scope))
    try:
        restart_service(runtime)
    except RuntimeError as exc:
        _fail(exc)
    _echo_summary_for(runtime, warn_health=True)


@service.command("status")
@click.option("--host", default=None, help="Health-check host (defaults from config.json).")
@click.option(
    "--port", default=None, type=int, help="Health-check port (defaults from config.json)."
)
@click.option(
    "--scope",
    default="auto",
    type=click.Choice(["user", "system", "auto"], case_sensitive=False),
    show_default=True,
    help="Service scope to inspect (must match the installed scope).",
)
@click.option("--no-health", is_flag=True, default=False, help="Skip HTTP health probe.")
def status(host: str | None, port: int | None, scope: str, no_health: bool) -> None:
    """Show system service and HTTP health status."""
    runtime = _runtime(host, port, _resolve_scope(scope))
    info = collect_service_status(
        runtime,
        check_health=not no_health,
        health_retries=DEFAULT_HEALTH_ATTEMPTS,
        health_delay_seconds=DEFAULT_HEALTH_DELAY_SECONDS,
    )
    if info.mode is None:
        click.echo(f"error: {info.detail}", err=True)
        raise SystemExit(1)
    click.echo(f"mode:      {info.mode}")
    click.echo(_describe_runtime(runtime))
    click.echo(f"installed: {info.installed}")
    click.echo(f"active:    {info.active}")
    if info.enabled is not None:
        click.echo(f"enabled:   {info.enabled}")
    if info.detail:
        click.echo(info.detail)
    if not no_health:
        _echo_health(info, warn_only=False, runtime=runtime)
