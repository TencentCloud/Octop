"""Attach this turn's MCP specs when the expert is a managed ACP runner.

The harness converts those specs and sends them on ``session/new`` and
``session/load``. Connectors are the specs a native expert already loads.
Knowledge search, ``ask_agent``, ``send_file_to_user``, cron, enabled plugin
tools, and memory (only when this expert turns memory on) are extra loopback
servers, because the runner is another process and cannot see Octop's
in-process tools.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_KNOWLEDGE_NAME = "octop-knowledge"
_AGENTS_NAME = "octop-agents"
_FILES_NAME = "octop-files"
_CRON_NAME = "octop-cron"
_MEMORY_NAME = "octop-memory"
_PLUGINS_NAME = "octop-plugins"
_TEAM_WORKSPACE_NAME = "octop-team-workspace"
_LOOPBACK_NAMES = {
    _KNOWLEDGE_NAME,
    _AGENTS_NAME,
    _FILES_NAME,
    _CRON_NAME,
    _MEMORY_NAME,
    _PLUGINS_NAME,
    _TEAM_WORKSPACE_NAME,
}

_SCOPES: dict[str, KnowledgeScope] = {}
_TOKENS: dict[tuple[Any, ...], str] = {}


@dataclass(frozen=True)
class KnowledgeScope:
    user_id: int
    is_admin: bool
    knowledge_base_ids: tuple[str, ...]
    locale: str
    catalog: tuple[tuple[str, str, str], ...]

    def catalog_rows(self) -> list[dict[str, str]]:
        return [
            {"id": kb_id, "name": name, "description": description}
            for kb_id, name, description in self.catalog
        ]


def knowledge_scope(token: str) -> KnowledgeScope | None:
    return _SCOPES.get(token)


def retain_knowledge_scope(scope: KnowledgeScope) -> str:
    """Reuse one token for the same user and knowledge-base selection."""
    key = (scope.user_id, scope.is_admin, scope.knowledge_base_ids, scope.locale)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = scope
    return token


def _catalog(raw: Any) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(raw, list):
        return ()
    rows: list[tuple[str, str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kb_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or kb_id).strip()
        if not kb_id and not name:
            continue
        rows.append((kb_id or name, name or kb_id, str(item.get("description") or "").strip()))
    return tuple(rows)


def _ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _user_id(request: dict[str, Any]) -> int | None:
    raw = request.get("user")
    if raw is None:
        configurable = request.get("configurable")
        if isinstance(configurable, dict):
            raw = configurable.get("user")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _http_spec(url: str) -> dict[str, Any]:
    return {"transport": "http", "url": url}


def _enabled(disabled: set[str], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if name not in disabled)


def _attach(specs: dict[str, Any], server_name: str, url: str | None) -> None:
    if url:
        specs[server_name] = _http_spec(url)


def _connectors_allowed(request: dict[str, Any], cfg: dict[str, Any]) -> bool:
    mode = str(request.get("conversation_mode") or cfg.get("conversation_mode") or "craft")
    return mode.strip().lower() not in {"ask", "plan"}


def _tool_limit_note(specs: dict[str, Any], locale: str) -> str | None:
    """Tell the agent which connector tools it may call. ACP cannot filter them."""
    chinese = locale.lower().startswith("zh")
    lines: list[str] = []
    for name, spec in specs.items():
        if name in _LOOPBACK_NAMES or not isinstance(spec, dict):
            continue
        allowed = spec.get("allowed_tools")
        if not isinstance(allowed, list) or not allowed:
            continue
        listed = (
            "、".join(str(item) for item in allowed)
            if chinese
            else ", ".join(str(item) for item in allowed)
        )
        if chinese:
            lines.append(f"连接器 {name} 只使用这些工具：{listed}。")
        else:
            lines.append(f"For connector {name}, use only these tools: {listed}.")
    return "\n".join(lines) if lines else None


def _team_workspace_note(
    manager: Any,
    cfg: dict[str, Any],
    locale: str,
    *,
    deliver: bool,
) -> tuple[str, str] | None:
    """URL and prompt note for the host workspace, or ``None`` when unset."""
    from octop.infra.agents.acp.team_workspace_mcp import (
        TeamWorkspaceScope,
        retain_team_workspace_scope,
    )
    from octop.infra.agents.teams.file_target import (
        BRIDGE_TARGET_KEY,
        DIR_KEY,
        HOST_KEY,
        capability_enabled,
        file_target_briefing,
    )
    from octop.infra.connectors.builder import team_workspace_mcp_url

    directory = cfg.get(DIR_KEY)
    if not isinstance(directory, str) or not directory.strip():
        return None
    execute = capability_enabled(cfg, "execute")
    bridge_id = cfg.get(BRIDGE_TARGET_KEY)
    host_id = cfg.get(HOST_KEY)
    local = isinstance(bridge_id, str) and bool(bridge_id.strip())
    if local:
        scope = TeamWorkspaceScope(
            host_agent_id="",
            directory=directory.strip(),
            execute=execute,
            bridge_target_id=str(bridge_id).strip(),
            deliver=deliver,
        )
    elif isinstance(host_id, str) and host_id.strip():
        scope = TeamWorkspaceScope(
            host_agent_id=host_id.strip(),
            directory=directory.strip(),
            execute=execute,
            deliver=deliver,
        )
    else:
        return None
    token = retain_team_workspace_scope(scope)
    url = team_workspace_mcp_url(config=manager._config, token=token)
    if not url:
        return None
    return url, file_target_briefing(
        locale,
        directory.strip(),
        execute=execute,
        managed=True,
        local=local,
        deliver=deliver,
    )


def _send_file_note(locale: str) -> str:
    if locale.lower().startswith("zh"):
        return "要把文件发给用户时，调用 send_file_to_user，传入工作区里已有的文件路径。"
    return (
        "To deliver a file to the user, call send_file_to_user "
        "with an existing path in the workspace."
    )


def _server_timezone(manager: Any) -> str:
    config = getattr(manager, "_config", None)
    raw = getattr(config, "default_timezone", None)
    text = raw.strip() if isinstance(raw, str) else ""
    return text or "Asia/Shanghai"


def _cron_note(locale: str, timezone_name: str) -> str:
    """Point a managed runner at Octop's cron tools, not its own session scheduler."""
    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        now = datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")
    except ZoneInfoNotFoundError:
        now = ""
    if locale.lower().startswith("zh"):
        clock = f"当前时间是 {now}（{timezone_name}）。" if now else ""
        return (
            f"{clock}"
            "定时提醒和周期任务只用 octop-cron 的 cronjob_create、cronjob_list、"
            "cronjob_update、cronjob_delete。"
            "不要调用 CronCreate、CronDelete、CronList：那些只存在于当前会话，不会出现在任务列表里。"
            f"日程按 {timezone_name} 解释。"
            "固定提醒用 task_type=text；要跑代码用 task_type=script。"
            "script_lang 必须是 python、bash 或 powershell 这三个字符串之一，不要传 null；不传则是 python。"
            "内联脚本用 script_source=inline，把源码放进 prompt。"
            "工作区文件用 script_source=file，script_path 写相对路径（不能是绝对路径，也不能含 ..），prompt 填同一路径。"
            "例如每 10 分钟打印：task_type=script，script_lang=python，script_source=inline，"
            "prompt 为 print('helloworld')，trigger=interval:600。"
            "智能体任务要跳过本次审批时 allow_all=true，不会改对话里已保存的放通。"
            "重复用 trigger=cron:五段表达式或 interval:秒数；"
            "一次性用 trigger=date:带时区的 ISO 时间。"
        )
    clock = f"The current time is {now} ({timezone_name}). " if now else ""
    return (
        f"{clock}"
        "For reminders and recurring jobs, call only the octop-cron tools "
        "cronjob_create, cronjob_list, cronjob_update, and cronjob_delete. "
        "Do not call CronCreate, CronDelete, or CronList: those live only in this session "
        "and never appear in the task list. "
        f"Interpret schedules in {timezone_name}. "
        "Use task_type=text for a fixed reminder. "
        "Use task_type=script to run code. "
        "script_lang must be the string python, bash, or powershell, never null; "
        "omit it for python. "
        "Inline: script_source=inline and the source in prompt. "
        "Workspace file: script_source=file, a relative script_path with no '..', "
        "and the same path in prompt. "
        "Set allow_all=true on an agent job to skip approval for that run only; "
        "it does not change the conversation's saved approval setting. "
        "trigger=cron:<5 fields> or interval:<seconds> to repeat; "
        "trigger=date:<ISO with offset> to run once."
    )


