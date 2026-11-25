"""Composition root — wire OctopServer, FastAPI, and uvicorn for ``octop run``."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

import uvicorn

from octop.infra.desktop import desktop_shell_enabled
from octop.infra.server import OctopServer
from octop.infra.utils.accept_errors import coalesce_accept_errors

logger = logging.getLogger(__name__)

# uvicorn's default ping_timeout is 20s. A busy peer — demo.octop.chat runs
# dozens of agents on one event loop — often reads the pong later than that
# and then closes the socket with 1011 "keepalive ping timeout". The dialer
# redials at once, so cloud collab looks like it is flapping. Keep sending
# pings; do not drop the connection on a late pong. BridgeSession's
# application heartbeat still detects a half-open link.
_WS_PING_INTERVAL = 20.0
_WS_PING_TIMEOUT: float | None = None

# Bound the drain so a wedged stream cannot block process exit forever.
_GRACEFUL_SHUTDOWN_TIMEOUT = 5


class _OctopUvicornServer(uvicorn.Server):
    """uvicorn server whose signal handling is owned by ``launch``.

    ``uvicorn.Server.capture_signals`` restores ``SIG_DFL`` and re-raises the
    signal on exit, which kills the process before ``run_foreground`` can run
    its ``finally``: ``Gateway.shutdown`` and ``db.close()`` never execute and
    the whole in-flight turn is lost. The handlers installed by
    :func:`_capture_shutdown_signals` only flip ``should_exit`` instead.
    """

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except ValueError:  # pragma: no cover - platform specific numbers
        return str(signum)


@contextmanager
def _capture_shutdown_signals(servers: list[uvicorn.Server], srv: OctopServer) -> Iterator[None]:
    """Drain in-flight turns on the first shutdown signal.

    The first signal starts the drain (preempt blocked streams, stop the
    listeners) and never re-raises, so the caller's ``finally`` still closes
    the database. A second signal forces the exit for unresponsive streams.
    """
    watched = [signal.SIGINT, signal.SIGTERM]
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        watched.append(sigbreak)
    previous: dict[int, Any] = {}
    draining = False

    def _handle(signum: int, _frame: Any) -> None:
        nonlocal draining
        name = _signal_name(signum)
        if draining:
            logger.warning("received %s during shutdown; forcing exit", name)
            for server in servers:
                server.force_exit = True
            return
        draining = True
        logger.info("received %s; draining in-flight turns", name)
        try:
            srv.begin_shutdown()
        except Exception:
            logger.warning("failed to begin graceful shutdown", exc_info=True)
        for server in servers:
            server.should_exit = True

    for sig in watched:
        try:
            previous[sig] = signal.signal(sig, _handle)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            logger.debug("cannot install handler for signal %s", _signal_name(sig))
    try:
        yield
    finally:
        for restored_sig, handler in previous.items():
            try:
                signal.signal(restored_sig, handler)
            except (ValueError, OSError):  # pragma: no cover - non-main thread
                logger.debug("cannot restore handler for signal %s", _signal_name(restored_sig))


def _ensure_linux_bubblewrap() -> None:
    """Best-effort startup provisioning; never fail the ``octop run`` process."""
    try:
        from octop.infra.utils.bwrap import ensure_bubblewrap

        result = ensure_bubblewrap()
    except Exception:
        logger.warning("background bubblewrap provisioning failed", exc_info=True)
        return
    status = result.get("status")
    detail = result.get("detail")
    if status == "degraded":
        logger.warning("background bubblewrap provisioning degraded: %s", detail or "unknown")
    else:
        logger.info("background bubblewrap provisioning status=%s", status)


def _schedule_linux_bubblewrap_ensure() -> asyncio.Task[None] | None:
    """Run bubblewrap provisioning once in the background on Linux."""
    if not sys.platform.startswith("linux"):
        return None
    return asyncio.create_task(
        asyncio.to_thread(_ensure_linux_bubblewrap),
        name="ensure-linux-bubblewrap",
    )


async def _cancel_background_task(task: asyncio.Task[None] | None) -> None:
    """Drop a startup background task on shutdown; never raise."""
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _serve(server: Any) -> None:
    await server.serve()


async def run_foreground(
    *,
    host: str | None,
    port: int | None,
    reload: bool,
    workers: int,
    log_level: str | None,
    ssl_certfile: str | None,
    ssl_keyfile: str | None,
) -> None:
    """Boot the domain server, serve the HTTP API, then shut down cleanly."""
    from octop.api.app import build_app
    from octop.infra.bridge.transport import BRIDGE_WS_MAX_BYTES
    from octop.infra.setup.tls.http_companion import build_http_companion_app
    from octop.infra.setup.tls.listeners import build_listen_plan
    from octop.infra.setup.tls.store import resolve_tls_paths

    srv = OctopServer()
    await srv.start()
    bwrap_task = _schedule_linux_bubblewrap_ensure()
    # Greenfield deferral leaves services unset until /setup/database binds.
    cfg = srv.services.config if srv.services is not None else srv.config
    assert cfg is not None
    bind_host = host or cfg.bind_host
    bind_port = port or cfg.port
    if desktop_shell_enabled():
        # Desktop-hosted sidecar always serves one loopback HTTP listener; it
        # must ignore any persisted TLS / dual-port configuration.
        ssl_certfile = None
        ssl_keyfile = None
    elif ssl_certfile is None and ssl_keyfile is None:
        ssl_certfile, ssl_keyfile = resolve_tls_paths(srv.paths.root, cfg.tls)

    plan = build_listen_plan(
        cfg,
        bind_host=bind_host,
        bind_port=bind_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
    level = (log_level or cfg.log_level).lower()
    worker_count = 1 if plan.dual_listeners or reload else workers
    if plan.dual_listeners and (reload or workers > 1):
        logger.warning(
            "TLS dual-port mode forces workers=1 and disables reload",
        )
        reload = False

    app = build_app(srv)
    servers: list[uvicorn.Server] = []

    if plan.dual_listeners:
        assert plan.https_port is not None
        assert plan.http_port is not None
        https_config = uvicorn.Config(
            app,
            host=plan.bind_host,
            port=plan.https_port,
            log_level=level,
            workers=worker_count,
            reload=False,
            ssl_certfile=plan.ssl_certfile,
            ssl_keyfile=plan.ssl_keyfile,
            ws_max_size=BRIDGE_WS_MAX_BYTES,
            ws_ping_interval=_WS_PING_INTERVAL,
            ws_ping_timeout=_WS_PING_TIMEOUT,
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
        )
        companion = build_http_companion_app(https_port=plan.https_port)
        http_config = uvicorn.Config(
            companion,
            host=plan.bind_host,
            port=plan.http_port,
            log_level=level,
            workers=1,
            reload=False,
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
        )
        servers.append(_OctopUvicornServer(https_config))
        servers.append(_OctopUvicornServer(http_config))
        logger.info(
            "Listening on https://%s:%s and http://%s:%s (ACME + redirect)",
            plan.bind_host,
            plan.https_port,
            plan.bind_host,
            plan.http_port,
        )
    else:
        single_config = uvicorn.Config(
            app,
            host=plan.bind_host,
            port=plan.http_port or bind_port,
            log_level=level,
            workers=worker_count,
            reload=reload,
            ssl_certfile=plan.ssl_certfile,
            ssl_keyfile=plan.ssl_keyfile,
            ws_max_size=BRIDGE_WS_MAX_BYTES,
            ws_ping_interval=_WS_PING_INTERVAL,
            ws_ping_timeout=_WS_PING_TIMEOUT,
            timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_TIMEOUT,
        )
        servers.append(_OctopUvicornServer(single_config))

    from octop.infra.agents.memory.slim_control import MemorySlimControl

    memory_control = MemorySlimControl(srv)
    with (
        _capture_shutdown_signals(servers, srv),
        coalesce_accept_errors(asyncio.get_running_loop()),
    ):
        try:
            await memory_control.start()
            await asyncio.gather(*(_serve(s) for s in servers))
        finally:
            await memory_control.close()
            await _cancel_background_task(bwrap_task)
            await srv.stop()


def run_foreground_blocking(**kwargs: Any) -> None:
    """Sync entry for Click commands and tests."""
    asyncio.run(run_foreground(**kwargs))
