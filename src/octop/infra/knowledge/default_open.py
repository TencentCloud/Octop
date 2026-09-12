"""Knowledge-base selection defaults for a single chat turn."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from octop.infra.db.repos.knowledge import KnowledgeBaseRow

DEFAULT_KNOWLEDGE_BASE_IDS_CONFIG_KEY = "default_knowledge_base_ids"


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
    visible_bases: Sequence[KnowledgeBaseRow],
    explicit_ids: list[str] | None,
    *,
    owner_user_id: int,
    extra_ids: Sequence[str] | None = None,
    agent_default_ids: Sequence[str] | None = None,
) -> list[str]:
    """Use the actor's own default-open bases when a turn omits a list.

    ``default_open`` is per-owner preference: shared bases marked default-open
    are auto-injected only for the creating user, not for other viewers.
    ``extra_ids`` (expert composer picks) and ``agent_default_ids`` (agent
    config defaults) are unioned in when still visible.
    """
    if explicit_ids is not None:
        return list(explicit_ids)
    selected: list[str] = []
    visible_ids = {base.id for base in visible_bases}
    for base in visible_bases:
        if base.default_open and int(base.owner_user_id) == int(owner_user_id):
            selected.append(base.id)
    extras: list[str] = []
    extras.extend(str(kb_id) for kb_id in extra_ids or [])
    extras.extend(str(kb_id) for kb_id in agent_default_ids or [])
    for kb_id in extras:
        text = kb_id.strip()
        if text and text in visible_ids and text not in selected:
            selected.append(text)
    return selected


def stamp_turn_knowledge_config(
    request: dict[str, Any],
    *,
    visible_bases: Sequence[KnowledgeBaseRow],
    explicit_ids: list[str] | None,
    owner_user_id: int,
    extra_ids: Sequence[str] | None = None,
    is_admin: bool = False,
    locale: str,
) -> list[str]:
    """Write this turn's knowledge-base selection onto the harness request."""
    from octop.infra.knowledge.hint import catalog_for_selected_bases  # noqa: PLC0415

    selected_ids = merge_knowledge_base_ids(
        visible_bases,
        explicit_ids,
        owner_user_id=owner_user_id,
        extra_ids=extra_ids,
    )
    configurable = dict(request.get("configurable") or {})
    configurable["knowledge_base_ids"] = selected_ids
    configurable["knowledge_base_catalog"] = catalog_for_selected_bases(visible_bases, selected_ids)
    configurable["user_is_admin"] = is_admin
    configurable["locale"] = locale
    request["configurable"] = configurable
    return selected_ids
