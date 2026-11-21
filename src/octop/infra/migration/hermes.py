"""Read a Hermes Agent home (``~/.hermes``) into a :class:`MigrationPlan`.

Covers ``config.yaml`` (model, ``providers`` / legacy ``custom_providers``,
``mcp_servers``), the ``.env`` secrets, ``SOUL.md``, the ``memories/`` files,
user-installed skills and the chat platforms Octop also has.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

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

SOURCE = "hermes"

_CUSTOM_PROVIDER = "hermes-custom"
# Hermes provider id -> the id Octop's presets use.
_PROVIDER_ALIASES = {
    "openai-api": "openai",
    "gemini": "google",
    "kimi-coding": "moonshot",
    "alibaba": "dashscope",
}
_LOCAL_PROVIDERS = frozenset({"custom", "ollama", "vllm", "llamacpp"})
_TRANSPORT_KINDS = {"chat_completions": "openai", "anthropic_messages": "anthropic"}
# Octop kind -> {Octop field: Hermes .env variable}.
_CHANNELS: dict[str, dict[str, str]] = {
    "telegram": {"bot_token": "TELEGRAM_BOT_TOKEN"},
    "discord": {"bot_token": "DISCORD_BOT_TOKEN"},
    "feishu": {"app_id": "FEISHU_APP_ID", "app_secret": "FEISHU_APP_SECRET"},
    "dingtalk": {"client_id": "DINGTALK_CLIENT_ID", "client_secret": "DINGTALK_CLIENT_SECRET"},
    "wecom": {"bot_id": "WECOM_BOT_ID", "secret": "WECOM_SECRET"},
    "qq": {"app_id": "QQ_APP_ID", "client_secret": "QQ_CLIENT_SECRET"},
}
_UNSUPPORTED_PLATFORM_VARS = {
    "slack": "SLACK_BOT_TOKEN",
    "whatsapp": "WHATSAPP_ENABLED",
    "signal": "SIGNAL_HTTP_URL",
    "matrix": "MATRIX_ACCESS_TOKEN",
    "mattermost": "MATTERMOST_TOKEN",
}
_MEMORY_ENTRY_DELIMITER = "\n§\n"
_ENV_REF = re.compile(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}")


def find_hermes_home(
    env: Mapping[str, str] | None = None, *, user_home: Path | None = None
) -> Path | None:
    """The Hermes home directory, or None when there is no install."""
    env = os.environ if env is None else env
    explicit = env.get("HERMES_HOME")
    path = Path(explicit).expanduser() if explicit else (user_home or Path.home()) / ".hermes"
    return path if path.is_dir() else None


def read_hermes(home: Path, *, env: Mapping[str, str] | None = None) -> MigrationPlan:
    plan = MigrationPlan(source=SOURCE, home=home)
    config = _load_config(home, plan)
    values: dict[str, str] = {}
    if (home / ".env").is_file():
        values.update(load_env_file(home / ".env"))
    values.update(os.environ if env is None else env)

    def substitute(text: str) -> str:
        return _ENV_REF.sub(lambda m: values.get(m.group(1), m.group(0)), text)

    _read_models(plan, config, values)
    _read_files(plan, home)
    add_skills(plan, discover_skills(home / "skills", skip=_bundled_skills(home)))
    for name, raw in as_dict(config.get("mcp_servers")).items():
        add_mcp_server(
            plan, name, raw, resolve=substitute, default_remote_transport="streamable_http"
        )
    _read_channels(plan, values)
    cron_jobs = count_cron_jobs(home / "cron" / "jobs.json")
    if cron_jobs:
        plan.note("cron_not_migrated", count=cron_jobs)
    return plan


def _load_config(home: Path, plan: MigrationPlan) -> dict[str, Any]:
    path = home / "config.yaml"
    if not path.is_file():
        plan.note("config_missing", path=str(path))
        return {}
    try:
        return as_dict(yaml.safe_load(path.read_text(encoding="utf-8-sig")))
    except (OSError, yaml.YAMLError) as exc:
        plan.note("config_unreadable", path=str(path), error=str(exc))
        return {}


def _custom_endpoints(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``providers:`` map plus the legacy ``custom_providers:`` list, keyed by name."""
    out: dict[str, dict[str, Any]] = {}
    for entry in config.get("custom_providers") or []:
        if isinstance(entry, dict) and entry.get("name"):
            out[str(entry["name"])] = entry
    for name, entry in as_dict(config.get("providers")).items():
        if isinstance(entry, dict):
            out[str(name)] = entry
    return out


