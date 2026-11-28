"""Server extensions: packages built on Octop plug in without patching it.

An installed distribution declares an entry point in the ``octop.extensions``
group that points at an object (module, instance, or class instance)::

    [project.entry-points."octop.extensions"]
    my_product = "my_product.extension:extension"

Every hook is optional; Octop calls only the ones the object defines:

``on_startup(server)`` (async)
    After the runtime is up (database, agents, gateway, cron). Start background
    work here.
``on_shutdown(server)`` (async)
    First thing in ``OctopServer.stop``, while the database is still open.
``configure_app(app, server)``
    At the end of ``build_app``: include routers, add exception handlers.
``public_paths()``
    A :class:`PublicPaths` of API paths that skip JWT (the route must
    authenticate on its own) and that stay open before the first user exists.

Agent policy (sync; raise an ``OctopError`` to refuse):

``normalize_agent_config(config, *, agent_id, user_id, current)``
    Return the config to store. ``current`` is ``None`` on create (after
    Octop's own policy checks) and the stored config on every later write.
``check_agent_share(row, shared)``
    Before an agent's shared flag changes.
``check_agent_delete(row)``
    Before an agent is deleted.
``hide_agent_from_peers(row)``
    ``True`` keeps the agent out of team rosters and agent-to-agent calls.

Harness-level tools, skills, and channels keep using ``octop_harness.plugins``;
this group is for what lives in the Octop server itself.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)

EXTENSION_GROUP = "octop.extensions"


@dataclass(frozen=True)
class PublicPaths:
    """API paths an extension serves without the Octop JWT."""

    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    # Also reachable before setup creates the first user.
    setup_exact: tuple[str, ...] = ()
    setup_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadedExtension:
    name: str
    obj: Any = field(repr=False)


@cache
def load_extensions() -> tuple[LoadedExtension, ...]:
    """Load every ``octop.extensions`` entry point once per process, sorted by name.

    A broken extension is logged and skipped so it cannot take the server down.
    """
    loaded: list[LoadedExtension] = []
    for ep in sorted(entry_points(group=EXTENSION_GROUP), key=lambda e: e.name):
        try:
            loaded.append(LoadedExtension(name=ep.name, obj=ep.load()))
        except Exception:
            logger.exception("octop extension %r failed to load; skipped", ep.name)
    if loaded:
        logger.info("octop extensions: %s", ", ".join(e.name for e in loaded))
    return tuple(loaded)


def extension_hooks(name: str) -> list[tuple[str, Any]]:
    """``(extension name, bound hook)`` for every loaded extension that defines ``name``."""
    out: list[tuple[str, Any]] = []
    for ext in load_extensions():
        hook = getattr(ext.obj, name, None)
        if callable(hook):
            out.append((ext.name, hook))
    return out


@cache
def extension_public_paths() -> PublicPaths:
    """Union of every extension's :class:`PublicPaths`."""
    exact: list[str] = []
    prefixes: list[str] = []
    setup_exact: list[str] = []
    setup_prefixes: list[str] = []
    for ext_name, hook in extension_hooks("public_paths"):
        paths = hook()
        if not isinstance(paths, PublicPaths):
            logger.error("octop extension %r: public_paths() must return PublicPaths", ext_name)
            continue
        for value in (*paths.exact, *paths.prefixes, *paths.setup_exact, *paths.setup_prefixes):
            if not value.startswith("/api/"):
                raise ValueError(
                    f"extension {ext_name!r}: public path {value!r} is not under /api/"
                )
        exact.extend(paths.exact)
        prefixes.extend(paths.prefixes)
        setup_exact.extend(paths.setup_exact)
        setup_prefixes.extend(paths.setup_prefixes)
    return PublicPaths(
        exact=tuple(exact),
        prefixes=tuple(prefixes),
        setup_exact=tuple(setup_exact),
        setup_prefixes=tuple(setup_prefixes),
    )


def normalize_agent_config(
    config: dict[str, Any],
    *,
    agent_id: str,
    user_id: int | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    """Pass ``config`` through every extension's ``normalize_agent_config``."""
    for ext_name, hook in extension_hooks("normalize_agent_config"):
        result = hook(config, agent_id=agent_id, user_id=user_id, current=current)
        if not isinstance(result, dict):
            raise TypeError(f"extension {ext_name!r}: normalize_agent_config must return a dict")
        config = result
    return config


def check_agent_share(row: Any, shared: bool) -> None:
    for _ext_name, hook in extension_hooks("check_agent_share"):
        hook(row, shared)


def check_agent_delete(row: Any) -> None:
    for _ext_name, hook in extension_hooks("check_agent_delete"):
        hook(row)


def hide_agent_from_peers(row: Any) -> bool:
    if row is None:
        return False
    return any(hook(row) for _ext_name, hook in extension_hooks("hide_agent_from_peers"))


async def run_startup_hooks(server: Any) -> tuple[str, ...]:
    """Start extensions in load order; return the names that started.

    An extension without ``on_startup`` counts as started, so its
    ``on_shutdown`` still runs at stop. If one raises, the extensions that
    already started are shut down in reverse order and the error propagates.
    """
    started: list[str] = []
    for ext in load_extensions():
        hook = getattr(ext.obj, "on_startup", None)
        if callable(hook):
            logger.info("octop extension %r: starting", ext.name)
            try:
                await hook(server)
            except Exception:
                logger.exception("octop extension %r: on_startup failed", ext.name)
                await run_shutdown_hooks(server, started)
                raise
        started.append(ext.name)
    return tuple(started)


async def run_shutdown_hooks(server: Any, started: Sequence[str]) -> None:
    """Shut down ``started`` extensions in reverse order; one failure does not stop the rest."""
    hooks = dict(extension_hooks("on_shutdown"))
    for ext_name in reversed(started):
        hook = hooks.get(ext_name)
        if hook is None:
            continue
        try:
            await hook(server)
        except Exception:
            logger.exception("octop extension %r: on_shutdown failed", ext_name)
