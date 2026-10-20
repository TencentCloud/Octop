"""``octop-memory openclaw`` — manage the OpenClaw native plugin slot.

These operator-facing subcommands wire up octopmemory without requiring
manual edits to ``openclaw.json``:

- ``openclaw setup`` — write ``plugins.slots.memory: octopmemory``, the
  default ``plugins.entries.octopmemory.config`` block, and the
  ``hooks.allowConversationAccess`` opt-in (required by OpenClaw >=2026.4.29
  for agent_end capture); idempotent.
- ``openclaw doctor`` — sanity check: openclaw config exists, plugin
  dir present, manifest parses, slot pointed at us, bridge importable.
- ``openclaw uninstall`` — remove our slot binding (does NOT delete
  data; namespace SQLite stays).
- ``openclaw print-config`` — emit a sample plugin config block to
  stdout (for users who'd rather copy-paste).

We stop short of installing the npm dependencies / building the TS
shell — that's outside the Python CLI's responsibility (the user runs
``npm install && npm run build`` in ``plugins/openclaw/octopmemory``
themselves, per its README).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import click

DEFAULT_OPENCLAW_HOME = Path("~/.openclaw").expanduser()
DEFAULT_OPENCLAW_CONFIG = DEFAULT_OPENCLAW_HOME / "openclaw.json"
DEFAULT_EXTENSIONS_DIR = DEFAULT_OPENCLAW_HOME / "extensions"
DEFAULT_HOST_FILES_ALLOW = ["topics/*.md", "projects/*.md"]

PLUGIN_ID = "octopmemory"
# Must match the TS plugin's fallback and setup.ts defaultNamespace() so the
# CLI, the plugin, and docs/integrations.md all resolve the same SQLite path.
DEFAULT_NAMESPACE = "openclaw__default"
NPM_PLUGIN_GLOB = "npm/projects/*/node_modules/@octop-memory/openclaw"
PROFILE_CHOICES = ("balanced", "low_latency", "proactive", "privacy", "archive", "eval")

_BALANCED_DEFAULTS: dict[str, Any] = {
    "mode": "self-hosted",
    "profile": "balanced",
    "host_files_allow": list(DEFAULT_HOST_FILES_ALLOW),
    "recall": {
        "mode": "tool_hint",
        "default_max_results": 5,
        "default_corpus": "all",
        "raw_policy": "fallback",
        "host_files_policy": "include",
        "citation_policy": "auto",
        "max_prompt_chars": 1200,
        "layer_order": ["atom", "host_file", "page", "raw"],
    },
    "capture": {
        "agent_end_hook": True,
        "host_files_watcher": True,
        "min_message_chars": 50,
        "include_roles": ["user", "assistant"],
        "include_tool_calls": False,
        "include_tool_results": False,
        "skip_memory_echo": True,
    },
    "privacy": {
        "redact_secrets": True,
        "redact_patterns": [],
        "store_raw_content": True,
        "store_tool_payloads": False,
    },
    "compaction": {
        "enabled": True,
        "soft_threshold_tokens": 4000,
        "force_flush_transcript_bytes": 2 * 1024 * 1024,
        "host_file_index_after_flush": True,
    },
}

_PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "balanced": {},
    "low_latency": {
        "recall": {
            "default_max_results": 3,
            "default_corpus": "memory",
            "raw_policy": "never",
            "host_files_policy": "off",
            "citation_policy": "off",
            "max_prompt_chars": 400,
            "layer_order": ["atom", "page"],
        },
        "capture": {"host_files_watcher": False, "min_message_chars": 100, "include_roles": ["user"]},
        "compaction": {"enabled": False},
    },
    "proactive": {"recall": {"mode": "hybrid", "citation_policy": "always"}, "capture": {"min_message_chars": 30}},
    "privacy": {
        "recall": {
            "default_corpus": "memory",
            "raw_policy": "never",
            "host_files_policy": "off",
            "citation_policy": "off",
            "layer_order": ["atom", "page"],
        },
        "capture": {"host_files_watcher": False, "min_message_chars": 120, "include_roles": ["user"]},
        "privacy": {"store_raw_content": False, "store_tool_payloads": False},
    },
    "archive": {
        "recall": {
            "default_max_results": 10,
            "raw_policy": "always",
            "citation_policy": "always",
            "max_prompt_chars": 2000,
            "layer_order": ["atom", "raw", "host_file", "page"],
        },
        "capture": {
            "min_message_chars": 0,
            "include_roles": ["user", "assistant", "tool"],
            "include_tool_calls": True,
            "include_tool_results": True,
        },
        "compaction": {"soft_threshold_tokens": 3000},
    },
    "eval": {
        "recall": {"citation_policy": "always", "layer_order": ["atom", "page", "raw", "host_file"]},
        "capture": {"min_message_chars": 0},
    },
}


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


@click.group(name="openclaw")
def openclaw_group() -> None:
    """Configure / inspect the OpenClaw native memory plugin slot."""


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def _resolve_bridge_config(bridge_python: str | None) -> dict[str, str]:
    """Bridge launch config for the plugin.

    Bridge launch config for the plugin, from an explicit interpreter or
    auto-detected from the environment running this command.

    This command necessarily runs inside an environment where octop-memory
    is importable (pipx/uv tool venv, project venv, ...), so ``sys.executable``
    is always a working bridge interpreter — unlike the bare ``python3`` we
    used to default to, which points at the system interpreter that usually
    lacks the package. The ``octopmemory-bridge`` console script sitting
    next to the interpreter is preferred (written as ``bridge.command``, the
    form the TS plugin favours); the interpreter itself is the fallback
    (``bridge.python``, spawned via ``python -m``).
    """
    if bridge_python:
        return {"python": bridge_python, "log_level": "info"}
    script = Path(sys.executable).with_name("octopmemory-bridge")
    if script.exists():
        return {"command": str(script), "log_level": "info"}
    return {"python": sys.executable, "log_level": "info"}


@openclaw_group.command(name="setup")
@click.option(
    "--openclaw-config",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_OPENCLAW_CONFIG,
    show_default=True,
    help="Path to OpenClaw's openclaw.json config file.",
)
@click.option(
    "--profile",
    type=click.Choice(PROFILE_CHOICES),
    default="balanced",
    show_default=True,
    help="Scenario preset for recall/capture/privacy defaults.",
)
@click.option(
    "--namespace",
    default=None,
    help=(
        f"Memory namespace (default: '{DEFAULT_NAMESPACE}', always written explicitly "
        "so the plugin does not derive its own). "
        "Use this to share memory across machines / agents under one identity."
    ),
)
@click.option(
    "--db-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "SQLite path. Defaults to <openclaw-home>/octopmemory/<namespace>/memory.sqlite — "
        "under the OpenClaw home because sandboxed deployments (openclaw-security/bwrap) "
        "only bind that directory into plugin subprocesses; ~/.octopmemory is invisible there."
    ),
)
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help=(
        "Workspace dir for D51-C host_files watcher. Defaults to ~/.openclaw/workspace "
        "or ~/.openclaw/workspace-<OPENCLAW_PROFILE>."
    ),
)
@click.option(
    "--host-files-allow",
    multiple=True,
    help=(
        "Additional relative Markdown glob to index under the workspace, e.g. topics/*.md. "
        "May be repeated or comma-separated."
    ),
)
@click.option(
    "--no-host-files-watcher",
    is_flag=True,
    default=False,
    help="Disable host_files watcher even though it is on by default.",
)
@click.option(
    "--bridge-python",
    default=None,
    help=(
        "Python interpreter the TS plugin should spawn for the bridge subprocess. "
        "Default: auto-detected from the environment running this command — the "
        "octopmemory-bridge console script next to this interpreter when present "
        "(written as bridge.command), else this interpreter itself (bridge.python). "
        "Only pass this to point the bridge at a different environment."
    ),
)
@click.option(
    "--recall-mode",
    type=click.Choice(["off", "tool_hint", "hybrid"]),
    default="tool_hint",
    show_default=True,
    help=(
        "Memory prompt mode: off=no memory prompt, tool_hint=tools-only hint, "
        "hybrid=hybrid auto-recall mode (currently falls back to explicit tool guidance)."
    ),
)
@click.option(
    "--no-agent-end-hook",
    is_flag=True,
    default=False,
    help="Disable D52-C agent_end auto-capture (default on).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the resulting JSON to stdout instead of writing it.",
)
def setup_cmd(
    openclaw_config: Path,
    profile: str,
    namespace: str | None,
    db_path: Path | None,
    workspace: Path | None,
    host_files_allow: tuple[str, ...],
    no_host_files_watcher: bool,
    bridge_python: str | None,
    recall_mode: str,
    no_agent_end_hook: bool,
    dry_run: bool,
) -> None:
    """Wire ``plugins.slots.memory: octopmemory`` into ``openclaw.json``.

    Existing config is preserved; only the relevant keys are
    inserted / overwritten. ``--dry-run`` is recommended on the first
    invocation so you can review the diff before persisting.
    """
    cfg = _load_or_init(openclaw_config)
    plugins = cfg.setdefault("plugins", {})
    slots = plugins.setdefault("slots", {})
    entries = plugins.setdefault("entries", {})

    slots["memory"] = PLUGIN_ID

    plugin_cfg = _profile_config(profile)
    # Always write the namespace: when omitted the TS plugin derives one from
    # its runtime plugin id (e.g. 'openclaw__octopmemory'), which diverges
    # from the documented default and from setup.ts.
    plugin_cfg["namespace"] = namespace or DEFAULT_NAMESPACE
    # Always write an explicit db_path, under the OpenClaw home. Sandboxed
    # deployments (openclaw-security/bwrap) replace $HOME with a tmpfs inside
    # plugin subprocesses and only bind a whitelist back in — ~/.openclaw is
    # on it, the old implicit default ~/.octopmemory is not, so a store
    # there is invisible to the bridge. Explicit also keeps the migration
    # tools (portable adopt/doctor) pointed at the same file.
    resolved_db = (
        db_path.expanduser()
        if db_path is not None
        else openclaw_config.parent / "octopmemory" / plugin_cfg["namespace"] / "memory.sqlite"
    )
    plugin_cfg["db_path"] = str(resolved_db)
    plugin_cfg["bridge"] = _resolve_bridge_config(bridge_python)
    plugin_cfg["recall"]["mode"] = recall_mode
    plugin_cfg["capture"]["agent_end_hook"] = not no_agent_end_hook
    patterns = _split_csv_options(host_files_allow) or list(DEFAULT_HOST_FILES_ALLOW)
    plugin_cfg["host_files_allow"] = patterns
    if no_host_files_watcher:
        plugin_cfg["capture"]["host_files_watcher"] = False
        plugin_cfg.pop("host_files_root", None)
    elif workspace is not None or plugin_cfg["capture"].get("host_files_watcher") is True:
        workspace_root = workspace or _default_openclaw_workspace()
        plugin_cfg["capture"]["host_files_watcher"] = True
        plugin_cfg["host_files_root"] = str(workspace_root.expanduser().resolve())
    else:
        plugin_cfg.pop("host_files_root", None)

    entries[PLUGIN_ID] = {
        "enabled": True,
        # OpenClaw >=2026.4.29 gates "conversation hooks" (agent_end, llm_input,
        # llm_output, ...) behind an explicit per-plugin opt-in. Without this
        # field the host never delivers agent_end, so auto-capture is silently
        # dead while everything else looks healthy.
        "hooks": {"allowConversationAccess": True},
        "config": plugin_cfg,
    }

    payload = json.dumps(cfg, indent=2, ensure_ascii=False)
    if dry_run:
        click.echo(payload)
        return

    openclaw_config.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write so a Ctrl-C in the middle doesn't truncate the user's
    # existing config.
    tmp = openclaw_config.with_suffix(openclaw_config.suffix + ".tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    tmp.replace(openclaw_config)
    click.echo(f"wrote {openclaw_config}")
    click.echo(f"  plugins.slots.memory = {PLUGIN_ID}")
    click.echo(f"  plugins.entries.{PLUGIN_ID}.hooks.allowConversationAccess = true")
    click.echo(f"  plugins.entries.{PLUGIN_ID}.config.namespace = {plugin_cfg['namespace']}")
    click.echo(f"  plugins.entries.{PLUGIN_ID}.config.db_path = {plugin_cfg['db_path']}")
    bridge_cfg = plugin_cfg["bridge"]
    bridge_key = "command" if "command" in bridge_cfg else "python"
    click.echo(f"  plugins.entries.{PLUGIN_ID}.config.bridge.{bridge_key} = {bridge_cfg[bridge_key]}")
    if plugin_cfg["capture"].get("host_files_watcher"):
        click.echo(f"  plugins.entries.{PLUGIN_ID}.config.host_files_root = {plugin_cfg['host_files_root']}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Install the plugin: openclaw plugins install @octop-memory/openclaw")
    click.echo("     (or from source: cd plugins/openclaw/octopmemory && npm install && npm run build,")
    click.echo(f"      then cp -r — not symlink — into {DEFAULT_EXTENSIONS_DIR}/{PLUGIN_ID})")
    click.echo("  2. Restart OpenClaw (openclaw gateway restart).")
    click.echo("")
    click.echo(f"Verify: octop-memory openclaw doctor --openclaw-config {openclaw_config}")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@openclaw_group.command(name="doctor")
@click.option(
    "--openclaw-config",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_OPENCLAW_CONFIG,
    show_default=True,
)
@click.option(
    "--extensions-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_EXTENSIONS_DIR,
    show_default=True,
)
def doctor_cmd(openclaw_config: Path, extensions_dir: Path) -> None:
    """Sanity-check the octopmemory plugin install.

    Each check prints OK / FAIL / WARN. Exits with code 0 if all FAIL
    checks pass; WARN-only is still considered healthy.
    """
    failed: list[str] = []

    def ok(msg: str) -> None:
        click.echo(f"  [OK]   {msg}")

    def fail(msg: str) -> None:
        click.echo(f"  [FAIL] {msg}")
        failed.append(msg)

    def warn(msg: str) -> None:
        click.echo(f"  [WARN] {msg}")

    click.echo(f"Checking {openclaw_config} ...")
    if not openclaw_config.exists():
        fail(f"openclaw config not found: {openclaw_config}")
    else:
        ok(f"openclaw config exists ({openclaw_config})")
        try:
            cfg = json.loads(openclaw_config.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            fail(f"openclaw config not parseable: {exc}")
            cfg = None
        if cfg is not None:
            slot = cfg.get("plugins", {}).get("slots", {}).get("memory")
            if slot == PLUGIN_ID:
                ok(f"plugins.slots.memory = {PLUGIN_ID}")
            elif slot is None:
                fail("plugins.slots.memory is unset (run `octop-memory openclaw setup`)")
            else:
                warn(f"plugins.slots.memory = {slot!r} (not {PLUGIN_ID!r})")
            entry = cfg.get("plugins", {}).get("entries", {}).get(PLUGIN_ID)
            if entry is None:
                warn(f"plugins.entries.{PLUGIN_ID} missing — slot points at us but no config block")
            elif entry.get("enabled") is False:
                fail(f"plugins.entries.{PLUGIN_ID}.enabled = false")
            else:
                ok(f"plugins.entries.{PLUGIN_ID}.enabled = true")
                hooks_cfg = entry.get("hooks")
                if isinstance(hooks_cfg, dict) and hooks_cfg.get("allowConversationAccess") is True:
                    ok(f"plugins.entries.{PLUGIN_ID}.hooks.allowConversationAccess = true")
                else:
                    fail(
                        f"plugins.entries.{PLUGIN_ID}.hooks.allowConversationAccess is not true — "
                        "OpenClaw >=2026.4.29 silently drops agent_end auto-capture without this "
                        "opt-in (re-run `octop-memory openclaw setup`)"
                    )

    # The plugin lives either in the manual-install extensions dir or wherever
    # `openclaw plugins install` put it (~/.openclaw/npm/projects/<hash>/...).
    npm_candidates = sorted(openclaw_config.parent.glob(NPM_PLUGIN_GLOB))
    plugin_dir = next((d for d in [extensions_dir / PLUGIN_ID, *npm_candidates] if d.exists()), None)
    click.echo(f"\nChecking plugin directory ({extensions_dir / PLUGIN_ID}) ...")
    if plugin_dir is None:
        fail(
            f"plugin directory missing: {extensions_dir / PLUGIN_ID} "
            f"(also checked {openclaw_config.parent / NPM_PLUGIN_GLOB})"
        )
    elif plugin_dir.is_symlink():
        fail("plugin directory is a symlink — OpenClaw v2026.4.11+ rejects these")
    else:
        ok(f"plugin directory exists ({plugin_dir})")
        manifest_path = plugin_dir / "openclaw.plugin.json"
        if not manifest_path.exists():
            fail(f"manifest missing: {manifest_path}")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("kind") == "memory" and manifest.get("id") == PLUGIN_ID:
                    ok(f"manifest kind=memory id={PLUGIN_ID}")
                else:
                    fail(f"manifest kind/id mismatch: {manifest.get('id')!r} / {manifest.get('kind')!r}")
            except (json.JSONDecodeError, OSError) as exc:
                fail(f"manifest not parseable: {exc}")
        if not (plugin_dir / "dist" / "index.js").exists():
            warn(f"{plugin_dir}/dist/index.js not built — run `npm install && npm run build`")
        else:
            ok("plugin TS shell is built (dist/index.js present)")

    click.echo("\nChecking Python bridge ...")
    try:
        # Doctor checks at *runtime* whether the bridge module imports
        # cleanly in the current env. A top-level import would fail
        # before this command even starts, defeating the purpose. We use
        # importlib.import_module (rather than a plain `import` statement)
        # purely for the ImportError side effect, so there's no unused
        # binding for ruff to flag.
        import importlib

        from octop_memory import __version__
        from octop_memory.adapters.bridge import PROTOCOL_VERSION

        importlib.import_module("octop_memory.adapters.bridge.server")

        ok(f"octop_memory {__version__} importable (bridge protocol {PROTOCOL_VERSION})")
    except ImportError as exc:
        fail(f"bridge server not importable: {exc}")

    # FTS5 is a compile-time SQLite feature, not a pip dependency: the
    # bridge's whole recall path is FTS5-backed, so a Python whose
    # bundled SQLite lacks it cannot run at all. Detect it explicitly
    # rather than letting capture/recall crash at runtime.
    import sqlite3

    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE _probe_fts USING fts5(x)")
        finally:
            conn.close()
        ok(f"SQLite {sqlite3.sqlite_version} with FTS5")
    except sqlite3.OperationalError:
        fail(
            f"this Python's SQLite {sqlite3.sqlite_version} has no FTS5 module "
            "→ use a python.org / Homebrew / conda interpreter, or point bridge.command/python "
            "at a venv whose sqlite3 has FTS5"
        )

    click.echo("")
    if failed:
        click.echo(f"❌ {len(failed)} check(s) failed.")
        raise click.exceptions.Exit(1)
    click.echo("✅ All required checks passed.")


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@openclaw_group.command(name="uninstall")
@click.option(
    "--openclaw-config",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_OPENCLAW_CONFIG,
    show_default=True,
)
@click.confirmation_option(prompt=f"Remove the {PLUGIN_ID} slot binding? (your stored memory data is NOT deleted.)")
def uninstall_cmd(openclaw_config: Path) -> None:
    """Remove octopmemory from ``plugins.slots.memory``.

    Does NOT delete the SQLite store or the plugin directory; that's a
    separate manual step. We deliberately leave the entries block in
    place so reactivating later (``openclaw setup``) keeps user-tuned
    options.
    """
    if not openclaw_config.exists():
        click.echo(f"nothing to remove: {openclaw_config} does not exist")
        return
    cfg = json.loads(openclaw_config.read_text(encoding="utf-8"))
    slots = cfg.get("plugins", {}).get("slots", {})
    if slots.get("memory") == PLUGIN_ID:
        del slots["memory"]
        openclaw_config.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        click.echo(f"removed plugins.slots.memory ({PLUGIN_ID}) from {openclaw_config}")
    else:
        click.echo(f"no-op: plugins.slots.memory = {slots.get('memory')!r}, not {PLUGIN_ID!r}")


# ---------------------------------------------------------------------------
# print-config
# ---------------------------------------------------------------------------


@openclaw_group.command(name="print-config")
@click.option("--profile", type=click.Choice(PROFILE_CHOICES), default="balanced", show_default=True)
@click.option("--namespace", default="openclaw__default")
def print_config_cmd(profile: str, namespace: str) -> None:
    """Print a sample ``plugins.entries.octopmemory.config`` block."""
    plugin_cfg = _profile_config(profile)
    plugin_cfg["namespace"] = namespace
    plugin_cfg["bridge"] = {"python": "python3", "log_level": "info", "spawn_timeout_ms": 5000}
    if plugin_cfg["capture"].get("host_files_watcher"):
        plugin_cfg["host_files_root"] = str(_default_openclaw_workspace().expanduser().resolve())
    sample = {
        "plugins": {
            "slots": {"memory": PLUGIN_ID},
            "entries": {
                PLUGIN_ID: {
                    "enabled": True,
                    "config": plugin_cfg,
                }
            },
        }
    }
    click.echo(json.dumps(sample, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_config(profile: str) -> dict[str, Any]:
    cfg = _deep_merge(_BALANCED_DEFAULTS, _PROFILE_OVERRIDES[profile])
    cfg["profile"] = profile
    return cfg


def _default_openclaw_workspace() -> Path:
    profile = os.environ.get("OPENCLAW_PROFILE", "").strip()
    if profile and profile != "default":
        return DEFAULT_OPENCLAW_HOME / f"workspace-{profile}"
    return DEFAULT_OPENCLAW_HOME / "workspace"


def _split_csv_options(values: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in base.items():
        out[key] = _clone_json(value)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = _clone_json(value)
    return out


def _clone_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _load_or_init(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return loaded
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"openclaw config at {path} is not valid JSON: {exc}; refusing to overwrite") from exc


__all__ = ["openclaw_group"]
