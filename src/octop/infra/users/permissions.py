"""Module-level permission catalog and checks.

A permission is a module key (e.g. ``"browser"``, ``"users"``). Possessing a
key grants access to that module's management page and write/configure actions.
Read access and agent use in chat are never gated. ``admin`` bypasses all.

Categories mirror dashboard nav groups: ``settings`` / ``control`` / ``admin``.
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
) -> PermissionDef:
    return PermissionDef(key, category, label_zh, label_en, page, page_zh, page_en, extra_tabs)


PERMISSIONS: dict[str, PermissionDef] = {
    # --- settings (nav.settings) — listed & default-selected for new users ---
    "channels": _p("channels", "settings", "通道", "Channels"),
    "connectors": _p("connectors", "settings", "连接器", "Connectors"),
    "skill_packages": _p("skill_packages", "settings", "技能包", "Skill Packages"),
    "knowledge_bases": _p("knowledge_bases", "settings", "知识库", "Knowledge Base"),
    # --- control (nav.control) — page/tab labels ---
    "terminal": _p("terminal", "control", "工作台/终端", "Workbench / Terminal"),
    "browser": _p("browser", "control", "工作台/浏览器", "Workbench / Browser"),
    "desktop": _p("desktop", "control", "远程桌面", "Remote Desktop"),
    "mobile": _p("mobile", "control", "远程手机", "Remote Phone"),
    # --- admin: grouped by page, chip = tab title ---
    "users": _p(
        "users",
        "admin",
        "内置用户",
        "Local users",
        page="users",
        page_zh="用户",
        page_en="Users",
    ),
    "sso": _p(
        "sso",
        "admin",
        "单点登录",
        "Single sign-on",
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
        "已安装",
        "Installed",
        page="plugins",
        page_zh="插件",
        page_en="Plugins",
    ),
    "security": _p(
        "security",
        "admin",
        "防护策略",
        "Policy",
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
}

ALL_PERMISSION_KEYS: set[str] = set(PERMISSIONS)

# Settings-group keys: shown in the picker and pre-checked for new users.
# They are still stored explicitly — not silently granted without being written.
BASELINE_PERMISSIONS: set[str] = {key for key, p in PERMISSIONS.items() if p.category == "settings"}


def user_has_permission(user: PermissionUser, key: str) -> bool:
    """Return True if ``user`` may access the module ``key``.

    Unknown keys are denied. ``admin`` bypasses everything.
    """
    if key not in PERMISSIONS:
        return False
    if user.is_admin:
        return True
    return key in (user.permissions or [])


def validate_permission_keys(keys: list[str]) -> list[str]:
    """Return a deduped list or raise ``ValueError`` on unknown keys."""
    unknown = sorted({k for k in keys if k not in PERMISSIONS})
    if unknown:
        raise ValueError(f"unknown permission keys: {unknown}")
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def effective_permissions(user: PermissionUser) -> list[str]:
    """Permissions to expose on ``/auth/me`` / login (admin gets the full catalog)."""
    if user.is_admin:
        return sorted(ALL_PERMISSION_KEYS)
    return list(user.permissions or [])
