"""@mentions for a managed ACP agent: subagents stay with the runner, experts call back.

The runner already loads subagents from its own project directory. An ``@slug``
in the prompt tells it to delegate. Other Octop experts are not in that
directory, so ``ask_agent`` is a loopback MCP tool, the same idea as knowledge
search.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

# Same rule as octop-harness ``has_agent_at_mention``: an @name, not @file.ext.
_AGENT_AT_RE = re.compile(r"@([^\W\d_][\w\-]*)(?![\w./\-~]*\.\w)")

_SCOPES: dict[str, AgentScope] = {}
_TOKENS: dict[tuple[int, str, str, tuple[str, ...]], str] = {}


@dataclass
class AgentScope:
    user_id: int
    from_agent_id: str
    thread_id: str
    session_key: str
    tools: tuple[str, ...] = ("agent_list", "ask_agent")


def agent_scope(token: str) -> AgentScope | None:
    return _SCOPES.get(token)


def retain_agent_scope(scope: AgentScope) -> str:
    """Reuse one token per caller, thread, and enabled tool set."""
    key = (scope.user_id, scope.from_agent_id, scope.thread_id, scope.tools)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = scope
    return token


def _is_user_message(message: Any) -> bool:
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "user")
    else:
        role = str(getattr(message, "type", None) or getattr(message, "role", None) or "user")
    return role in {"user", "human"}


def user_text(request: dict[str, Any]) -> str:
    messages = request.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not _is_user_message(message):
            continue
        content = (
            message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
        )
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "".join(parts)
    return ""


def _token(name: str) -> str:
    return "-".join(name.split())


def _mentions(text: str) -> list[str]:
    return [match.group(1) for match in _AGENT_AT_RE.finditer(text)]


def delegation_note_for(
    text: str,
    *,
    experts: list[tuple[str, str]],
    subagents: list[tuple[str, str]],
    locale: str,
) -> str | None:
    """One note when the user wrote ``@Name``. Experts win over a same-named subagent."""
    wanted = _mentions(text)
    if not wanted:
        return None
    expert_by_token = {_token(name): name for name, _desc in experts if _token(name)}
    sub_by_token = {_token(name): (name, desc) for name, desc in subagents if _token(name)}
    expert_hits: list[str] = []
    sub_hits: list[str] = []
    seen: set[str] = set()
    for raw in wanted:
        key = raw.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        if key in expert_by_token:
            expert_hits.append(expert_by_token[key])
            continue
        sub = sub_by_token.get(key)
        if sub is not None:
            label, desc = sub
            sub_hits.append(f"@{label}: {desc}" if desc else f"@{label}")
    if not expert_hits and not sub_hits:
        return None
    chinese = locale.lower().startswith("zh")
    lines: list[str] = []
    if expert_hits:
        names = (
            "、".join(f"@{name}" for name in expert_hits)
            if chinese
            else ", ".join(f"@{name}" for name in expert_hits)
        )
        if chinese:
            lines.append(
                f"用户点名了专家 {names}。调用 ask_agent，expert 用这个名字，不要代替对方回答。"
            )
        else:
            lines.append(
                f"The user named expert {names}. Call ask_agent with that name and do not answer in their place."
            )
    if sub_hits:
        listed = "；".join(sub_hits) if chinese else "; ".join(sub_hits)
        if chinese:
            lines.append(f"用户点名了子智能体 {listed}。把这件事交给同名子智能体。")
        else:
            lines.append(
                f"The user named subagent {listed}. Delegate this request to that subagent."
            )
    return "\n".join(lines)


def _peer_rows(team: Any, *, user_id: int, agent_id: str) -> list[tuple[str, str]]:
    from octop_harness.teams.team_manager import TeamManager

    try:
        peers = team.list_peers(user_id, exclude_agent_id=agent_id)
    except Exception:
        return []
    rows: list[tuple[str, str]] = []
    for entry in peers:
        name = TeamManager.peer_display_name(entry)
        description = str((entry.metadata or {}).get("description") or "").strip()
        if name:
            rows.append((name, description))
    return rows


async def _subagent_rows(manager: Any, agent_id: str) -> list[tuple[str, str]]:
    lister = getattr(manager, "list_subagent_summaries", None)
    if not callable(lister):
        return []
    try:
        rows = await lister(agent_id)
    except Exception:
        return []
    out: list[tuple[str, str]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or row.get("name") or "").strip()
        if not slug:
            continue
        out.append((slug, str(row.get("description") or "").strip()))
    return out


async def prepare_managed_delegation(
    manager: Any,
    agent_id: str,
    request: dict[str, Any],
    *,
    user_id: int | None,
    tools: tuple[str, ...] = ("agent_list", "ask_agent"),
) -> tuple[str | None, dict[str, Any] | None]:
    """Return the @ note and, when this user has peers, an expert-call MCP spec."""
    from octop.infra.connectors.builder import agents_mcp_url

    configurable = request.get("configurable")
    cfg = configurable if isinstance(configurable, dict) else {}
    locale = str(cfg.get("locale") or "en")
    thread_id = str(request.get("thread_id") or "").strip()
    session_key = str(cfg.get("session_key") or "").strip()
    harness = getattr(manager, "_harness_manager", None)
    team = getattr(harness, "team", None)
    experts = (
        _peer_rows(team, user_id=user_id, agent_id=agent_id)
        if team is not None and user_id is not None
        else []
    )
    enabled = tuple(name for name in ("agent_list", "ask_agent") if name in tools)
    subagents = await _subagent_rows(manager, agent_id)
    note = delegation_note_for(
        user_text(request),
        experts=experts if "ask_agent" in enabled else [],
        subagents=subagents,
        locale=locale,
    )
    if user_id is None or not experts or not enabled:
        return note, None
    scope = AgentScope(
        user_id=user_id,
        from_agent_id=agent_id,
        thread_id=thread_id,
        session_key=session_key,
        tools=enabled,
    )
    url = agents_mcp_url(config=manager._config, token=retain_agent_scope(scope))
    return note, {"transport": "http", "url": url}
