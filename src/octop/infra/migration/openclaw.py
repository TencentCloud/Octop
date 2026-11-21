"""Read an OpenClaw home (``~/.openclaw``) into a :class:`MigrationPlan`.

Covers ``openclaw.json`` (JSON5, ``$include``, ``${VAR}`` and env SecretRefs),
the state ``.env``, the default agent workspace, workspace and managed skills,
``mcp.servers`` and the chat channels Octop also has.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from octop.infra.migration import relaxed_json
from octop.infra.migration.common import (
    KNOWN_PROVIDERS,
    add_mcp_server,
    add_skills,
    as_dict,
    count_cron_jobs,
    discover_skills,
    known_provider,
)
from octop.infra.migration.plan import ChannelImport, FileImport, MigrationPlan, ProviderImport
from octop.infra.utils.env_file import load_env_file

SOURCE = "openclaw"

# Current name first, then the names the project used before its renames.
_STATE_DIRS = (".openclaw", ".clawdbot", ".moltbot", ".moldbot")
_CONFIG_NAMES = ("openclaw.json", "clawdbot.json", "moltbot.json", "moldbot.json")
_WORKSPACE_FILES = (
    "AGENTS.md",
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "MEMORY.md",
    "TOOLS.md",
    "HEARTBEAT.md",
)
_API_KINDS = {
    "openai-completions": "openai",
    "openai-responses": "openai",
    "ollama": "openai",
    "anthropic-messages": "anthropic",
}
# OpenClaw channel -> (Octop kind, {OpenClaw field: Octop field}).
_CHANNELS: dict[str, tuple[str, dict[str, str]]] = {
    "telegram": ("telegram", {"botToken": "bot_token"}),
    "discord": ("discord", {"token": "bot_token"}),
    "feishu": ("feishu", {"appId": "app_id", "appSecret": "app_secret"}),
    "qqbot": ("qq", {"appId": "app_id", "clientSecret": "client_secret"}),
    "wecom": ("wecom", {"botId": "bot_id", "secret": "secret"}),
    "dingtalk": ("dingtalk", {"clientId": "client_id", "clientSecret": "client_secret"}),
}
_ENV_REF = re.compile(r"(\$?)\$\{([A-Z_][A-Z0-9_]*)\}")
_MAX_INCLUDE_DEPTH = 10


def find_openclaw_home(
    env: Mapping[str, str] | None = None, *, user_home: Path | None = None
) -> Path | None:
    """The OpenClaw state directory, or None when there is no install."""
    env = os.environ if env is None else env
    explicit = env.get("OPENCLAW_STATE_DIR")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_dir() else None
    base = Path(env.get("OPENCLAW_HOME") or user_home or Path.home()).expanduser()
    return next((base / name for name in _STATE_DIRS if (base / name).is_dir()), None)


def read_openclaw(home: Path, *, env: Mapping[str, str] | None = None) -> MigrationPlan:
    process_env = os.environ if env is None else env
    plan = MigrationPlan(source=SOURCE, home=home)
    config = _load_config(home, process_env, plan)
    values = _source_env(home, config, process_env)

    def resolve(value: Any) -> str | None:
        return _resolve(value, values)

    def substitute(text: str) -> str:
        return _substitute(text, values)[0]

    _read_models(plan, home, config, values, resolve)
    workspace = _workspace_dir(home, config, process_env)
    _read_workspace(plan, workspace)
    add_skills(plan, discover_skills(workspace / "skills"))
    add_skills(plan, discover_skills(home / "skills"))
    for name, raw in as_dict(as_dict(config.get("mcp")).get("servers")).items():
        # OpenClaw's remote default is SSE, which Octop's custom MCP cannot speak.
        add_mcp_server(plan, name, raw, resolve=substitute, default_remote_transport="sse")
    _read_channels(plan, config, resolve)

    agents = as_dict(config.get("agents"))
    entries = agents.get("entries")
    agent_count = len(entries) if isinstance(entries, dict) else len(agents.get("list") or [])
    if agent_count > 1:
        plan.note("extra_agents", count=agent_count - 1)
    cron_jobs = count_cron_jobs(home / "cron" / "jobs.json")
    if cron_jobs:
        plan.note("cron_not_migrated", count=cron_jobs)
    return plan


def _load_config(home: Path, env: Mapping[str, str], plan: MigrationPlan) -> dict[str, Any]:
    explicit = env.get("OPENCLAW_CONFIG_PATH")
    candidates = [Path(explicit).expanduser()] if explicit else [home / n for n in _CONFIG_NAMES]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        plan.note("config_missing", path=str(candidates[0]))
        return {}
    try:
        return as_dict(_load_file(path, plan, depth=0))
    except (OSError, ValueError) as exc:
        plan.note("config_unreadable", path=str(path), error=str(exc))
        return {}


def _load_file(path: Path, plan: MigrationPlan, *, depth: int) -> Any:
    data = relaxed_json.loads(path.read_text(encoding="utf-8-sig"))
    return _expand_includes(data, path.parent, plan, depth)


def _expand_includes(node: Any, base: Path, plan: MigrationPlan, depth: int) -> Any:
    """Apply ``$include``: included files merge in order, sibling keys win."""
    if isinstance(node, list):
        return [_expand_includes(item, base, plan, depth) for item in node]
    if not isinstance(node, dict):
        return node
    merged: dict[str, Any] = {}
    include = node.get("$include")
    paths = [include] if isinstance(include, str) else include if isinstance(include, list) else []
    for rel in paths:
        target = (base / str(rel)).expanduser()
        if depth >= _MAX_INCLUDE_DEPTH or not target.is_file():
            plan.note("include_missing", path=str(target))
            continue
        try:
            included = _load_file(target, plan, depth=depth + 1)
        except (OSError, ValueError) as exc:
            plan.note("config_unreadable", path=str(target), error=str(exc))
            continue
        if isinstance(included, dict):
            merged = _deep_merge(merged, included)
    siblings = {
        key: _expand_includes(value, base, plan, depth)
        for key, value in node.items()
        if key != "$include"
    }
    return _deep_merge(merged, siblings)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _source_env(home: Path, config: dict[str, Any], env: Mapping[str, str]) -> dict[str, str]:
    """Variables OpenClaw would see: config ``env`` block, state ``.env``, process."""
    values: dict[str, str] = {}
    block = as_dict(config.get("env"))
    for source in (block, as_dict(block.get("vars"))):
        values.update({k: v for k, v in source.items() if isinstance(v, str)})
    if (home / ".env").is_file():
        values.update(load_env_file(home / ".env"))
    values.update(env)
    return values


def _substitute(text: str, values: Mapping[str, str]) -> tuple[str, bool]:
    """Expand ``${VAR}`` (``$${VAR}`` is a literal). Second item: everything resolved."""
    complete = True

    def replace(match: re.Match[str]) -> str:
        nonlocal complete
        if match.group(1):
            return "${" + match.group(2) + "}"
        value = values.get(match.group(2))
        if value is None:
            complete = False
            return match.group(0)
        return value

    return _ENV_REF.sub(replace, text), complete


def _resolve(value: Any, values: Mapping[str, str]) -> str | None:
    """A credential as plain text, or None when it points somewhere we cannot read."""
    if isinstance(value, dict):  # SecretRef
        if value.get("source") == "env":
            return values.get(str(value.get("id") or "")) or None
        return None
    if not isinstance(value, str) or not value:
        return None
    text, complete = _substitute(value, values)
    return text if complete else None


def _read_models(
    plan: MigrationPlan,
    home: Path,
    config: dict[str, Any],
    values: Mapping[str, str],
    resolve: Any,
) -> None:
    providers = as_dict(as_dict(config.get("models")).get("providers"))
    for provider_id, raw in providers.items():
        if not isinstance(raw, dict):
            continue
        api = str(raw.get("api") or "openai-completions")
        base_url = str(raw.get("baseUrl") or "")
        if api not in _API_KINDS or not base_url:
            plan.note("provider_unsupported", name=provider_id, api=api)
            continue
        models = tuple(
            str(m["id"]) for m in raw.get("models") or [] if isinstance(m, dict) and m.get("id")
        )
        plan.providers.append(
            ProviderImport(
                name=provider_id,
                kind=_API_KINDS[api],
                base_url=base_url,
                api_key=resolve(raw.get("apiKey")),
                models=models,
            )
        )

    model = as_dict(config.get("agents")).get("defaults")
    model = as_dict(model).get("model")
    primary = model.get("primary") if isinstance(model, dict) else model
    if not isinstance(primary, str) or "/" not in primary:
        return
    provider_id, model_id = primary.split("/", 1)
    if provider_id not in providers:
        if provider_id not in KNOWN_PROVIDERS:
            plan.note("provider_unsupported", name=provider_id, api="built-in")
            return
        keys = {**_auth_profile_keys(home), **values}
        found = known_provider(provider_id, keys, model_id)
        if found is None:
            plan.note("provider_key_missing", name=provider_id)
            return
        plan.providers.append(found)
    plan.default_model = (provider_id, model_id)


def _auth_profile_keys(home: Path) -> dict[str, str]:
    """API keys from legacy ``auth-profiles.json`` files, as their usual env names."""
    out: dict[str, str] = {}
    for path in sorted(home.glob("agents/*/agent/auth-profiles.json")):
        try:
            profiles = as_dict(json.loads(path.read_text(encoding="utf-8"))).get("profiles")
        except (OSError, ValueError):
            continue
        for profile in as_dict(profiles).values():
            if not isinstance(profile, dict) or profile.get("type") != "api_key":
                continue
            known = KNOWN_PROVIDERS.get(str(profile.get("provider")))
            if known and isinstance(profile.get("key"), str) and profile["key"]:
                out.setdefault(known[2][0], profile["key"])
    return out


def _workspace_dir(home: Path, config: dict[str, Any], env: Mapping[str, str]) -> Path:
    defaults = as_dict(as_dict(config.get("agents")).get("defaults"))
    configured = defaults.get("workspace") or env.get("OPENCLAW_WORKSPACE_DIR")
    return Path(str(configured)).expanduser() if configured else home / "workspace"


def _read_workspace(plan: MigrationPlan, workspace: Path) -> None:
    for name in _WORKSPACE_FILES:
        path = workspace / name
        if not path.is_file() and name == "MEMORY.md":
            path = workspace / "memory.md"  # pre-2026 lowercase name
        if path.is_file():
            plan.files.append(FileImport(dest=name, source=path))
    daily = workspace / "memory"
    if daily.is_dir():
        for path in sorted(daily.glob("*.md")):
            plan.files.append(FileImport(dest=f"memory/{path.name}", source=path))


def _read_channels(plan: MigrationPlan, config: dict[str, Any], resolve: Any) -> None:
    for channel, raw in as_dict(config.get("channels")).items():
        if not isinstance(raw, dict):
            continue
        if channel not in _CHANNELS:
            plan.note("channel_unsupported", name=channel)
            continue
        kind, fields = _CHANNELS[channel]
        # Top-level credentials are the default account; named accounts inherit from it.
        accounts: dict[str, dict[str, Any]] = {"": raw}
        for account_id, account in as_dict(raw.get("accounts")).items():
            if isinstance(account, dict):
                accounts[str(account_id)] = {**raw, **account}
        seen: list[dict[str, Any]] = []
        for account_id, account in accounts.items():
            credentials = {dest: resolve(account.get(src)) for src, dest in fields.items()}
            if not all(credentials.values()):
                if account_id:
                    plan.note("channel_credentials_missing", name=f"{channel}:{account_id}")
                continue
            if credentials in seen:  # an account that only inherits the default one
                continue
            seen.append(credentials)
            name = f"{kind}-{account_id}" if account_id else kind
            plan.channels.append(ChannelImport(kind=kind, name=name, config=credentials))
