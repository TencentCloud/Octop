"""Composition root — wire OctopServer, FastAPI, and uvicorn for ``octop run``."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress
from typing import Any

from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)


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
    import uvicorn

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
    if ssl_certfile is None and ssl_keyfile is None:
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
        )
        companion = build_http_companion_app(https_port=plan.https_port)
        http_config = uvicorn.Config(
            companion,
            host=plan.bind_host,
            port=plan.http_port,
            log_level=level,
            workers=1,
            reload=False,
        )
        servers.append(uvicorn.Server(https_config))
        servers.append(uvicorn.Server(http_config))
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
        )
        servers.append(uvicorn.Server(single_config))

    from octop.infra.agents.memory.slim_control import MemorySlimControl

    memory_control = MemorySlimControl(srv)
    try:
        await memory_control.start()
        await asyncio.gather(*(_serve(s) for s in servers))
    finally:
        await memory_control.close()
        await _cancel_background_task(bwrap_task)
        await srv.stop()


def _apply_nofile_floor(resource: Any) -> tuple[int, int] | None:
    """Raise the soft NOFILE limit toward the hard cap; ``(soft, hard)`` if applied."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = max(soft, 65535) if hard == resource.RLIM_INFINITY else hard
    if soft >= target:
        return None
    resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    return (target, hard)


def _raise_nofile_soft_limit(resource_module: Any = None) -> None:
    """Raise the soft fd limit to the hard cap (POSIX only, best effort).

    Multi-agent installs keep one SQLite pool per agent, so the common 1024
    soft cap is the ceiling long before the hard cap matters (#2060): a busy
    registry baseline sits near the soft cap and tips into an EMFILE storm.
    Containers may deny ``setrlimit`` — never fail the boot over it.
    """
    if resource_module is None:
        try:
            import resource as _resource  # noqa: PLC0415
        except ImportError:  # pragma: no cover - Windows has no resource module
            return
        resource_module = _resource
    try:
        applied = _apply_nofile_floor(resource_module)
    except (OSError, ValueError):
        logger.warning("could not raise NOFILE soft limit", exc_info=True)
        return
    if applied is not None:
        logger.info("raised NOFILE soft limit %d -> %d", applied[0], applied[1])


def run_foreground_blocking(**kwargs: Any) -> None:
    """Sync entry for Click commands and tests."""
    _raise_nofile_soft_limit()
    asyncio.run(run_foreground(**kwargs))
