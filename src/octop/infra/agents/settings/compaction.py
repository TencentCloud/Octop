"""Per-expert automatic context compaction.

Stored on the agent under ``config_json["compaction"]``. Empty means the
harness defaults: compact at 85% of the context window, keep 10%, and send at
most 8000 tokens of evicted history to the summary model.

Forwarded to ``HarnessAgentConfig`` only when the installed octop-harness
accepts the fields:

- ``summarization_enabled``
- ``summarization_trigger`` — ``("fraction", float)``
- ``summarization_keep`` — ``("fraction", float)``
- ``summarization_trim_tokens``
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

COMPACTION_CONFIG_KEY = "compaction"
DEFAULT_TRIGGER_FRACTION = 0.85
DEFAULT_KEEP_FRACTION = 0.10
DEFAULT_TRIM_TOKENS = 8000
MIN_TRIM_TOKENS = 1000

_HARNESS_ENABLED = "summarization_enabled"
_HARNESS_TRIGGER = "summarization_trigger"
_HARNESS_KEEP = "summarization_keep"
_HARNESS_TRIM = "summarization_trim_tokens"


def _fraction(value: Any, *, upper: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    parsed = float(value)
    if 0 < parsed <= upper:
        return parsed
    return None


def _trim_tokens(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < MIN_TRIM_TOKENS:
        return None
    return value


def normalize_compaction(value: Any) -> dict[str, Any] | None:
    """Return the stored object, or ``None`` when it matches the harness default.

    Invalid entries are dropped. ``enabled: true`` alone is the default and is
    not stored. ``None`` and non-objects clear the setting.
    """
    if not isinstance(value, dict):
        return None
    cleaned: dict[str, Any] = {}
    enabled = value.get("enabled")
    if isinstance(enabled, bool) and enabled is False:
        cleaned["enabled"] = False
    trigger = _fraction(value.get("trigger_fraction"), upper=1)
    if trigger is not None:
        cleaned["trigger_fraction"] = trigger
    keep_limit = trigger if trigger is not None else DEFAULT_TRIGGER_FRACTION
    keep = _fraction(value.get("keep_fraction"), upper=1)
    if keep is not None and keep < keep_limit:
        cleaned["keep_fraction"] = keep
    trim = _trim_tokens(value.get("trim_tokens"))
    if trim is not None:
        cleaned["trim_tokens"] = trim
    if not cleaned:
        return None
    return cleaned


def apply_compaction_update(cfg: dict[str, Any], value: Any) -> dict[str, Any]:
    """Merge one compaction update into an agent config dict.

    ``None`` and an empty or default-only object remove the key.
    """
    merged = dict(cfg)
    normalized = normalize_compaction(value)
    if normalized is None:
        merged.pop(COMPACTION_CONFIG_KEY, None)
    else:
        merged[COMPACTION_CONFIG_KEY] = normalized
    return merged


def compaction_for_api(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Return the stored compaction object for API responses."""
    raw = cfg.get(COMPACTION_CONFIG_KEY)
    if not isinstance(raw, dict):
        return None
    return normalize_compaction(raw)


def harness_summarization_kwargs(
    cfg: dict[str, Any],
    *,
    supported_fields: frozenset[str],
) -> dict[str, Any]:
    """Map stored compaction onto harness config kwargs the install understands."""
    stored = compaction_for_api(cfg)
    if not stored:
        return {}
    if stored.get("enabled") is False:
        if _HARNESS_ENABLED in supported_fields:
            return {_HARNESS_ENABLED: False}
        logger.debug(
            "agent compaction is disabled, but this octop-harness has no %s field",
            _HARNESS_ENABLED,
        )
        return {}

    out: dict[str, Any] = {}
    trigger = stored.get("trigger_fraction")
    if trigger is not None and _HARNESS_TRIGGER in supported_fields:
        out[_HARNESS_TRIGGER] = ("fraction", float(trigger))
    keep = stored.get("keep_fraction")
    if keep is not None and _HARNESS_KEEP in supported_fields:
        out[_HARNESS_KEEP] = ("fraction", float(keep))
    trim = stored.get("trim_tokens")
    if trim is not None and _HARNESS_TRIM in supported_fields:
        out[_HARNESS_TRIM] = int(trim)
    if (
        stored
        and not out
        and not supported_fields.intersection(
            {_HARNESS_ENABLED, _HARNESS_TRIGGER, _HARNESS_KEEP, _HARNESS_TRIM}
        )
    ):
        logger.debug(
            "installed octop-harness has no summarization config fields; compaction saved only"
        )
    return out


__all__ = [
    "COMPACTION_CONFIG_KEY",
    "DEFAULT_KEEP_FRACTION",
    "DEFAULT_TRIGGER_FRACTION",
    "DEFAULT_TRIM_TOKENS",
    "MIN_TRIM_TOKENS",
    "apply_compaction_update",
    "compaction_for_api",
    "harness_summarization_kwargs",
    "normalize_compaction",
]
