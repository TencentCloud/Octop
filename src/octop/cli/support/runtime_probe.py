"""Detect a live ``octop run`` instance so offline CLI writes can warn.

Offline commands write ``~/.octop`` directly; a running server keeps its
boot-time snapshot of providers / channels / cron jobs and will not see the
change until it restarts (see #952). Probe ``/api/health`` on the configured
bind address before hinting — never warn when nothing is listening.
"""

from __future__ import annotations

import click
import httpx

from octop.i18n import tr

_HINT_KEY = "cli.restart_hint"


def running_server_url(*, timeout: float = 0.5) -> str | None:
    """Base URL of a live ``octop run`` per ``config.json``, or ``None``.

    Best-effort by design: any failure (missing config, TLS-only listener,
    timeout, non-Octop listener) means "no hint" — the probe must never fail
    or slow down a CLI write.
    """
    try:
        from octop.config import load_config
        from octop.infra.utils.paths import PathLayout

        config_path = PathLayout.from_env().root / "config.json"
        if not config_path.exists():
            return None
        cfg = load_config(config_path)
    except Exception:
        return None
    host = cfg.bind_host or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    base = f"http://{host}:{cfg.port}"
    try:
        response = httpx.get(f"{base}/api/health", timeout=timeout)
        payload = response.json()
    except Exception:
        return None
    if response.status_code == 200 and payload.get("ok") is True:
        return base
    return None


def warn_if_server_running() -> None:
    """Echo a localized restart hint on stderr when an instance is live.

    stderr keeps ``--json`` output parseable; yellow + one line only.
    """
    url = running_server_url()
    if url is None:
        return
    from octop.cli.support.db import resolve_cli_locale

    click.echo(click.style(tr(_HINT_KEY, resolve_cli_locale(), url=url), fg="yellow"), err=True)
