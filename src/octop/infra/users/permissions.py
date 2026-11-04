"""Module-level permission catalog and checks.

A permission is a module key (e.g. ``"browser"``, ``"users"``). Possessing a
key grants access to that module's management page and write/configure actions.
Read access and agent use in chat are never gated. ``admin`` bypasses all.

Categories mirror dashboard nav groups: ``settings`` / ``control`` / ``admin``.
``nav`` is the ungrouped pages that can be granted (chat stays ungated).
Admin keys may also carry a ``page`` so the picker can group by page / tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PermissionUser(Protocol):
    @property
    def is_admin(self) -> bool: ...

    permissions: list[str]


@dataclass(frozen=True)
class PermissionDef:
    key: str
    category: str  # "settings" | "control" | "admin"
    label_zh: str
    label_en: str
    page: str = ""
    page_zh: str = ""
    page_en: str = ""
    extra_tabs: tuple[tuple[str, str], ...] = ()
    # Retired umbrellas stay valid in stored grants but are not picker chips.
    assignable: bool = True


def _p(
    key: str,
    category: str,
    label_zh: str,
    label_en: str,
    *,
    page: str = "",
    page_zh: str = "",
    page_en: str = "",
    extra_tabs: tuple[tuple[str, str], ...] = (),
    assignable: bool = True,
) -> PermissionDef:
    return PermissionDef(
        key, category, label_zh, label_en, page, page_zh, page_en, extra_tabs, assignable
    )


PERMISSIONS: dict[str, PermissionDef] = {
    # Ungrouped pages. Default-on for new users. Chat is not a permission.
    "experts": _p("experts", "nav", "专家", "Experts"),
    "tasks": _p("tasks", "nav", "自动化", "Automation"),
    "token_usage": _p("token_usage", "nav", "Token 统计", "Token usage"),
    # --- settings (nav.settings) — listed & default-selected for new users ---
    # Personalization tabs. ``channels`` is also a sidebar item; the rest are
    # tabs on the personalization page. ``agent_plugins`` is per-agent plugin
    # switches — distinct from the admin ``plugins`` catalog.
    "skills": _p(
        "skills",
        "settings",
        "已安装技能",
        "Installed skills",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "skill_builtin": _p(
        "skill_builtin",
        "settings",
        "内置技能",
        "Built-in skills",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "skill_market": _p(
        "skill_market",
        "settings",
        "技能市场",
        "Skill market",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "subagents": _p(
        "subagents",
        "settings",
        "子智能体",
        "Subagents",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "tools": _p(
        "tools",
        "settings",
        "工具",
        "Tools",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "agent_plugins": _p(
        "agent_plugins",
        "settings",
        "插件",
        "Plugins",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "mbti": _p(
        "mbti",
        "settings",
        "MBTI",
        "MBTI",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "memory": _p(
        "memory",
        "settings",
        "记忆",
        "Memory",
        page="personalization",
        page_zh="个性化",
        page_en="Personalization",
    ),
    "channels": _p("channels", "settings", "通道", "Channels"),
    "connectors": _p("connectors", "settings", "连接器", "Connectors", assignable=False),
    "connector_enabled": _p("connector_enabled", "settings", "已启用连接器", "Enabled connectors"),
    "connector_builtin": _p("connector_builtin", "settings", "内置连接器", "Built-in connectors"),
    "connector_custom": _p("connector_custom", "settings", "自定义连接器", "Custom connectors"),
    "skill_packages": _p("skill_packages", "settings", "技能包", "Skill Packages"),
    "knowledge_bases": _p("knowledge_bases", "settings", "知识库", "Knowledge Base"),
    "bridge": _p("bridge", "settings", "云端协同", "Cloud collab"),
    # --- control (nav.control) — page/tab labels ---
    "terminal": _p("terminal", "control", "工作台/终端", "Workbench / Terminal"),
    "browser": _p("browser", "control", "工作台/浏览器", "Workbench / Browser"),
    "desktop": _p("desktop", "control", "远程桌面", "Remote Desktop"),
    "mobile": _p("mobile", "control", "远程手机", "Remote Phone"),
    # --- admin: grouped by page, chip = tab title ---
    "users": _p(
        "users",
        "admin",
        "用户管理",
        "User management",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "user_roles": _p(
        "user_roles",
        "admin",
        "角色管理",
        "Roles",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "user_groups": _p(
        "user_groups",
        "admin",
        "用户分组",
        "Groups",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    # Retired: one chip used to cover every login tab. Still honored on read.
    "sso": _p(
        "sso",
        "admin",
        "单点登录",
        "Single sign-on",
        page="users",
        page_zh="用户",
        page_en="Users",
        assignable=False,
    ),
    "sso_feishu": _p(
        "sso_feishu",
        "admin",
        "飞书登录",
        "Feishu login",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "sso_wecom": _p(
        "sso_wecom",
        "admin",
        "企微登录",
        "WeCom login",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "sso_dingtalk": _p(
        "sso_dingtalk",
        "admin",
        "钉钉登录",
        "DingTalk login",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "sso_oidc": _p(
        "sso_oidc",
        "admin",
        "通用OIDC",
        "Generic OIDC",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "sso_ldap": _p(
        "sso_ldap",
        "admin",
        "LDAP",
        "LDAP",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "providers": _p(
        "providers",
        "admin",
        "云端",
        "Cloud",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "ollama_models": _p(
        "ollama_models",
        "admin",
        "Ollama",
        "Ollama",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "onnx_models": _p(
        "onnx_models",
        "admin",
        "ONNX",
        "ONNX",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "storage_backends": _p("storage_backends", "admin", "存储", "Storage"),
    "plugins": _p(
        "plugins",
        "admin",
        "已安装插件",
        "Installed plugins",
        page="plugins",
        page_zh="插件",
        page_en="Plugins",
    ),
    "plugin_market": _p(
        "plugin_market",
        "admin",
        "插件市场",
        "Plugin market",
        page="plugins",
        page_zh="插件",
        page_en="Plugins",
    ),
    # Retired: one chip used to cover every policy tab.
    "security": _p(
        "security",
        "admin",
        "防护策略",
        "Policy",
        page="security",
        page_zh="安全防护",
        page_en="Security",
        assignable=False,
    ),
    "security_hitl": _p(
        "security_hitl",
        "admin",
        "工具审批",
        "Tool approval",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "security_filesystem": _p(
        "security_filesystem",
        "admin",
        "文件访问",
        "File access",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "security_pii": _p(
        "security_pii",
        "admin",
        "敏感信息",
        "Sensitive data",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "security_tool_guard": _p(
        "security_tool_guard",
        "admin",
        "命令防护",
        "Command guard",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "security_skill_scan": _p(
        "security_skill_scan",
        "admin",
        "技能扫描",
        "Skill scan",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "admin_console": _p(
        "admin_console",
        "admin",
        "审计日志",
        "Audit log",
        page="security",
        page_zh="安全防护",
        page_en="Security",
    ),
    "envs": _p(
        "envs",
        "admin",
        "环境变量",
        "Environment",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "search": _p(
        "search",
        "admin",
        "搜索引擎",
        "Search engines",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "knowledge_settings": _p(
        "knowledge_settings",
        "admin",
        "知识库设置",
        "Knowledge-base settings",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "model_generation": _p(
        "model_generation",
        "admin",
        "生成模型",
        "Generation models",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "model_decision": _p(
        "model_decision",
        "admin",
        "决策模型",
        "Decision models",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "voice": _p(
        "voice",
        "admin",
        "语音模型",
        "Voice models",
        page="models",
        page_zh="模型",
        page_en="Models",
    ),
    "observability": _p(
        "observability",
        "admin",
        "可观测",
        "Observability",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "backup": _p(
        "backup",
        "admin",
        "备份与恢复",
        "Backup & restore",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "tls": _p(
        "tls",
        "admin",
        "HTTPS",
        "HTTPS",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "update": _p(
        "update",
        "admin",
        "应用更新",
        "Updates",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
    "captcha": _p(
        "captcha",
        "admin",
        "登录验证码",
        "Login captcha",
        page="advanced",
        page_zh="应用设置",
        page_en="App settings",
    ),
}

ALL_PERMISSION_KEYS: set[str] = set(PERMISSIONS)

ASSIGNABLE_PERMISSION_KEYS: set[str] = {key for key, perm in PERMISSIONS.items() if perm.assignable}

# Retired umbrellas. Holding the parent grants every tab; holding any tab
# still satisfies routes that check the parent (``connectors``).
LEGACY_GRANTS: dict[str, tuple[str, ...]] = {
    "sso": ("sso_feishu", "sso_wecom", "sso_dingtalk", "sso_oidc", "sso_ldap"),
    "security": (
        "security_hitl",
        "security_filesystem",
        "security_pii",
        "security_tool_guard",
        "security_skill_scan",
    ),
    "connectors": ("connector_enabled", "connector_builtin", "connector_custom"),
}

# One-time grant expansion. ``retire`` drops the parent so a later uncheck sticks.
# Retired parents stay in ``LEGACY_GRANTS`` and still imply their tabs at check time.
PAGE_TAB_EXPANSIONS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("sso", LEGACY_GRANTS["sso"], True),
    ("security", LEGACY_GRANTS["security"], True),
    ("connectors", LEGACY_GRANTS["connectors"], True),
    ("users", ("user_roles", "user_groups"), False),
    ("plugins", ("plugin_market",), False),
    ("providers", ("model_generation", "model_decision"), False),
    ("skills", ("skill_builtin", "skill_market"), False),
)

# Pre-checked for new users. Stored explicitly — not granted unless written.
# ``nav`` pages used to be open to everyone, so they stay in the default set.
BASELINE_PERMISSIONS: set[str] = {
    key
    for key, perm in PERMISSIONS.items()
    if perm.assignable and perm.category in {"settings", "nav"}
}


def expand_permission_grants(keys: list[str]) -> list[str]:
    """Replace retired umbrella keys with the tab keys they cover.

    Assignable keys pass through. Unknown keys are dropped; callers that must
    reject them use ``validate_permission_keys`` first.
    """
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        additions = LEGACY_GRANTS.get(key, (key,))
        for item in additions:
            perm = PERMISSIONS.get(item)
            if perm is None or not perm.assignable or item in seen:
                continue
            seen.add(item)
            out.append(item)
    return out


def user_has_permission(user: PermissionUser, key: str) -> bool:
    """Return True if ``user`` may access the module ``key``.

    Unknown keys are denied. ``admin`` bypasses everything. A retired umbrella
    still grants its tabs, and any tab satisfies the umbrella.
    """
    if key not in PERMISSIONS:
        return False
    if user.is_admin:
        return True
    held = set(user.permissions or [])
    if key in held:
        return True
    for parent, children in LEGACY_GRANTS.items():
        if key in children and parent in held:
            return True
        if key == parent and not held.isdisjoint(children):
            return True
    return False


def validate_permission_keys(keys: list[str]) -> list[str]:
    """Return a deduped assignable list or raise ``ValueError`` on unknown keys.

    Retired umbrellas are accepted and expanded into their tab keys.
    """
    unknown = sorted({k for k in keys if k not in PERMISSIONS})
    if unknown:
        raise ValueError(f"unknown permission keys: {unknown}")
    return expand_permission_grants(keys)


def effective_permissions(user: PermissionUser) -> list[str]:
    """Permissions to expose on ``/auth/me`` / login (admin gets the picker catalog)."""
    if user.is_admin:
        return sorted(ASSIGNABLE_PERMISSION_KEYS)
    return expand_permission_grants(list(user.permissions or []))
