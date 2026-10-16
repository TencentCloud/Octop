"""Apply Codex OAuth credentials to the Octop provider store."""

from __future__ import annotations

import json
from typing import Any

from octop.infra.agents.providers.codex_catalog import fetch_codex_catalog
from octop.infra.agents.providers.codex_oauth import (
    CODEX_BASE_URL,
    CodexOAuthCredentials,
    build_codex_headers,
    save_codex_token,
)
from octop.infra.utils.paths import PathLayout

CODEX_PROVIDER_NAME = "openai-codex"


def apply_codex_credentials(
    services: Any,
    paths: PathLayout,
    cred: CodexOAuthCredentials,
    *,
    set_active: bool = True,
) -> int:
    """Create or update the ``openai-codex`` provider row. Returns provider id."""
    account_id = cred.get("account_id", "")
    # Discover before writing anything: failures leave the previous provider,
    # active model and saved credentials intact, and the caller shows the error.
    models = fetch_codex_catalog(cred["access"], account_id)
    row = services.provider_repo.get_by_name(CODEX_PROVIDER_NAME)
    try:
        old_extra = json.loads(row.extra_json or "{}") if row else {}
    except (TypeError, ValueError):
        old_extra = {}
    if not isinstance(old_extra, dict):
        old_extra = {}
    old_headers = old_extra.get("headers", {})
    same_account = (
        bool(account_id)
        and isinstance(old_headers, dict)
        and (old_headers.get("chatgpt-account-id") == account_id)
    )
    if row and same_account:
        previous = {m["id"]: m for m in row.get_models() if isinstance(m, dict) and m.get("id")}
        for model in models:
            # Keep explicit per-model settings without reviving retired models
            # or replacing fresh catalog identity/capability metadata.
            old = previous.get(model["id"], {})
            model.update({k: v for k, v in old.items() if k not in model or k == "enabled"})
    extra = dict(old_extra) if same_account else {}
    extra["headers"] = build_codex_headers(account_id)
    extra_json = json.dumps(extra)
    models_json = json.dumps(models)
    active_provider, active_model = services.settings_repo.get_active_model()
    save_codex_token(paths, cred)
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
        enabled_ids = [m["id"] for m in models if m.get("enabled", True)]
        chosen = (
            active_model
            if (
                same_account
                and active_provider == CODEX_PROVIDER_NAME
                and active_model in enabled_ids
            )
            else next(iter(enabled_ids), "")
        )
        services.settings_repo.set_active_model(CODEX_PROVIDER_NAME, chosen)
    return int(pid)


def sync_refreshed_codex_api_key(services: Any, paths: PathLayout, access_token: str) -> None:
    row = services.provider_repo.get_by_name(CODEX_PROVIDER_NAME)
    if row is not None:
        services.provider_repo.update(row.id, api_key=access_token)
