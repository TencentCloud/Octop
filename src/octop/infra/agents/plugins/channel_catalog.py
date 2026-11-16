"""Host channel/group catalog for plugin settings; no plugin policy is interpreted."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from octop_gateway.group_context import GroupContextConfig
from octop_gateway.models import ChannelSubject, InboundMessage

logger = logging.getLogger(__name__)
_NAME_CACHE: dict[tuple[str, str, str], tuple[float, str | None]] = {}


def channels(server: Any) -> list[dict[str, Any]]:
    """Return configured instances without leaking credentials."""
    if server.services is None:
        return []
    repos = server.services.repos
    return [
        {
            "channelKind": row.kind,
            "channelId": row.channel_id,
            "channelName": row.name,
            "agentId": row.agent_id,
        }
        for row in repos.channel_repo.list_all()
    ]


def groups(server: Any) -> list[dict[str, Any]]:
    """Keep platform, instance, group and expert identities separate."""
    if server.services is None:
        return []
    repos = server.services.repos
    runtime = getattr(server, "app_runtime", None)
    manager = runtime.gateway.channel_manager if runtime is not None else None
    get_channel = getattr(manager, "get_channel", lambda _: None)
    rows = repos.channel_repo.list_all()
    sessions = {
        agent: repos.session_repo.list_by_agent(agent, limit=500)
        for agent in {row.agent_id for row in rows}
    }
    found = {}
    for row in rows:
        config = json.loads(row.config_json or "{}")
        raw_group = config.get("group_context")
        raw_group = raw_group if isinstance(raw_group, dict) else {}
        cold = GroupContextConfig.from_dict(raw_group)
        live = get_channel(row.channel_id)
        for session in sessions[row.agent_id]:
            if (
                session.channel_type != row.kind
                or session.channel_chat_type != "group"
                or session.channel_id != row.channel_id
                or not session.channel_subject_id
            ):
                continue
            group_id = session.channel_subject_id
            key = (row.kind, row.channel_id, group_id, row.agent_id)
            if key in found:
                continue
            host = cold.resolve(group_id)
            if live is not None:
                message = InboundMessage(
                    channel_type=row.kind,
                    channel_id=row.channel_id,
                    tenant_id=row.agent_id,
                    content=[],
                    channel_subject=ChannelSubject(subject_id=group_id, chat_type="group"),
                    metadata={"chat_type": "group", "conversation_id": group_id},
                )
                host = live.group_context_manager.policy_for(message)
            found[key] = {
                "channelKind": row.kind,
                "channelId": row.channel_id,
                "groupId": group_id,
                "agentId": row.agent_id,
                "channelName": row.name,
                "updatedAt": session.updated_at,
                "ready": bool(row.enabled and host.enabled and host.visibility == "all"),
                "channelEnabled": bool(row.enabled),
                "policyKnown": live is not None or bool(raw_group),
                "groupPolicyEnabled": bool(host.enabled),
                "groupVisibility": str(host.visibility),
                "pluginSettings": {
                    key: value
                    for key, value in raw_group.items()
                    if key not in GroupContextConfig.__dataclass_fields__ and type(value) is bool
                },
                "hostActivation": str(host.activation),
            }
    return sorted(found.values(), key=lambda item: item["updatedAt"], reverse=True)


async def load_group_names(server: Any, items: list[dict[str, Any]]) -> None:
    """Query names only for settings views, with positive and negative caches."""
    runtime = getattr(server, "app_runtime", None)
    manager = runtime.gateway.channel_manager if runtime is not None else None
    get_channel = getattr(manager, "get_channel", None)
    if not callable(get_channel):
        return
    semaphore = asyncio.Semaphore(5)

    async def lookup(group: dict[str, Any], key: tuple[str, str, str]) -> None:
        channel = get_channel(group["channelId"])
        getter = getattr(channel, "get_group_info", None)
        if not callable(getter):
            return
        try:
            async with semaphore:
                info = await asyncio.wait_for(getter(group["groupId"]), timeout=3)
            name = info.get("group_name") if isinstance(info, dict) else None
            name = name.strip() if isinstance(name, str) and name.strip() else None
            _NAME_CACHE[key] = (time.monotonic() + (43200 if name else 600), name)
            group["groupName"] = name
        except Exception:
            _NAME_CACHE[key] = (time.monotonic() + 600, None)
            logger.debug("Group name unavailable for channel %s", group["channelId"])

    pending: list[tuple[dict[str, Any], tuple[str, str, str]]] = []
    for group in items:
        key = (group.get("channelKind", "qq"), group["channelId"], group["groupId"])
        cached = _NAME_CACHE.get(key)
        group["groupName"] = cached[1] if cached and cached[0] > time.monotonic() else None
        if (not cached or cached[0] <= time.monotonic()) and len(pending) < 20:
            pending.append((group, key))
    await asyncio.gather(*(lookup(group, key) for group, key in pending))
