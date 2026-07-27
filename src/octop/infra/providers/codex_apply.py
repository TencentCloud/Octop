"""Apply Codex OAuth credentials to the Octop provider store."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.providers.codex_oauth import (
    CODEX_BASE_URL,
    CodexOAuthCredentials,
    build_codex_headers,
    save_codex_token,
)
from octop.infra.utils.paths import PathLayout

CODEX_PROVIDER_NAME = "openai-codex"

CODEX_MODELS = [
    {"id": "gpt-5.4", "name": "GPT-5.4", "enabled": True, "input": ["text"]},
    {"id": "gpt-5.4-mini", "name": "GPT-5.4 mini", "enabled": True, "input": ["text"]},
    {"id": "gpt-5.5", "name": "GPT-5.5", "enabled": True, "input": ["text"]},
    {"id": "gpt-5.6-sol", "name": "GPT-5.6 Sol", "enabled": True, "input": ["text"]},
    {"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra", "enabled": True, "input": ["text"]},
    {"id": "gpt-5.6-luna", "name": "GPT-5.6 Luna", "enabled": True, "input": ["text"]},
]


def apply_codex_credentials(
    services: Any,
    paths: PathLayout,
    cred: CodexOAuthCredentials,
    *,
    set_active: bool = True,
) -> int:
    """Create or update the ``openai-codex`` provider row. Returns provider id."""
    save_codex_token(paths, cred)
    account_id = cred.get("account_id", "")
    extra_json = json.dumps({"headers": build_codex_headers(account_id)})
    models_json = json.dumps(CODEX_MODELS)
    row = services.provider_repo.get_by_name(CODEX_PROVIDER_NAME)
    if row is None:
        pid = services.provider_repo.create(
            name=CODEX_PROVIDER_NAME,
            kind="openai",
            base_url=CODEX_BASE_URL,
            api_key=cred["access"],
            extra_json=extra_json,
            models_json=models_json,
            note="ChatGPT OAuth (Codex)",
        )
    else:
        services.provider_repo.update(
            row.id,
            kind="openai",
            base_url=CODEX_BASE_URL,
            api_key=cred["access"],
            extra_json=extra_json,
            models_json=models_json,
            enabled=True,
        )
        pid = row.id
    if set_active:
        services.settings_repo.set_active_model(CODEX_PROVIDER_NAME, "gpt-5.4")
    return int(pid)


def sync_refreshed_codex_api_key(services: Any, paths: PathLayout, access_token: str) -> None:
    row = services.provider_repo.get_by_name(CODEX_PROVIDER_NAME)
    if row is not None:
        services.provider_repo.update(row.id, api_key=access_token)
