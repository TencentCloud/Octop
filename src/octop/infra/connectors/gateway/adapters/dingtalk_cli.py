"""DingTalk Workspace CLI gateway — one tool passing argv to ``dws``."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
from typing import Any

from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.cli_runner import resolve_binary, run_cli
from octop.infra.utils.paths import PathLayout

_KIND = "dingtalk-cli"
_TIMEOUT_S = 60.0
_MAX_OUTPUT = 32_000
# Interactive / self-modifying subcommands: they hang headless or touch the host.
_DENIED = frozenset({"auth", "upgrade", "skill", "connect", "completion"})
_STANDALONE_FLAGS = frozenset({"--help", "-h", "--version"})

TOOLS: list[dict[str, Any]] = [
    {
        "name": "dws",
        "description": (
            "Run a DingTalk Workspace CLI (dws) command via Octop Connectors. "
            "args is the command line after `dws`, e.g. "
            "'contact user search --query Alice -f json'; quote values with spaces. "
            "Use '--help' or '<product> --help' to discover commands. "
            "On auth errors, tell the user to authorize the DingTalk connector in Octop — "
            "never run shell/CLI commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                # String, not array: harness mcp_args_model only maps scalar JSON types.
                "args": {"type": "string", "description": "Arguments after `dws`"},
            },
            "required": ["args"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name != "dws":
        raise ValueError(f"unknown DingTalk CLI tool: {name}")
    argv = _parse_argv(args.get("args"))
    # Product must come first so leading global flags can't smuggle a denied subcommand.
    if argv[0].startswith("-") and argv[0] not in _STANDALONE_FLAGS:
        raise ValueError("args must start with a dws product, e.g. 'chat +chat-list'")
    if argv[0] in _DENIED:
        raise ValueError(
            f"dws {argv[0]!r} is not available through Octop. 禁止建议或执行任何终端命令。"
        )
    # Empty stdin: a confirmation prompt fails fast instead of waiting for the timeout.
    out = run_cli(
        [resolve_binary("dws"), *argv],
        env=prepare_env(creds),
        timeout_s=_TIMEOUT_S,
        stdin_text="",
    )
    if len(out) > _MAX_OUTPUT:
        # Keep chat-history dumps out of the model context; dws can page and filter.
        return (
            out[:_MAX_OUTPUT]
            + f"\n…[truncated {len(out) - _MAX_OUTPUT} chars; narrow with --limit, --jq or --fields]"
        )
    return out


def _parse_argv(raw: Any) -> list[str]:
    if isinstance(raw, str) and raw.strip().startswith("["):
        with contextlib.suppress(json.JSONDecodeError):
            raw = json.loads(raw)
    if isinstance(raw, str):
        try:
            raw = shlex.split(raw)
        except ValueError as exc:
            raise ValueError(f"args is not a valid command line: {exc}") from exc
    if not isinstance(raw, list) or not raw or not all(isinstance(a, str) for a in raw):
        raise ValueError("args must be the non-empty command line after `dws`")
    return raw


def probe_credentials(creds: dict[str, Any]) -> None:
    # Runs before the instance is saved; user login is authorized afterwards in Connectors.
    run_cli([resolve_binary("dws"), "version"], env=prepare_env(creds), timeout_s=_TIMEOUT_S)


def prepare_env(creds: dict[str, Any]) -> dict[str, str]:
    client_id = str(creds.get("client_id") or "").strip()
    client_secret = str(creds.get("client_secret") or "").strip()
    config_dir = PathLayout.from_env().ensure_connector_cli_instance_dir(
        _KIND, resolve_cli_config_key(creds)
    )
    env = os.environ.copy()
    env.update(DWS_CONFIG_DIR=str(config_dir), DWS_DISABLE_KEYCHAIN="1")
    # Without a custom app pair, dws logs in through DingTalk's official app;
    # never inherit a host-wide pair into another user's instance.
    env.pop("DWS_CLIENT_ID", None)
    env.pop("DWS_CLIENT_SECRET", None)
    if client_id and client_secret:
        env.update(DWS_CLIENT_ID=client_id, DWS_CLIENT_SECRET=client_secret)
    return env
