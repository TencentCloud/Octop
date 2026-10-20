"""The `octop-harness chat` command — launches the REPL."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click

from octop_harness.cli.config.loader import load_config
from octop_harness.cli.config.paths import CliPaths


@click.command()
@click.option("-p", "--prompt", type=str, default=None, help="One-shot prompt (non-interactive).")
@click.option("--model", type=str, default=None, help="Model override (provider/model_id).")
@click.option("--session", "session_id", type=str, default=None, help="Resume a session by ID.")
@click.option("--agent", "agent_name", type=str, default=None, help="Agent profile to use.")
def chat(
    prompt: str | None,
    model: str | None,
    session_id: str | None,
    agent_name: str | None,
) -> None:
    """Chat with the agent in an interactive REPL."""
    agent_cfg, cli_cfg = load_config(project_dir=Path.cwd())

    if agent_cfg is None:
        if prompt is not None:
            click.echo(
                "Error: No provider configured.\n"
                "Run `octop-harness chat` (interactive) to set up, "
                "or create ~/.octop-harness/config.json",
                err=True,
            )
            raise SystemExit(1)

        # Interactive mode: launch setup wizard
        from octop_harness.cli.providers.setup_wizard import run_setup_wizard

        paths = CliPaths(project_dir=Path.cwd())
        result = run_setup_wizard(config_path=paths.global_config_file)
        if result is None:
            raise SystemExit(1)
        # Reload config after wizard writes it
        agent_cfg, cli_cfg = load_config(project_dir=Path.cwd())
        if agent_cfg is None:
            click.echo("Error: Configuration failed.", err=True)
            raise SystemExit(1)

    if prompt is not None:
        _run_one_shot(agent_cfg, cli_cfg.to_dict(), prompt, model)
    else:
        _run_repl(agent_cfg, cli_cfg.to_dict(), model, session_id, agent_name)


def _run_repl(
    agent_cfg: dict[str, Any],
    cli_cfg: dict[str, Any],
    model: str | None,
    session_id: str | None,
    agent_name: str | None = None,
) -> None:
    """Launch the interactive REPL."""
    from octop_harness.cli.repl import run

    asyncio.run(run(agent_cfg, cli_cfg, model=model, session_id=session_id, agent_name=agent_name))


def _run_one_shot(
    agent_cfg: dict[str, Any],
    cli_cfg: dict[str, Any],
    prompt: str,
    model: str | None,
) -> None:
    """Execute a single prompt and print the result (no REPL)."""
    from octop_harness import ChatRequest, HarnessAgent, HarnessAgentConfig

    config = HarnessAgentConfig.from_dict(agent_cfg)
    agent = HarnessAgent(config)
    request = ChatRequest(messages=prompt, model=model, source="cli")

    async def _invoke() -> None:
        result = await agent.call(request)
        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            content = last.content if hasattr(last, "content") else str(last)
            if content:
                click.echo(content)

    asyncio.run(_invoke())
