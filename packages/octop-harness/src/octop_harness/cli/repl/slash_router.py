"""REPL slash routing — agent runtime commands + CLI host commands."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop_harness.slash import (
    RuntimeSlashCtx,
    build_runtime_dispatcher,
    parse_slash,
)

if TYPE_CHECKING:
    from rich.console import Console

    from octop_harness.cli.repl.state import SessionState
    from octop_harness.cli.ui.theme import Theme

_RUNTIME = build_runtime_dispatcher()
_RUNTIME_COMMANDS = frozenset({"stop", "cancel", "model", "models", "skills"})


def _cmd_model_interactive(state: SessionState, console: Console, theme: Theme) -> None:
    """Select a model interactively from the configured providers."""
    models: list[str] = []
    for provider_name, provider_cfg in state.agent_cfg.get("providers", {}).items():
        if not isinstance(provider_cfg, dict):
            continue
        for m in provider_cfg.get("models", []):
            model_id = m["id"] if isinstance(m, dict) else getattr(m, "id", str(m))
            models.append(f"{provider_name}/{model_id}")

    if not models:
        console.print(f"  [{theme.dot_info}]●[/] No models configured.", highlight=False)
        return

    if len(models) == 1:
        console.print(f"  [{theme.dot_info}]●[/] Current model: {models[0]}", highlight=False)
        return

    console.print()
    for i, model in enumerate(models, 1):
        marker = "  ← current" if model == state.model else ""
        console.print(f"    [{theme.dot_info}]{i:>3}[/]  {model}{marker}", highlight=False)
    console.print()

    from rich.prompt import Prompt

    choice = Prompt.ask(f"  Select (1-{len(models)}) or Enter to cancel", default="")

    if not choice.strip():
        console.print(f"  [{theme.dot_info}]●[/] Cancelled.", highlight=False)
        return

    try:
        idx = int(choice.strip()) - 1
        if not (0 <= idx < len(models)):
            raise ValueError
    except ValueError:
        console.print(f"  [{theme.dot_error}]●[/] Invalid selection.", highlight=False)
        return

    state.model = models[idx]
    state.thread_model_override = models[idx]
    console.print(f"  [{theme.dot_info}]●[/] Switched to: {state.model}", highlight=False)


class _ConsoleSlashSink:
    def __init__(self, console: Console, theme: Theme) -> None:
        self._console = console
        self._theme = theme

    async def text(self, line: str) -> None:
        self._console.print(f"  [{self._theme.dot_info}]●[/] {line}", highlight=False)

    async def complete(self) -> None:
        return None


def _skills_dir() -> Path:
    return Path.cwd() / ".octop-harness" / "skills"


async def _list_cli_skills() -> list[dict[str, Any]]:
    root = _skills_dir()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for item in sorted(root.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            rows.append({"name": item.name, "description": "", "enabled": True})
    return rows


def _build_cli_runtime_ctx(state: SessionState) -> RuntimeSlashCtx:
    default_model = str(state.agent_cfg.get("default_model") or state.model)

    def _get_model(_agent_id: str, _thread_id: str) -> str | None:
        return state.thread_model_override

    def _set_model(_agent_id: str, _thread_id: str, model: str) -> None:
        state.thread_model_override = model
        state.model = model

    def _clear_model(_agent_id: str, _thread_id: str) -> None:
        state.thread_model_override = None
        state.model = default_model

    def _cancel(_agent_id: str, _thread_id: str) -> None:
        state.request_stop()

    return RuntimeSlashCtx(
        agent_id=state.current_agent,
        thread_id=state.session_id,
        locale="zh",
        default_model=default_model,
        cancel_stream=_cancel,
        get_thread_model=_get_model,
        set_thread_model=_set_model,
        clear_thread_model=_clear_model,
        list_skills=_list_cli_skills,
    )


async def dispatch_slash(
    text: str,
    state: SessionState,
    console: Console,
    theme: Theme,
) -> None:
    """Route a slash line to runtime handlers or CLI host commands."""
    from octop_harness.cli.repl.commands import _ALIASES, COMMANDS

    cmd = parse_slash(text)
    if cmd is None:
        return

    if cmd.name in _RUNTIME_COMMANDS:
        if cmd.name in ("model", "models") and not cmd.args.strip():
            _cmd_model_interactive(state, console, theme)
            return
        sink = _ConsoleSlashSink(console, theme)
        await _RUNTIME.handle(cmd, _build_cli_runtime_ctx(state), sink)
        return

    canonical = _ALIASES.get(cmd.name, cmd.name)
    handler = COMMANDS.get(canonical)
    if handler is None:
        console.print(
            f"  [{theme.dot_error}]●[/] Unknown command: /{cmd.name}. Type /help",
            highlight=False,
        )
        return
    handler(state, console, theme, cmd.args)


def runtime_command_names() -> frozenset[str]:
    return _RUNTIME_COMMANDS
