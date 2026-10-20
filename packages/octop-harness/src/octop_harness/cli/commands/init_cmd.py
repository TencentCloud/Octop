"""The `octop-harness init` command — workspace initialization.

By default ``octop-harness init`` lays down a **global** Harness home
under ``~/.octop-harness/``:

    ~/.octop-harness/
    ├── config.json          # provider config + agent workspace_dir
    ├── credentials.json     # API keys (touched by ``config provider add``)
    ├── sessions/            # CLI session metadata
    └── workspace/           # agent's workspace
        ├── _builtin_skills/   # bundled skills (synced from the package)
        ├── AGENTS.md          # seeded markdown templates
        └── …

The agent's workspace_dir defaults to that ``workspace/`` subdir. The
backend is rooted at the workspace by default; pass an explicit backend
spec in ``config.json`` to override (e.g. ``{"type": "local_shell",
"root_dir": "/"}`` for full host access).

Pass ``--scope project`` to install into ``./.octop-harness/`` instead;
the per-project layout mirrors the global one.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console

from octop_harness.cli.config.paths import CliPaths

console = Console()


@click.command()
@click.option(
    "--path",
    type=click.Path(exists=False),
    default=None,
    help="Override the install location (defaults to ~/.octop-harness or <cwd>/.octop-harness depending on --scope).",
)
@click.option(
    "--scope",
    type=click.Choice(["global", "project"]),
    default="global",
    show_default=True,
    help="Install to ~/.octop-harness (global, default) or <cwd>/.octop-harness (project).",
)
@click.option(
    "--language",
    type=click.Choice(["en", "zh"]),
    default="en",
    show_default=True,
    help="Language for the seeded markdown templates.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite existing templates and force a built-in skills resync.",
)
def init(path: str | None, scope: str, language: str, overwrite: bool) -> None:
    """Initialize a Harness Agent workspace."""
    # Imported lazily so ``--help`` stays cheap.
    from octop_harness import init_workspace
    from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

    paths = CliPaths(project_dir=Path.cwd())

    if path is not None:
        harness_dir = Path(path).expanduser().resolve()
    elif scope == "project":
        harness_dir = paths.project_dir.resolve()
    else:
        harness_dir = paths.global_dir.resolve()

    workspace_dir = harness_dir / "workspace"
    sessions_dir = harness_dir / "sessions"
    config_file = harness_dir / "config.json"

    fresh_install = not config_file.exists()

    # Layout dirs (idempotent).
    harness_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(exist_ok=True)

    # Seed templates + built-in skills via the library helper.
    # ``init_workspace`` operates a backend rooted at ``workspace_dir``
    # itself; templates and skills land directly inside.
    try:
        result = init_workspace(
            workspace_dir,
            language=language,
            overwrite=overwrite,
        )
    except DEFENSIVE_OP_ERRORS as exc:
        console.print(f"[red]Failed to seed workspace:[/] {exc}")
        raise click.Abort() from exc

    # Default config.json — only written when missing, never clobbered.
    # ``workspace_dir`` is absolute; the agent's backend will be rooted
    # at it by default. Users that need full host access can swap the
    # backend spec to ``{"type": "local_shell", "root_dir": "/"}``.
    if not config_file.exists():
        default_config = {
            "workspace_dir": str(workspace_dir),
            "language": language,
            "providers": {},
            # Memory: enabled by default so the agent captures / recalls out of the box.
            # ``memory.sqlite`` and daily JSONL logs land under ``workspace_dir``.
            # "memory_enabled": True,
            # "memory_backend": "sqlite",
            # "memory_jsonl_enabled": True,
            # "memory_aux_model_enabled": True,
            # "memory_recall_inject_enabled": True,
            # "memory_capture_enabled": True,
            # "memory_extract_on_session_end": True,
            # Idle-watchdog cadence for L0 -> L2 promotion. 30s is a friendly
            # default for local / REPL usage; production hosts should raise it.
            # "memory_extract_idle_seconds": 30.0,
            "cli": {
                "theme": "dark",
                "stream": True,
            },
        }
        config_file.write_text(json.dumps(default_config, indent=2) + "\n", encoding="utf-8")

    # ----- Reporting -----
    console.print(f"[green]Initialized[/] Harness home at {harness_dir}")
    if fresh_install:
        console.print(f"  Created: {config_file}")
        console.print(f"  Created: {sessions_dir}/")
    if result.templates_created:
        console.print(f"  Templates created: {len(result.templates_created)}")
    if result.templates_overwritten:
        console.print(f"  Templates overwritten: {len(result.templates_overwritten)}")
    if result.templates_skipped:
        console.print(f"  Templates left untouched: {len(result.templates_skipped)}")
    if result.skills_synced:
        console.print(f"  Built-in skills synced -> {workspace_dir}/_builtin_skills/")
    else:
        console.print("  Built-in skills already up-to-date")

    if fresh_install:
        console.print(f"\n[dim]Workspace is at {workspace_dir} — edit {config_file} to customize.[/]")
        console.print("Run [bold]octop-harness config provider add[/] to configure a model provider.")