def _stored_config(manager: Any, agent_id: str) -> dict[str, Any]:
    getter = getattr(manager, "get_config", None)
    if not callable(getter):
        return {}
    try:
        config = getter(agent_id)
    except Exception:
        logger.warning("managed ACP could not read config for %s", agent_id, exc_info=True)
        return {}
    return config if isinstance(config, dict) else {}


def _session_key(request: dict[str, Any], cfg: dict[str, Any], agent_id: str, user_id: int) -> str:
    raw = cfg.get("session_key") or request.get("session_key")
    text = str(raw or "").strip()
    if text:
        return text
    from octop.infra.gateway.threads import ThreadRegistry

    return ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user_id)


def _managed_session_mode(
    manager: Any, agent_id: str, request: dict[str, Any], cfg: dict[str, Any]
) -> str:
    from octop.infra.agents.acp.session_modes import resolve_managed_session_mode

    explicit = request.get("session_mode") or cfg.get("acp_session_mode")
    thread_id = _thread_id(request, cfg)
    stored = None
    store = getattr(manager, "_hitl_session_store", None)
    repo = getattr(store, "_repo", None)
    getter = getattr(repo, "get", None)
    if callable(getter) and thread_id:
        row = getter(thread_id)
        stored = getattr(row, "conversation_mode", None) if row is not None else None
    return resolve_managed_session_mode(
        explicit=explicit,
        stored=stored,
        config=_stored_config(manager, agent_id),
    )


