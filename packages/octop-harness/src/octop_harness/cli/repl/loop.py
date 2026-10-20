"""REPL main loop — read input, route commands, stream agent responses."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from rich.console import Console

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.cli.repl.handler import StreamEventHandler
from octop_harness.cli.repl.slash_router import dispatch_slash
from octop_harness.cli.repl.state import SessionState
from octop_harness.cli.ui.input import create_prompt_session
from octop_harness.cli.ui.theme import Theme, get_theme
from octop_harness.cli.ui.toolbar import format_toolbar


async def run(
    agent_cfg: dict[str, Any],
    cli_cfg: dict[str, Any],
    model: str | None,
    session_id: str | None,
    agent_name: str | None = None,
) -> None:
    """Main REPL entry point.

    Lifecycle: init → welcome → loop → exit.
    """
    from octop_harness.cli.agents.manager import CliAgentManager
    from octop_harness.cli.config.paths import CliPaths

    # Resolve agent
    paths = CliPaths(project_dir=Path.cwd())
    mgr = CliAgentManager(paths.global_config_file)
    current_agent_name = agent_name or mgr.default_agent_name

    # Resolve agent profile against the already-loaded config (which has
    # credentials injected from env vars — reading from disk again would lose them).
    profile = mgr.get(current_agent_name)
    if profile is not None:
        # Strip non-agent keys that resolve() would strip
        top_level = {k: v for k, v in agent_cfg.items() if k not in ("agents", "default_agent", "cli")}
        resolved_cfg = profile.resolve(top_level)
    else:
        resolved_cfg = agent_cfg

    # Initialize
    console = Console()
    theme = get_theme(cli_cfg.get("theme", "dark"))
    sid = session_id or uuid.uuid4().hex
    model_name = model or resolved_cfg.get("default_model", "unknown")
    max_tokens = cli_cfg.get("context_window_tokens", 128_000)

    state = SessionState(
        session_id=sid,
        model=model_name,
        agent_cfg=resolved_cfg,
        current_agent=current_agent_name,
        max_tokens=max_tokens,
    )

    agent = _create_agent(resolved_cfg)

    # Prompt session
    history_file = Path.home() / ".octop-harness" / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = create_prompt_session(history_file=history_file)

    # Welcome
    project_dir = str(Path.cwd())
    config_path = Path.cwd() / ".octop-harness" / "config.json"
    print_welcome(console, theme, state, project_dir=project_dir, config_found=config_path.exists())

    # REPL loop
    while True:
        try:
            text = await session.prompt_async(
                "> ",
                bottom_toolbar=lambda: format_toolbar(state),
            )
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        text = text.strip()
        if not text:
            continue

        if text.startswith("/"):
            console.print()  # Spacing before command output (match AI response)
            try:
                await dispatch_slash(text, state, console, theme)
            except SystemExit:
                break

            # Check if agent switch was requested
            switch_target = getattr(state, "_switch_to", None)
            if switch_target:
                delattr(state, "_switch_to")
                try:
                    switch_profile = mgr.get(switch_target)
                    if switch_profile is None:
                        raise ValueError(f"Agent '{switch_target}' not found")
                    top = {k: v for k, v in agent_cfg.items() if k not in ("agents", "default_agent", "cli")}
                    new_cfg = switch_profile.resolve(top)
                    agent = _create_agent(new_cfg)
                    state.agent_cfg = new_cfg
                    state.current_agent = switch_target
                    state.model = model or new_cfg.get("default_model", "unknown")
                    state.session_id = uuid.uuid4().hex
                    state.input_tokens = 0
                    state.output_tokens = 0
                    console.print(
                        f"  [{theme.dot_info}]●[/] Now using: {switch_target} ({state.model})",
                        highlight=False,
                    )
                except ValueError as exc:
                    console.print(f"  [{theme.dot_error}]●[/] Switch failed: {exc}")
            console.print()  # Spacing after command output (match AI response)
        else:
            console.print()  # Blank line before AI response
            await _send_to_agent(text, agent, state, console, theme)
            console.print()  # Extra spacing after AI turn (2 lines total with footer)


async def _send_to_agent(
    text: str,
    agent: Any,
    state: SessionState,
    console: Console,
    theme: Theme,
) -> None:
    """Send user message to agent via stream() and render events."""
    from octop_harness import ChatRequest

    request = ChatRequest(
        messages=text,
        thread_id=state.session_id,
        model=state.thread_model_override or state.model,
        source="cli",
    )

    handler = StreamEventHandler(console, theme, state)
    cancel_event = asyncio.Event()
    state.bind_stop(cancel_event.set)

    async def _guarded_stream() -> AsyncGenerator[Any, None]:
        async for chunk in agent.stream(request):
            if cancel_event.is_set():
                break
            yield chunk

    try:
        await handler.handle_stream(_guarded_stream())
        if cancel_event.is_set():
            console.print(f"  [{theme.dot_error}]●[/] Generation stopped.", highlight=False)
    except asyncio.CancelledError:
        console.print(f"  [{theme.dot_error}]●[/] Generation stopped.")
    except DEFENSIVE_OP_ERRORS as e:
        console.print(f"  [{theme.dot_error}]●[/] Error: {e}")


def print_welcome(
    console: Console,
    theme: Theme,
    state: SessionState,
    *,
    project_dir: str = "",
    config_found: bool = False,
) -> None:
    """Print the startup banner and project info."""
    from octop_harness import __version__

    # ASCII banner
    banner = (
        f"  [{theme.dot_ai}]╦ ╦╔═╗╦═╗╔╗╔╔═╗╔═╗╔═╗[/]\n"
        f"  [{theme.dot_ai}]╠═╣╠═╣╠╦╝║║║║╣ ╚═╗╚═╗[/]\n"
        f"  [{theme.dot_ai}]╩ ╩╩ ╩╩╚═╝╚╝╚═╝╚═╝╚═╝[/] [dim]v{__version__}[/]"
    )
    console.print(banner)
    console.print()

    config_status = "✓" if config_found else "✗ not found"
    console.print(f"  [dim]Model:   {state.model}[/]", highlight=False)
    console.print(f"  [dim]Session: {state.session_id[:8]}[/]", highlight=False)
    console.print(f"  [dim]Project: {project_dir}[/]", highlight=False)
    console.print(f"  [dim]Config:  .octop-harness/config.json {config_status}[/]", highlight=False)
    console.print()
    console.print(f"  [{theme.separator_style}]Type /help for commands, Ctrl+C to stop/quit[/]")
    console.print()


def _create_agent(agent_cfg: dict[str, Any]) -> Any:
    """Create a HarnessAgent from config dict."""
    from octop_harness import HarnessAgent, HarnessAgentConfig

    config = HarnessAgentConfig.from_dict(agent_cfg)
    return HarnessAgent(config)
