"""Runtime policy for host-facing memory operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRuntimeConfig:
    """Runtime policy shared by in-process hosts and JSON-RPC bridge adapters."""

    profile: str | None = None
    mode: str | None = None
    recall: dict[str, Any] = field(default_factory=dict)
    capture: dict[str, Any] = field(default_factory=dict)
    privacy: dict[str, Any] = field(default_factory=dict)
    llm: dict[str, Any] = field(default_factory=dict)
    extraction: dict[str, Any] = field(default_factory=dict)


DEFAULT_RECALL_CFG = {
    "default_max_results": 5,
    "default_corpus": "all",
    "raw_policy": "fallback",
    "host_files_policy": "include",
    "layer_order": ["atom", "host_file", "page", "raw"],
}
DEFAULT_CAPTURE_CFG = {
    "min_message_chars": 12,
    "include_roles": ["user", "assistant"],
    "include_tool_calls": False,
    "include_tool_results": False,
    "skip_memory_echo": True,
}
DEFAULT_PRIVACY_CFG = {
    "redact_secrets": True,
    "redact_patterns": [],
    "store_raw_content": True,
    "store_tool_payloads": False,
}
DEFAULT_EXTRACTION_CFG = {
    "max_candidates": 20,
    # ``None`` → the extractor's built-in budget
    # (:data:`octop_memory.ports.llm.DEFAULT_EXTRACT_MAX_TOKENS`). A positive
    # int caps the extraction / episode completions so a reasoning-heavy
    # model cannot run past the client read timeout (TencentCloud/Octop#1360).
    "max_tokens": None,
    "promote": True,
    "regen_pages": True,
    "page_regen_limit": 5,
    # Kept so older host configs still parse. ADR-028 stopped writing
    # extract_run to the journal; the latest pass lives in meta instead.
    # This value is no longer read.
    "journal_noop_heartbeat_minutes": 1440,
}


def coerce_runtime_config(config: MemoryRuntimeConfig | dict[str, Any] | None) -> MemoryRuntimeConfig:
    if config is None:
        return MemoryRuntimeConfig()
    if isinstance(config, MemoryRuntimeConfig):
        return config
    return MemoryRuntimeConfig(
        profile=config.get("profile") if isinstance(config.get("profile"), str) else None,
        mode=config.get("mode") if isinstance(config.get("mode"), str) else None,
        recall=_dict_value(config.get("recall")),
        capture=_dict_value(config.get("capture")),
        privacy=_dict_value(config.get("privacy")),
        llm=_dict_value(config.get("llm")),
        extraction=_dict_value(config.get("extraction")),
    )


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
