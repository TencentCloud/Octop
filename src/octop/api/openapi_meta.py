"""OpenAPI metadata for Scalar API docs."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from octop.api.deps import is_jwt_exempt_path

API_DESCRIPTION = """\
**Octop** is a smarter, self-hosted AI assistant for multiple users and agents. All routes are served under `/api`.

## Authentication

Most endpoints require a JWT bearer token:

1. Complete initial setup via `/api/setup/*` (first install only).
2. `POST /api/auth/login` with `username` and `password`.
3. Send `Authorization: Bearer <access_token>` on subsequent requests.

Public endpoints (no token): `/api/docs`, `/api/openapi.json`, `/api/health`,
`/api/setup/*`, `/api/auth/login`, `/api/connectors/oauth/callback`, and
`/api/internal/mcp/*`.

## Agent scope

Many agent-scoped routes use the agent ID in the URL path (`/api/agents/{agent_id}/…`).
The caller must own the agent unless they are an admin.

## Streaming chat

Dashboard live turns use **WebSocket** at `/api/agents/{agent_id}/chat/ws` (pass JWT as
`?token=` query param). Send `{"type":"user_turn", ...}` frames; the server replies with JSON
chunks matching the harness stream format, ending with `{"type":"done"}` or
`{"type":"error","message":"..."}`.

HITL resume still uses `POST /api/agents/{agent_id}/chat/hitl/resume` (SSE).
"""

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "setup",
        "description": "First-run wizard: create the admin user and optional LLM provider.",
    },
    {"name": "auth", "description": "Sign in, sign out, and manage the current user profile."},
    {"name": "health", "description": "Liveness probe for load balancers and monitoring."},
    {"name": "users", "description": "Admin user management (create, disable, reset passwords)."},
    {
        "name": "agents",
        "description": "Create and configure AI agents; start, stop, and inspect runtime status.",
    },
    {
        "name": "chat",
        "description": "Dashboard chat: SSE streaming, threads, and conversation history.",
    },
    {
        "name": "slash",
        "description": "Slash command metadata for composer menus and inline help.",
    },
    {
        "name": "connectors",
        "description": "Third-party integrations (Notion, Figma, …) exposed as MCP servers.",
    },
    {
        "name": "internal-mcp",
        "description": "Internal MCP gateway used by harness agents (no dashboard auth).",
    },
    {
        "name": "channels",
        "description": "Instant-messaging bridges (WeCom, Feishu, Telegram, …) per agent.",
    },
    {
        "name": "cron",
        "description": "Scheduled prompts that run against an agent on a cron trigger.",
    },
    {"name": "envs", "description": "Environment variable presets for agents and workspaces."},
    {"name": "providers", "description": "LLM provider configuration and active model selection."},
    {"name": "voice", "description": "Speech-to-text and text-to-speech provider configuration."},
    {
        "name": "observability",
        "description": "LLM observability integrations (Langfuse tracing).",
    },
    {
        "name": "tls",
        "description": "Let's Encrypt HTTPS certificate issuance and status.",
    },
    {
        "name": "security",
        "description": "Agent security policy: tool approval (HITL), command guard rules, filesystem rules, PII redaction.",
    },
    {"name": "admin", "description": "Server-wide admin operations (audit log, storage, usage)."},
    {"name": "storage-backends", "description": "User-visible remote storage backend connections."},
    {
        "name": "filesystem",
        "description": "Host filesystem directory browsing for dashboard forms.",
    },
    {"name": "mbti", "description": "MBTI persona presets applied to agent personality."},
    {"name": "experts", "description": "Bundled expert templates for creating specialized agents."},
    {"name": "workspace", "description": "Agent workspace file tree: list, read, write, upload."},
    {"name": "agent_files", "description": "Agent-owned configuration files (SOUL.md, skills, …)."},
    {"name": "usage", "description": "Token usage summaries for billing and dashboards."},
    {"name": "skills", "description": "Per-agent skills and Skill Hub marketplace search."},
    {
        "name": "subagents",
        "description": "Per-agent subagent definitions (agents/*.md) and bundled catalog install.",
    },
    {"name": "terminal", "description": "AI-assisted remote terminal sessions."},
    {"name": "update", "description": "In-place server update checks and apply flow."},
    {
        "name": "browser",
        "description": "Remote browser sessions: navigate, screenshot, live stream.",
    },
    {
        "name": "desktop",
        "description": "Remote OS desktop stream and input injection (admin only).",
    },
    {"name": "ollama", "description": "Local Ollama model discovery and download management."},
]

_BEARER_SCHEME = {
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "description": "JWT from `POST /api/auth/login` (`access_token` field).",
}


def configure_openapi(app: FastAPI) -> None:
    """Attach tag descriptions, API intro, and Bearer security to the OpenAPI schema."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=API_DESCRIPTION,
            routes=app.routes,
            tags=OPENAPI_TAGS,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["BearerAuth"] = _BEARER_SCHEME

        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith("/api/") or is_jwt_exempt_path(path):
                continue
            for operation in path_item.values():
                if isinstance(operation, dict) and "security" not in operation:
                    operation["security"] = [{"BearerAuth": []}]

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
