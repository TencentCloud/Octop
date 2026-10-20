"""Configuration file discovery, loading, and merging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop_harness.cli.config.paths import CliPaths
from octop_harness.cli.config.schema import CliConfig


def load_config(
    project_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, CliConfig]:
    """Load and merge configuration from all layers.

    Layer order (later layers override earlier):

    1. **Global** ``~/.octop-harness/config.json`` — primary config,
       written by ``octop-harness init``.
    2. **Project** ``<cwd>/.octop-harness/config.json`` — optional
       per-project overrides, deep-merged on top of global.
    3. **Credentials** ``~/.octop-harness/credentials.json`` and
       provider env vars — injected into the resolved providers map.

    Returns:
        A tuple of (agent_config_dict or None, cli_config).
        agent_config_dict is the merged dict suitable for
        HarnessAgentConfig.from_dict(), or None if no providers
        are configured.
    """
    if project_dir is None:
        project_dir = Path.cwd()

    paths = CliPaths(project_dir=project_dir)

    # Load layers
    global_data = _load_json(paths.global_config_file)
    project_data = _load_json(paths.project_config_file)
    credentials = _load_json(paths.credentials_file)

    # Merge: project overrides global (per-project tweaks win over user-global)
    merged = _deep_merge(global_data, project_data)

    # Extract CLI-specific config
    cli_data = merged.pop("cli", {})
    cli_cfg = CliConfig.from_dict(cli_data) if cli_data else CliConfig()

    # Inject credentials into providers
    providers = merged.get("providers")
    if providers and isinstance(providers, dict):
        _inject_credentials(providers, credentials)

    # Return None if no providers configured
    if not merged.get("providers"):
        return None, cli_cfg

    return merged, cli_cfg


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning empty dict if missing or invalid."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dicts. Override wins for scalars and arrays."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _inject_credentials(providers: dict[str, Any], credentials: dict[str, Any]) -> None:
    """Inject API keys from credentials.json into providers.

    Note: Environment variable injection (OPENAI_API_KEY, HARNESS_PROVIDER_* etc.)
    is handled automatically by HarnessAgentConfig.__post_init__ via
    ``octop_harness.config.env.detect_providers_from_env()``.
    This function only handles the credentials.json layer.
    """
    for provider_name, provider_cfg in providers.items():
        if not isinstance(provider_cfg, dict):
            continue
        # API key from credentials.json (only if not already set in config)
        if not provider_cfg.get("api_key") and provider_name in credentials:
            provider_cfg["api_key"] = credentials[provider_name]