def _endpoint_provider(
    plan: MigrationPlan, name: str, entry: dict[str, Any], values: Mapping[str, str]
) -> ProviderImport | None:
    base_url = str(entry.get("api") or entry.get("base_url") or entry.get("url") or "")
    transport = str(entry.get("transport") or entry.get("api_mode") or "chat_completions")
    if transport not in _TRANSPORT_KINDS or not base_url:
        plan.note("provider_unsupported", name=name, api=transport)
        return None
    models: list[str] = []
    listed = entry.get("models")
    if isinstance(listed, dict):
        models.extend(str(model) for model in listed)
    elif isinstance(listed, list):
        models.extend(str(m.get("id") if isinstance(m, dict) else m) for m in listed)
    default = entry.get("default_model") or entry.get("model")
    if default and str(default) not in models:
        models.insert(0, str(default))
    api_key = entry.get("api_key") or values.get(str(entry.get("key_env") or ""))
    return ProviderImport(
        name=name,
        kind=_TRANSPORT_KINDS[transport],
        base_url=base_url,
        api_key=str(api_key) if api_key else None,
        models=tuple(models),
    )


def _read_models(plan: MigrationPlan, config: dict[str, Any], values: Mapping[str, str]) -> None:
    for name, entry in _custom_endpoints(config).items():
        provider = _endpoint_provider(plan, name, entry, values)
        if provider is not None:
            plan.providers.append(provider)
    imported = {provider.name for provider in plan.providers}

    model = config.get("model")
    model = {"default": model} if isinstance(model, str) else as_dict(model)
    model_id = str(model.get("default") or model.get("model") or model.get("name") or "")
    if not model_id:
        return
    provider_id = str(model.get("provider") or "auto")
    base_url = str(model.get("base_url") or model.get("api_base") or "")

    if provider_id.startswith("custom:"):
        name = provider_id.removeprefix("custom:")
        if name in imported:
            plan.default_model = (name, model_id)
        return
    if provider_id == "auto" and not base_url:
        # Hermes picks the first provider it has a key for.
        provider_id = next(
            (
                pid
                for pid, (_, _, keys) in KNOWN_PROVIDERS.items()
                if any(values.get(k) for k in keys)
            ),
            "auto",
        )
    provider_id = _PROVIDER_ALIASES.get(provider_id, provider_id)
    if provider_id in KNOWN_PROVIDERS and not base_url:
        found = known_provider(provider_id, values, model_id)
        if found is None:
            plan.note("provider_key_missing", name=provider_id)
            return
        plan.providers.append(found)
        plan.default_model = (provider_id, model_id)
        return
    if base_url and (provider_id in _LOCAL_PROVIDERS or provider_id in ("auto", "openrouter")):
        api_key = model.get("api_key") or values.get("OPENAI_API_KEY")
        plan.providers.append(
            ProviderImport(
                name=_CUSTOM_PROVIDER,
                kind="openai",
                base_url=base_url,
                api_key=str(api_key) if api_key else None,
                models=(model_id,),
            )
        )
        plan.default_model = (_CUSTOM_PROVIDER, model_id)
        return
    plan.note("provider_unsupported", name=provider_id, api="built-in")


def _read_files(plan: MigrationPlan, home: Path) -> None:
    soul = home / "SOUL.md"
    if soul.is_file():
        plan.files.append(FileImport(dest="SOUL.md", source=soul))
    for name in ("MEMORY.md", "USER.md"):
        path = home / "memories" / name
        if not path.is_file():
            continue
        # Hermes separates memory entries with a line holding only "§".
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        entries = [entry.strip() for entry in raw.split(_MEMORY_ENTRY_DELIMITER)]
        content = "\n\n".join(entry for entry in entries if entry) + "\n"
        plan.files.append(FileImport(dest=name, source=path, content=content))


def _bundled_skills(home: Path) -> frozenset[str]:
    """Skill names Hermes ships itself, from ``skills/.bundled_manifest``.

    The manifest maps skill name to content hash, as JSON or ``name:hash``
    lines. An unreadable one skips nothing, so every skill is offered.
    """
    path = home / "skills" / ".bundled_manifest"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    try:
        data = json.loads(text)
    except ValueError:
        return frozenset(
            line.split(":", 1)[0].strip() for line in text.splitlines() if line.strip()
        )
    return frozenset(str(name) for name in data) if isinstance(data, dict) else frozenset()


def _read_channels(plan: MigrationPlan, values: Mapping[str, str]) -> None:
    for kind, fields in _CHANNELS.items():
        config = {field: values.get(var, "") for field, var in fields.items()}
        if all(config.values()):
            plan.channels.append(ChannelImport(kind=kind, name=kind, config=config))
    for platform, var in _UNSUPPORTED_PLATFORM_VARS.items():
        if values.get(var):
            plan.note("channel_unsupported", name=platform)
