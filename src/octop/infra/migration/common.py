"""Pieces the OpenClaw and Hermes readers share."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from octop.infra.migration.plan import McpImport, MigrationPlan, ProviderImport, SkillImport

# Hosted providers both tools know by id: (Octop kind, base URL, API key variables).
# Base URLs match Octop's own provider presets.
KNOWN_PROVIDERS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "anthropic": ("anthropic", "https://api.anthropic.com/v1", ("ANTHROPIC_API_KEY",)),
    "openai": ("openai", "https://api.openai.com/v1", ("OPENAI_API_KEY",)),
    "openrouter": ("openai", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
    "deepseek": ("openai", "https://api.deepseek.com/v1", ("DEEPSEEK_API_KEY",)),
    "google": (
        "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
    "groq": ("openai", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",)),
    "zai": (
        "openai",
        "https://api.z.ai/api/paas/v4",
        ("ZAI_API_KEY", "GLM_API_KEY", "Z_AI_API_KEY"),
    ),
    "moonshot": ("openai", "https://api.moonshot.ai/v1", ("MOONSHOT_API_KEY", "KIMI_API_KEY")),
    "minimax": ("openai", "https://api.minimax.io/v1", ("MINIMAX_API_KEY",)),
    "dashscope": (
        "openai",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ("DASHSCOPE_API_KEY",),
    ),
}

_SKILL_SCAN_DEPTH = 4
_SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})
_MCP_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")
_HTTP_TRANSPORTS = frozenset({"streamable-http", "streamable_http", "http"})


def known_provider(provider_id: str, env: Mapping[str, str], model: str) -> ProviderImport | None:
    """A hosted provider with the key found in ``env``, or None without a key."""
    kind, base_url, key_vars = KNOWN_PROVIDERS[provider_id]
    api_key = next((env[name] for name in key_vars if env.get(name)), None)
    if not api_key:
        return None
    return ProviderImport(
        name=provider_id, kind=kind, base_url=base_url, api_key=api_key, models=(model,)
    )


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def discover_skills(root: Path, *, skip: frozenset[str] = frozenset()) -> list[SkillImport]:
    """Every directory holding a ``SKILL.md`` under ``root``, grouped layouts included."""
    found: list[SkillImport] = []
    if not root.is_dir():
        return found

    def walk(directory: Path, depth: int) -> None:
        if (directory / "SKILL.md").is_file():
            if directory != root and directory.name not in skip:
                found.append(SkillImport(slug=directory.name, source=directory))
            return
        if depth >= _SKILL_SCAN_DEPTH:
            return
        for child in sorted(directory.iterdir()):
            hidden = child.name.startswith(".") or child.name in _SKIPPED_DIRS
            if child.is_dir() and not hidden:
                walk(child, depth + 1)

    walk(root, 0)
    return found


def add_skills(plan: MigrationPlan, skills: list[SkillImport]) -> None:
    """Append skills; the first root to provide a name wins."""
    taken = {skill.slug for skill in plan.skills}
    for skill in skills:
        if skill.slug not in taken:
            taken.add(skill.slug)
            plan.skills.append(skill)


def add_mcp_server(
    plan: MigrationPlan,
    name: str,
    raw: Any,
    *,
    resolve: Any,
    default_remote_transport: str,
) -> None:
    """Translate one MCP server entry into Octop's custom MCP shape.

    ``resolve`` substitutes the source tool's ``${VAR}`` references and leaves
    unknown ones as written.
    """
    if not isinstance(raw, dict):
        return
    safe_name = _MCP_NAME_UNSAFE.sub("-", name).strip("-") or "mcp-server"
    enabled = raw.get("enabled") is not False and raw.get("disabled") is not True
    spec: dict[str, Any]
    if raw.get("command"):
        spec = {"transport": "stdio", "command": str(raw["command"])}
        if isinstance(raw.get("args"), list):
            spec["args"] = [resolve(str(arg)) for arg in raw["args"]]
        env = {str(k): resolve(str(v)) for k, v in as_dict(raw.get("env")).items()}
        if env:
            spec["env"] = env
    elif raw.get("url"):
        transport = str(raw.get("transport") or raw.get("type") or default_remote_transport)
        if transport not in _HTTP_TRANSPORTS:
            plan.note("mcp_sse_unsupported", name=name)
            return
        spec = {"transport": "streamable_http", "url": resolve(str(raw["url"]))}
        headers = {str(k): resolve(str(v)) for k, v in as_dict(raw.get("headers")).items()}
        if headers:
            spec["headers"] = headers
    else:
        return
    if not enabled:
        spec["enabled"] = False
    plan.mcp_servers.append(McpImport(name=safe_name, spec=spec))


def count_cron_jobs(path: Path) -> int:
    """Jobs in a ``cron/jobs.json`` (``{"jobs": [...]}``, a bare list, or an id map)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    jobs = data.get("jobs") if isinstance(data, dict) else data
    return len(jobs) if isinstance(jobs, (list, dict)) else 0
