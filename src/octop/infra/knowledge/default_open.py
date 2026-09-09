"""Knowledge-base selection defaults for a single chat turn."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY = "default_knowledge_base_ids"


class _KnowledgeBase(Protocol):
    id: str
    owner_user_id: int
    default_open: bool


def default_knowledge_base_ids_from_config(cfg: object | None) -> list[str]:
    """Read agent ``default_knowledge_base_ids``; missing/invalid → empty."""
    if not isinstance(cfg, dict):
        return []
    raw = cfg.get(DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY)
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        kid = item.strip()
        if not kid or kid in seen:
            continue
        seen.add(kid)
        out.append(kid)
    return out


def normalize_config_default_knowledge_base_ids(cfg: dict[str, object]) -> dict[str, object]:
    """Validate/normalize ``default_knowledge_base_ids``; raises ``ValueError`` on bad types."""
    if DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY not in cfg:
        return dict(cfg)
    out = dict(cfg)
    raw = out.get(DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY)
    if raw is None:
        out.pop(DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY, None)
        return out
    if not isinstance(raw, list):
        raise ValueError("default_knowledge_base_ids must be a list of strings")
    cleaned = default_knowledge_base_ids_from_config({DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY: raw})
    if cleaned:
        out[DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY] = cleaned
    else:
        out.pop(DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY, None)
    return out


def apply_default_knowledge_base_ids(
    config: dict[str, object],
    ids: object | None,
) -> dict[str, object]:
    """Write ``default_knowledge_base_ids`` when *ids* is set. Mutates and returns *config*."""
    if ids is None:
        return config
    if not isinstance(ids, list):
        raise ValueError("default_knowledge_base_ids must be a list of strings")
    cleaned = default_knowledge_base_ids_from_config({DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY: ids})
    if cleaned:
        config[DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY] = cleaned
    else:
        config.pop(DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY, None)
    return config


def merge_knowledge_base_ids(
    visible_bases: Sequence[_KnowledgeBase],
    explicit_ids: list[str] | None,
    *,
    owner_user_id: int,
    agent_default_ids: Sequence[str] | None = None,
) -> list[str]:
    """Resolve turn KB ids: explicit → agent defaults → owner default-open.

    ``default_open`` is per-owner preference: shared bases marked default-open
    are auto-injected only for the creating user, not for other viewers.
    Agent defaults are filtered to ids present in *visible_bases*.
    """
    if explicit_ids is not None:
        return list(explicit_ids)
    visible = {base.id for base in visible_bases}
    if agent_default_ids:
        selected = [kid for kid in agent_default_ids if kid in visible]
        if selected:
            return selected
    return [
        base.id
        for base in visible_bases
        if base.default_open and int(base.owner_user_id) == int(owner_user_id)
    ]
