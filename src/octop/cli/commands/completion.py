"""octop completion: emit / install shell completion script."""

from __future__ import annotations

import os
from pathlib import Path

import click

_EVAL_TEMPLATE = {
    "bash": 'eval "$(_OCTOP_COMPLETE=bash_source octop)"\n',
    "zsh": 'autoload -U compinit && compinit\neval "$(_OCTOP_COMPLETE=zsh_source octop)"\n',
}

_DEFAULT_RC = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
}


def _detect_shell() -> str:
    sh = os.environ.get("SHELL", "")
    if sh.endswith("zsh"):
        return "zsh"
    return "bash"


@click.group("completion")
def completion() -> None:
    """Shell completion utilities."""


@completion.command("show")
@click.option("--shell", type=click.Choice(["bash", "zsh"]), default=None)
def show(shell: str | None) -> None:
    """Print a completion script for the chosen shell to stdout."""
    sh = shell or _detect_shell()
    click.echo(_EVAL_TEMPLATE[sh], nl=False)


@completion.command("install")
@click.option("--shell", type=click.Choice(["bash", "zsh"]), default=None)
@click.option("--rc-file", "rc_file", default=None, help="Custom rc file path.")
def install(shell: str | None, rc_file: str | None) -> None:
    """Idempotently append the completion eval line to the user's rc file."""
    sh = shell or _detect_shell()
    rc_path = Path(rc_file).expanduser() if rc_file else Path(_DEFAULT_RC[sh]).expanduser()
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    snippet = _EVAL_TEMPLATE[sh]

    if rc_path.exists() and b"_OCTOP_COMPLETE" in rc_path.read_bytes():
        click.echo(f"already installed in {rc_path}")
        return
    with rc_path.open("a", encoding="utf-8") as f:
        f.write("\n# octop shell completion\n")
        f.write(snippet)
    click.echo(f"installed to {rc_path} — restart your shell to activate")