def _thread_id(request: dict[str, Any], cfg: dict[str, Any]) -> str:
    raw = request.get("thread_id") or cfg.get("thread_id")
    return str(raw or "").strip()


def _stored_thread_mode(manager: Any, thread_id: str) -> str | None:
    """Saved chat policy, or ``None`` when this thread has never chosen one."""
    store = getattr(manager, "_hitl_session_store", None)
    repo = getattr(store, "_repo", None)
    getter = getattr(repo, "get", None)
    if callable(getter) and thread_id:
        row = getter(thread_id)
        raw = getattr(row, "hitl_policy", None) if row is not None else None
        if not isinstance(raw, str) or not raw.strip():
            return None
        from octop.infra.agents.security.hitl_session import parse_hitl_session_policy

        policy = parse_hitl_session_policy(raw)
        return "yolo" if policy.mode == "allow_all" else "ask"
    read = getattr(store, "get", None)
    if callable(read) and thread_id:
        policy = read(thread_id)
        return "yolo" if getattr(policy, "mode", None) == "allow_all" else "ask"
    return None


def _expert_permission_mode(manager: Any, agent_id: str) -> str:
    repos = getattr(manager, "_repos", None)
    get = getattr(getattr(repos, "agent_repo", None), "get", None)
    if not callable(get) or not agent_id:
        return "ask"
    row = get(agent_id)
    if row is None:
        return "ask"
    from octop.infra.agents.managed import read_managed_permission_mode
    from octop.infra.agents.settings.profile import parse_config_json

    return read_managed_permission_mode(parse_config_json(getattr(row, "config_json", None)))


