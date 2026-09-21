"""The CLI tip written into ``credential.txt`` must name options the CLI accepts."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from octop.cli.registry import COMMANDS

_ENTRYPOINT = Path(__file__).resolve().parents[2] / "docker" / "docker-entrypoint.sh"


def _passwd_tip_flags() -> list[str]:
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "octop user passwd" in line]
    assert lines, "docker-entrypoint.sh no longer documents `octop user passwd`"
    return [token for line in lines for token in line.split() if token.startswith("--")]


def test_credential_passwd_tip_only_uses_real_options() -> None:
    module_path, attr, _help = COMMANDS["user"]
    group = getattr(import_module(module_path, "octop.cli"), attr)
    options = {
        opt
        for param in group.commands["passwd"].params
        for opt in param.opts
        if opt.startswith("--")
    }
    unknown = [flag for flag in _passwd_tip_flags() if flag not in options]
    assert not unknown, (
        f"`octop user passwd` accepts {sorted(options)}, but the credential tip "
        f"passes {unknown} — `username` is a positional argument."
    )
