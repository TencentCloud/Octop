"""octop-memory dashboard CLI command.

Usage:
    octop-memory dashboard
    octop-memory dashboard --db-path ~/.octopmemory/openclaw__default/memory.sqlite --namespace openclaw__default
    octop-memory dashboard --port 7861
"""

from __future__ import annotations

import socket
import webbrowser

import click


def _find_free_port(start: int = 7860, attempts: int = 10) -> int:
    """Try ports starting from ``start``, return the first free one."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find a free port in range {start}~{start + attempts - 1}")


@click.command("dashboard")
@click.option(
    "--db-path",
    default=None,
    envvar="OCTOP_MEMORY_DB",
    help="SQLite database path (default: fill in interactively in the dashboard).",
)
@click.option(
    "--namespace",
    "-n",
    default=None,
    envvar="OCTOP_MEMORY_NAMESPACE",
    help="Memory namespace (default: fill in interactively in the dashboard).",
)
@click.option(
    "--port",
    default=None,
    type=int,
    envvar="OCTOP_MEMORY_DASHBOARD_PORT",
    help="Listen port (default: auto-detect starting from 7860).",
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Listen address.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Don't open the browser automatically.",
)
def dashboard_cmd(
    db_path: str | None,
    namespace: str | None,
    port: int | None,
    host: str,
    no_browser: bool,
) -> None:
    """Launch the local memory visualization dashboard (FastAPI + static frontend).

    The dashboard provides visual browsing of OpenClaw / Hermes memory data,
    covering five views: Raw Events, Candidates, Atoms, Journal, and Episodes.
    """
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException("Missing dependency uvicorn. Run: pip install 'octop-memory[dashboard]'") from e

    try:
        from octop_memory.adapters.dashboard.server import app
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency fastapi. Run: pip install 'octop-memory[dashboard]'\nDetails: {e}"
        ) from e

    # Auto-detect a free port.
    actual_port = port if port is not None else _find_free_port(7860)

    url = f"http://{host}:{actual_port}"

    # Build the startup params hint.
    params_hint = []
    if db_path:
        params_hint.append(f"db_path={db_path}")
    if namespace:
        params_hint.append(f"namespace={namespace}")

    click.echo("=" * 60)
    click.echo("  octop-memory dashboard")
    click.echo("=" * 60)
    click.echo(f"  URL: {url}")
    if params_hint:
        click.echo(f"  Params: {', '.join(params_hint)}")
    click.echo("  Press Ctrl+C to stop the server")
    click.echo("=" * 60)

    # Inject db_path / namespace into app state so the frontend can skip
    # the connection setup step.
    if db_path or namespace:
        app.state.default_db_path = db_path or ""
        app.state.default_namespace = namespace or ""

    if not no_browser:
        # Open the browser after a short delay, waiting for the server to start.
        import threading

        def _open_browser() -> None:
            import time

            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=actual_port, log_level="warning")