def acp_permission_mode(manager: Any, request: dict[str, Any], agent_id: str = "") -> str:
    """``yolo`` when this chat, or the expert's default, has turned off approval."""
    configurable = request.get("configurable")
    cfg = configurable if isinstance(configurable, dict) else {}
    explicit = cfg.get("acp_permission_mode")
    if explicit in {"ask", "yolo"}:
        return str(explicit)
    thread_id = _thread_id(request, cfg)
    stored = _stored_thread_mode(manager, thread_id)
    if stored is not None:
        return stored
    return _expert_permission_mode(manager, agent_id)


async def managed_mcp_specs(
    manager: Any, agent_id: str, request: dict[str, Any]
) -> tuple[dict[str, Any], str | None] | None:
    """Specs and @ note for a managed turn. ``None`` when the agent is native."""
    from octop.infra.agents.acp.cron_mcp import CronScope, retain_cron_scope
    from octop.infra.agents.acp.delegation import prepare_managed_delegation
    from octop.infra.agents.acp.files_mcp import retain_file_scope
    from octop.infra.agents.acp.memory_mcp import memory_enabled, retain_memory_scope
    from octop.infra.agents.acp.plugins_mcp import plugin_tools, retain_plugin_scope
    from octop.infra.agents.managed import is_managed_agent
    from octop.infra.agents.settings.tool_catalog import (
        MANAGED_AGENT_TOOLS,
        MANAGED_CRON_TOOLS,
        MANAGED_FILE_TOOLS,
        MANAGED_KNOWLEDGE_TOOLS,
        MANAGED_MEMORY_TOOLS,
        tools_disabled_set,
    )
    from octop.infra.connectors.builder import (
        cron_mcp_url,
        files_mcp_url,
        knowledge_mcp_url,
        memory_mcp_url,
        plugins_mcp_url,
    )

    row = manager.get_row(agent_id)
    if not is_managed_agent(row):
        return None

    configurable = request.get("configurable")
    cfg = configurable if isinstance(configurable, dict) else {}
    connector_names = _ids(request.get("mcp_servers")) or _ids(cfg.get("mcp_servers"))
    user_id = _user_id(request)
    loaded: dict[str, Any] = {}
    if user_id is not None and connector_names:
        try:
            raw = await manager._connector_svc.mcp_configs_for_user(user_id)
        except Exception:
            logger.warning("managed ACP MCP specs failed for agent %s", agent_id, exc_info=True)
            raw = {}
        if isinstance(raw, dict):
            loaded = raw
    specs: dict[str, Any] = {}
    if _connectors_allowed(request, cfg):
        specs = {
            name: loaded[name] for name in connector_names if isinstance(loaded.get(name), dict)
        }

    stored = _stored_config(manager, agent_id)
    disabled = tools_disabled_set(stored)
    locale = str(cfg.get("locale") or "en")
    # Loopback servers, in the order the runner sees them.
    kb_ids = tuple(_ids(cfg.get("knowledge_base_ids")))
    if kb_ids and user_id is not None and _enabled(disabled, MANAGED_KNOWLEDGE_TOOLS):
        scope = KnowledgeScope(
            user_id=user_id,
            is_admin=bool(cfg.get("user_is_admin")),
            knowledge_base_ids=kb_ids,
            locale=locale,
            catalog=_catalog(cfg.get("knowledge_base_catalog")),
        )
        _attach(
            specs,
            _KNOWLEDGE_NAME,
            knowledge_mcp_url(config=manager._config, token=retain_knowledge_scope(scope)),
        )
    agent_tools = _enabled(disabled, MANAGED_AGENT_TOOLS)
    try:
        note, agents = await prepare_managed_delegation(
            manager,
            agent_id,
            request,
            user_id=user_id,
            tools=agent_tools,
        )
    except Exception:
        logger.warning("managed ACP expert delegation failed for %s", agent_id, exc_info=True)
        note, agents = None, None
    if agents is not None:
        specs[_AGENTS_NAME] = agents
    send_enabled = bool(_enabled(disabled, MANAGED_FILE_TOOLS))
    workspace_note = _team_workspace_note(manager, cfg, locale, deliver=send_enabled)
    if send_enabled and workspace_note is None:
        _attach(
            specs,
            _FILES_NAME,
            files_mcp_url(config=manager._config, token=retain_file_scope(agent_id)),
        )
    cron_tools = _enabled(disabled, MANAGED_CRON_TOOLS)
    if user_id is not None and cron_tools and getattr(manager, "_cron_manager", None) is not None:
        cron_scope = CronScope(
            user_id=user_id,
            agent_id=agent_id,
            thread_id=_thread_id(request, cfg),
            session_key=_session_key(request, cfg, agent_id, user_id),
            tools=cron_tools,
        )
        _attach(
            specs,
            _CRON_NAME,
            cron_mcp_url(config=manager._config, token=retain_cron_scope(cron_scope)),
        )
    memory_tools = _enabled(disabled, MANAGED_MEMORY_TOOLS)
    if memory_enabled(stored) and memory_tools:
        _attach(
            specs,
            _MEMORY_NAME,
            memory_mcp_url(
                config=manager._config,
                token=retain_memory_scope(agent_id, memory_tools),
            ),
        )
    try:
        enabled_plugins = plugin_tools(manager, stored)
    except Exception:
        logger.warning("managed ACP plugin tools failed for %s", agent_id, exc_info=True)
        enabled_plugins = []
    if enabled_plugins:
        plugin_tool_names = tuple(
            sorted(str(getattr(tool, "name", "")) for tool in enabled_plugins)
        )
        _attach(
            specs,
            _PLUGINS_NAME,
            plugins_mcp_url(
                config=manager._config,
                token=retain_plugin_scope(agent_id, plugin_tool_names),
            ),
        )
    if send_enabled and workspace_note is None:
        file_note = _send_file_note(locale)
        note = f"{note}\n{file_note}" if note else file_note
    if workspace_note is not None:
        _attach(specs, _TEAM_WORKSPACE_NAME, workspace_note[0])
        note = f"{note}\n{workspace_note[1]}" if note else workspace_note[1]
    if _CRON_NAME in specs:
        cron_note = _cron_note(locale, _server_timezone(manager))
        note = f"{note}\n{cron_note}" if note else cron_note
    limit = _tool_limit_note(specs, locale)
    if limit:
        note = f"{note}\n{limit}" if note else limit
    if specs:
        logger.info("managed ACP MCP agent=%s servers=%s", agent_id, sorted(specs))
    return specs, note


async def attach_managed_turn(manager: Any, agent_id: str, request: dict[str, Any]) -> None:
    """Put this turn's MCP specs and @ note on ``request`` for the harness."""
    from octop.infra.agents.teams.file_target_guard import install_file_target_guards

    install_file_target_guards()
    extras = await managed_mcp_specs(manager, agent_id, request)
    if extras is None:
        return
    specs, note = extras
    configurable = request.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        request["configurable"] = configurable
    configurable["acp_mcp_servers"] = specs
    session_mode = _managed_session_mode(manager, agent_id, request, configurable)
    if session_mode:
        configurable["acp_session_mode"] = session_mode
    from octop.infra.agents.acp.session_modes import approval_for_session

    stored = _stored_config(manager, agent_id)
    runner = stored.get("managed_runner") if isinstance(stored, dict) else ""
    configurable["acp_permission_mode"] = approval_for_session(
        session_mode,
        acp_permission_mode(manager, request, agent_id),
        runner=runner if isinstance(runner, str) else "",
    )
    if note:
        configurable["acp_prompt_note"] = note
