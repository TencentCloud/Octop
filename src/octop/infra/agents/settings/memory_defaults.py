"""Global default memory extraction settings & per-expert inheritance resolver.

Implements TencentCloud/Octop#2963:
- Admins configure global defaults for the memory extraction model
  (``aux_model``) and retention/skip rules (``extract_keep_rules`` /
  ``extract_skip_rules``) in ``settings["memory_global_defaults"]``.
- New experts and existing experts without explicit overrides inherit each
  setting independently (``aux_model_mode == "inherit"``,
  ``extract_rules_mode == "inherit"``).
- Existing experts with a non-empty ``memory.aux_model`` and no stored
  ``aux_model_mode`` are inferred as ``"custom"`` so existing overrides stay
  intact without requiring a database migration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

GLOBAL_MEMORY_DEFAULTS_SETTINGS_KEY = "memory_global_defaults"
MAX_EXTRACT_RULE_CHARS = 2000

MemoryOverrideMode = Literal["inherit", "custom"]


@dataclass(frozen=True)
class GlobalMemoryDefaults:
    """Process-wide default memory extraction settings stored in ``settings``."""

    aux_model: str | None = None
    extract_keep_rules: str = ""
    extract_skip_rules: str = ""

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "aux_model": self.aux_model,
            "extract_keep_rules": self.extract_keep_rules,
            "extract_skip_rules": self.extract_skip_rules,
        }


@dataclass(frozen=True)
class EffectiveMemoryDefaults:
    """Resolved per-expert modes, stored custom values, and effective values."""

    aux_model_mode: MemoryOverrideMode
    aux_model: str | None
    extract_rules_mode: MemoryOverrideMode
    extract_keep_rules: str
    extract_skip_rules: str
    effective_aux_model: str | None
    effective_keep_rules: str
    effective_skip_rules: str


def normalize_rule_text(
    value: Any,
    *,
    max_chars: int = MAX_EXTRACT_RULE_CHARS,
    strict: bool = False,
) -> str:
    """Normalize a keep/skip extraction rule string.

    When ``strict=True`` (API write path), non-string values or strings longer
    than *max_chars* raise ``ValueError``. On read (``strict=False``), bad
    persisted shapes degrade safely to empty/truncated text.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if strict:
            raise ValueError("memory rule must be a string")
        return ""
    text = value.strip()
    if len(text) > max_chars:
        if strict:
            raise ValueError(f"memory rule must be at most {max_chars} characters")
        return text[:max_chars].strip()
    return text


def normalize_aux_model_ref(value: Any) -> str | None:
    """Normalize a stored ``aux_model`` value: blank / 'auto' / non-str → None."""
    if not isinstance(value, str):
        return None
    ref = value.strip()
    if not ref or ref.lower() == "auto":
        return None
    return ref


def infer_aux_model_mode(mem: Mapping[str, Any]) -> MemoryOverrideMode:
    """Determine whether an expert inherits the global extraction model or overrides it."""
    mode = mem.get("aux_model_mode")
    if mode == "inherit":
        return "inherit"
    if mode == "custom":
        return "custom"
    # Legacy experts that already pinned a concrete aux_model keep their override.
    if normalize_aux_model_ref(mem.get("aux_model")) is not None:
        return "custom"
    return "inherit"


def infer_extract_rules_mode(mem: Mapping[str, Any]) -> MemoryOverrideMode:
    """Determine whether an expert inherits global memory rules or overrides them."""
    mode = mem.get("extract_rules_mode")
    if mode == "inherit":
        return "inherit"
    if mode == "custom":
        return "custom"
    if normalize_rule_text(mem.get("extract_keep_rules")) or normalize_rule_text(
        mem.get("extract_skip_rules")
    ):
        return "custom"
    return "inherit"


def resolve_effective_memory_defaults(
    mem: Mapping[str, Any] | None,
    global_defaults: GlobalMemoryDefaults | None = None,
) -> EffectiveMemoryDefaults:
    """Resolve an expert's stored ``memory`` section against global defaults."""
    stored = mem if isinstance(mem, Mapping) else {}
    glob = global_defaults if global_defaults is not None else GlobalMemoryDefaults()

    aux_mode = infer_aux_model_mode(stored)
    custom_aux = normalize_aux_model_ref(stored.get("aux_model")) if aux_mode == "custom" else None
    effective_aux = glob.aux_model if aux_mode == "inherit" else custom_aux

    rules_mode = infer_extract_rules_mode(stored)
    custom_keep = (
        normalize_rule_text(stored.get("extract_keep_rules")) if rules_mode == "custom" else ""
    )
    custom_skip = (
        normalize_rule_text(stored.get("extract_skip_rules")) if rules_mode == "custom" else ""
    )
    effective_keep = glob.extract_keep_rules if rules_mode == "inherit" else custom_keep
    effective_skip = glob.extract_skip_rules if rules_mode == "inherit" else custom_skip

    return EffectiveMemoryDefaults(
        aux_model_mode=aux_mode,
        aux_model=custom_aux,
        extract_rules_mode=rules_mode,
        extract_keep_rules=custom_keep,
        extract_skip_rules=custom_skip,
        effective_aux_model=effective_aux,
        effective_keep_rules=effective_keep,
        effective_skip_rules=effective_skip,
    )


def load_global_memory_defaults(settings_repo: Any) -> GlobalMemoryDefaults:
    """Load global memory defaults from ``SettingsRepo``; never raises on corrupt JSON."""
    if settings_repo is None:
        return GlobalMemoryDefaults()
    raw = settings_repo.get(GLOBAL_MEMORY_DEFAULTS_SETTINGS_KEY)
    if not raw:
        return GlobalMemoryDefaults()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Corrupt %s JSON in settings table; using empty defaults",
            GLOBAL_MEMORY_DEFAULTS_SETTINGS_KEY,
        )
        return GlobalMemoryDefaults()
    if not isinstance(parsed, dict):
        return GlobalMemoryDefaults()
    return GlobalMemoryDefaults(
        aux_model=normalize_aux_model_ref(parsed.get("aux_model")),
        extract_keep_rules=normalize_rule_text(parsed.get("extract_keep_rules")),
        extract_skip_rules=normalize_rule_text(parsed.get("extract_skip_rules")),
    )


def save_global_memory_defaults(
    settings_repo: Any,
    defaults: GlobalMemoryDefaults,
) -> GlobalMemoryDefaults:
    """Persist normalized global memory defaults to ``SettingsRepo``."""
    normalized = GlobalMemoryDefaults(
        aux_model=normalize_aux_model_ref(defaults.aux_model),
        extract_keep_rules=normalize_rule_text(defaults.extract_keep_rules, strict=True),
        extract_skip_rules=normalize_rule_text(defaults.extract_skip_rules, strict=True),
    )
    settings_repo.set(
        GLOBAL_MEMORY_DEFAULTS_SETTINGS_KEY,
        json.dumps(normalized.to_storage_dict(), ensure_ascii=False),
    )
    return normalized


__all__ = [
    "EffectiveMemoryDefaults",
    "GLOBAL_MEMORY_DEFAULTS_SETTINGS_KEY",
    "GlobalMemoryDefaults",
    "MAX_EXTRACT_RULE_CHARS",
    "MemoryOverrideMode",
    "infer_aux_model_mode",
    "infer_extract_rules_mode",
    "load_global_memory_defaults",
    "normalize_aux_model_ref",
    "normalize_rule_text",
    "resolve_effective_memory_defaults",
    "save_global_memory_defaults",
]
