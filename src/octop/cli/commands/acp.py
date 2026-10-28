"""`octop acp` — run Octop agent as an ACP server over stdio."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import click


@dataclass(frozen=True, slots=True)
class _ExpertInfo:
    """Agent advertised to inbound ACP as a session config option."""

    value: str
    name: str
    description: str = ""


def _resolve_agent_ref(registry: Any, ref: str) -> str:
    """Resolve ``--agent`` to a public agent id (accepts id or display name)."""
    token = ref.strip()
    if not token:
        raise click.ClickException("agent ref is empty")

    rows = list(registry.list_rows())
    by_id = {row.agent_id: row for row in rows}
    if token in by_id:
        return token

    needle = token.casefold()
    name_hits = [row for row in rows if (row.name or "").strip().casefold() == needle]
    if len(name_hits) == 1:
        return str(name_hits[0].agent_id)
    if len(name_hits) > 1:
        ids = ", ".join(row.agent_id for row in name_hits)
        raise click.ClickException(
            f"agent name {token!r} is ambiguous; matches: {ids}. Pass an agent id instead.",
        )
    raise click.ClickException(
        f"agent {token!r} not found (use agent id or exact display name)",
    )


def _resolve_default_agent_id(registry: Any, agent_id: str | None) -> str:
    from octop.cli.support.state import default_state_path, load

    aid = agent_id
    if not aid:
        state = load(default_state_path())
        aid = state.default_agent
    if not aid:
        rows = registry.list_rows()
        if not rows:
            raise click.ClickException(
                "no agent found; create one in the dashboard or pass --agent",
            )
        return str(rows[0].agent_id)
    return _resolve_agent_ref(registry, str(aid))


def _expert_from_row(row: Any) -> _ExpertInfo:
    aid = str(row.agent_id)
    return _ExpertInfo(
        value=aid,
        name=(row.name or aid).strip() or aid,
        description=(row.description or "").strip(),
    )


def _load_acp_experts(agent_id: str | None) -> tuple[str, list[_ExpertInfo]]:
    """Load all local agents as ACP expert options; resolve the default id.

    Default is ``--agent`` / CLI ``default_agent`` / first enabled agent. All
    enabled agents are advertised so the IDE can switch without restarting;
    only the default is started at process boot (others start on first use).
    """
    from octop.cli.support.db import open_cli_services

    with open_cli_services() as svc:
        rows = list(svc.agent_repo.list_all(include_disabled=False))

    class _Rows:
        def list_rows(self) -> list[Any]:
            return rows

    if not rows:
        raise click.ClickException(
            "no agent found; create one in the dashboard or pass --agent",
        )

    default_id = _resolve_default_agent_id(_Rows(), agent_id)
    by_id = {str(row.agent_id): row for row in rows}
    if default_id not in by_id:
        raise click.ClickException(f"agent {default_id!r} not found")

    # Default first so clients that ignore currentValue still pick a sensible option.
    ordered = [by_id[default_id], *[row for row in rows if str(row.agent_id) != default_id]]
    return default_id, [_expert_from_row(row) for row in ordered]


def _resolve_boot_agent_id(agent_id: str | None) -> str:
    """Resolve default expert id (tests / callers that only need the id)."""
    default_id, _experts = _load_acp_experts(agent_id)
    return default_id


def _running_experts(registry: Any) -> list[_ExpertInfo]:
    """Collect running agents as ACP expert options (name + description)."""
    experts: list[_ExpertInfo] = []
    for row in registry.list_rows():
        try:
            registry.get_agent(row.agent_id)
        except Exception:
            continue
        experts.append(_expert_from_row(row))
    return experts


def _experts_as_mapping(experts: list[_ExpertInfo]) -> dict[str, dict[str, str]]:
    return {item.value: {"name": item.name, "description": item.description} for item in experts}


async def _ensure_running_harness(registry: Any, expert_id: str) -> Any:
    """Return a live harness for ``expert_id``, starting the agent if needed."""
    try:
        return registry.get_agent(expert_id)
    except Exception:
        pass
    try:
        await registry.start(expert_id)
    except Exception as exc:
        raise RuntimeError(f"agent {expert_id!r} failed to start: {exc}") from exc
    try:
        return registry.get_agent(expert_id)
    except Exception as exc:
        raise RuntimeError(f"agent {expert_id!r} is not running: {exc}") from exc


async def _run_acp_server(*, agent_id: str | None, debug: bool) -> None:
    from octop_harness.acp.server import run_harness_acp_server

    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    # Advertise every local agent immediately; boot only the default so Zed's
    # Loading… is not blocked. Switching experts starts that agent on demand.
    aid, expert_list = _load_acp_experts(agent_id)
    experts = _experts_as_mapping(expert_list)

    ready = asyncio.Event()
    holder: dict[str, Any] = {}
    boot_errors: list[BaseException] = []

    async def _boot() -> None:
        from octop.infra.server import OctopServer

        try:
            srv = OctopServer()
            await srv.start(boot_agent_ids=frozenset({aid}))
            assert srv.app_runtime is not None
            registry = srv.app_runtime.agent_registry
            try:
                registry.get_agent(aid)
            except Exception as exc:
                raise click.ClickException(f"agent {aid!r} is not running: {exc}") from exc
            holder["srv"] = srv
            holder["registry"] = registry
        except BaseException as exc:
            boot_errors.append(exc)
            raise
        finally:
            ready.set()

    async def _resolve_harness(expert_id: str) -> Any:
        await ready.wait()
        if boot_errors:
            raise RuntimeError(f"octop acp boot failed: {boot_errors[0]}") from boot_errors[0]
        return await _ensure_running_harness(holder["registry"], expert_id)

    boot_task = asyncio.create_task(_boot(), name="octop-acp-boot")
    try:
        # Listen on stdio immediately — Zed's "Loading…" ends at initialize,
        # which does not need the harness. First prompt / load awaits ready.
        await run_harness_acp_server(
            None,
            agent_id=aid,
            experts=experts,
            resolve_harness=_resolve_harness,
        )
    finally:
        if not boot_task.done():
            boot_task.cancel()
            with suppress(asyncio.CancelledError):
                await boot_task
        srv = holder.get("srv")
        if srv is not None:
            await srv.stop()
        elif boot_task.done() and not boot_task.cancelled():
            with suppress(Exception):
                boot_task.result()


@click.command("acp")
@click.option(
    "--agent",
    "agent_id",
    default=None,
    help=(
        "Optional default expert (id or exact display name). "
        "Omit to use CLI default_agent or the first local agent; "
        "all agents are still listed for the client to pick."
    ),
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging to stderr")
def acp_cmd(agent_id: str | None, debug: bool) -> None:
    """Start Octop as an ACP agent (stdio) for IDE clients (Zed, OpenCode, WorkBuddy, …).

    All local agents are advertised as session configOptions (id=expert). Clients that
    support session/set_config_option can switch experts without restarting; the default
    expert starts at boot, others start on first use.
    """
    from octop.cli.support.ctx import resolve_agent

    aid = resolve_agent(agent_id)
    try:
        asyncio.run(_run_acp_server(agent_id=aid, debug=debug))
    except click.ClickException:
        raise
    except KeyboardInterrupt:
        raise SystemExit(0) from None
