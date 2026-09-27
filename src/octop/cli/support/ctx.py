"""Shared CLI context helpers — root-level option fallback.

The root ``cli`` accepts ``--user`` and ``--agent`` options that subcommands
inherit when not given explicitly. Subcommands keep their own ``--user`` /
``--agent`` options; this module provides a single resolver that picks the
explicit value first, falls back to ``ctx.obj`` (set by the root group), and
finally returns ``None``.

Importing ``octop.cli.support.ctx`` is cheap (no third-party imports), so it is
safe to call from any subcommand at the top of its body.
"""

from __future__ import annotations

from typing import Any

import click


def _root_obj() -> dict[str, Any]:
    """Return the root group's ``ctx.obj`` dict, or an empty dict.

    Looks up the *current* click context via ``click.get_current_context``;
    walks to the root so the lookup is reliable regardless of nesting depth.
    """
    try:
        ctx = click.get_current_context(silent=True)
    except RuntimeError:
        return {}
    if ctx is None:
        return {}
    root = ctx.find_root()
    obj = root.obj
    return obj if isinstance(obj, dict) else {}


def resolve_user(explicit: str | None) -> str | None:
    """Return the username to act as, falling back to root ``--user``."""
    if explicit is not None:
        return explicit
    return _root_obj().get("as_user")


def resolve_agent(explicit: str | None) -> str | None:
    """Return the agent id, falling back to root ``--agent`` then CLI state."""
    if explicit is not None:
        return explicit
    from_env = _root_obj().get("agent_id")
    if from_env:
        return str(from_env)
    from octop.cli.support.state import default_state_path, load

    pinned = load(default_state_path()).default_agent
    return str(pinned) if pinned else None


def json_output_enabled() -> bool:
    """Return True if the root ``--json`` flag was set."""
    return bool(_root_obj().get("json_out", False))


def require_agent(agent_id: str | None) -> str:
    """Resolve agent id or exit with code 2."""
    aid = resolve_agent(agent_id)
    if aid is None:
        click.echo("error: --agent is required (or set root --agent / OCTOP_AGENT)", err=True)
        raise SystemExit(2)
    return aid
