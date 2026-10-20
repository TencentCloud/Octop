"""The `octop-harness skill` command group — skill management."""

from __future__ import annotations

import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _skills_dir() -> Path:
    """Get the project-level skills directory."""
    return Path.cwd() / ".octop-harness" / "skills"


@click.group()
def skill() -> None:
    """Manage agent skills (plugins)."""


@skill.command("list")
def skill_list() -> None:
    """List installed skills."""
    skills_path = _skills_dir()
    if not skills_path.exists():
        console.print("[dim]No skills installed.[/]")
        return

    table = Table(title="Installed Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Path")

    for item in sorted(skills_path.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            table.add_row(item.name, str(item))

    if table.row_count == 0:
        console.print("[dim]No skills installed.[/]")
    else:
        console.print(table)


@skill.command("install")
@click.argument("source")
def skill_install(source: str) -> None:
    """Install a skill from a local path."""
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        console.print(f"[red]Error:[/] {source} is not a directory")
        raise SystemExit(1)

    skills_path = _skills_dir()
    skills_path.mkdir(parents=True, exist_ok=True)

    target = skills_path / source_path.name
    if target.exists():
        console.print(f"[yellow]Warning:[/] Skill '{source_path.name}' already exists. Overwriting.")
        shutil.rmtree(target)

    shutil.copytree(source_path, target)
    console.print(f"[green]Installed skill:[/] {source_path.name}")


@skill.command("remove")
@click.argument("name")
def skill_remove(name: str) -> None:
    """Remove an installed skill by name."""
    target = _skills_dir() / name
    if not target.exists():
        console.print(f"[red]Error:[/] Skill '{name}' not found")
        raise SystemExit(1)

    shutil.rmtree(target)
    console.print(f"[green]Removed skill:[/] {name}")
