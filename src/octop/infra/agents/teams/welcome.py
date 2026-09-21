"""Team chat welcome: host intro + members' own quick cards."""

from __future__ import annotations

from typing import Any

from octop.infra.agents.experts.catalog import (
    default_welcome_payload,
    read_workspace_manifest_data,
    welcome_payload_from_expert,
    welcome_payload_from_manifest_data,
)
from octop.infra.agents.profile import welcome_from_row
from octop.infra.agents.teams.service import is_team_agent
from octop.infra.db.repos.agents import AgentRow

_TEAM_INTRO = {
    "zh": "这是一个专家团队，成员各有专长，会一起回答你的问题。",
    "en": "This is an expert team. Members bring different strengths and answer together.",
}


async def _workspace_welcome(registry: Any, agent_id: str) -> dict[str, Any] | None:
    workspace = registry.workspace_for_agent(agent_id)
    if workspace is None:
        return None
    manifest = await read_workspace_manifest_data(workspace)
    if manifest is None:
        return None
    return welcome_payload_from_manifest_data(manifest)


def _prompt_cards(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    cards = payload.get("quick_prompts")
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def _card_key(card: dict[str, Any]) -> tuple[str, str, str, str]:
    title_raw = card.get("title")
    prompt_raw = card.get("prompt")
    title: dict[str, Any] = title_raw if isinstance(title_raw, dict) else {}
    prompt: dict[str, Any] = prompt_raw if isinstance(prompt_raw, dict) else {}
    return (
        str(title.get("zh") or "").strip(),
        str(title.get("en") or "").strip(),
        str(prompt.get("zh") or "").strip(),
        str(prompt.get("en") or "").strip(),
    )


def _catalog_welcome(row: AgentRow, catalog: Any) -> dict[str, Any] | None:
    if catalog is None:
        return None
    template = str(getattr(row, "template_name", None) or "").strip()
    if not template:
        return None
    getter = getattr(catalog, "get", None)
    if not callable(getter):
        return None
    expert = getter(template)
    if expert is None:
        return None
    return welcome_payload_from_expert(expert)


async def _member_quick_prompts(
    registry: Any,
    member: AgentRow,
    catalog: Any,
) -> list[dict[str, Any]]:
    """Same cards the member's own welcome screen would show."""
    workspace = await _workspace_welcome(registry, member.agent_id)
    cards = _prompt_cards(workspace)
    if cards:
        return cards
    cards = _prompt_cards(_catalog_welcome(member, catalog))
    if cards:
        return cards
    return _prompt_cards(default_welcome_payload(catalog))


async def team_host_welcome_payload(
    row: AgentRow,
    registry: Any,
    catalog: Any = None,
) -> dict[str, Any]:
    """Host welcome copy plus each member's existing quick cards.

    The team itself is not turned into cards: host ``quick_prompts`` are ignored.
    Member cards follow the same resolution as 1:1 chat (workspace, then the
    member's expert template, then the shared default set). Identical cards
    from several members are kept once.
    """
    host = await _workspace_welcome(registry, row.agent_id)
    db_welcome = welcome_from_row(row)
    if db_welcome is not None:
        welcome_message = {"zh": db_welcome, "en": db_welcome}
    elif isinstance(host, dict) and isinstance(host.get("welcome_message"), dict):
        welcome_message = host["welcome_message"]
    else:
        welcome_message = dict(_TEAM_INTRO)

    prompts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    teams = getattr(registry, "teams", None)
    member_ids = teams.visible_member_ids(row.agent_id) if teams is not None else []
    for member_id in member_ids:
        if member_id == row.agent_id:
            continue
        member = registry.get_row(member_id)
        if member is None or is_team_agent(member):
            continue
        expert_name = str(getattr(member, "name", "") or "").strip()
        for card in await _member_quick_prompts(registry, member, catalog):
            key = (*_card_key(card), member.agent_id)
            if not any(key[:4]) or key in seen:
                continue
            seen.add(key)
            stamped = dict(card)
            stamped["expert"] = expert_name
            stamped["agent_id"] = member.agent_id
            prompts.append(stamped)
    return {"welcome_message": welcome_message, "quick_prompts": prompts}
