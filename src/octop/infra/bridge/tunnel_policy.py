"""Path policy for Bridge HTTP tunnel requests against the local ASGI app."""

from __future__ import annotations

import re

# Only agent-scoped product surfaces may be executed on behalf of the connection
# owner. Management / auth / bridge control planes stay local-only.
_AGENT_COLLECTION = re.compile(r"^/api/agents/?$")
_AGENT_RESOURCE = re.compile(
    r"^/api/agents/"
    r"(?:bridge:[^/]+|[^/]+)"
    r"(?:/(?:threads|history|uploads|avatar|icon|chat|messages|files|workspace"
    r"|attachments|media|turns|memory|skills|tools|tool-settings|mbti|persona"
    r"|channels|cron|config|state|status|welcome|members|subagents|reload|acp"
    r")(?:/.*)?)?$"
)

# Composer read-only surfaces for remote chat (models + knowledge pickers).
# Write / document / admin provider routes stay denied.
_COMPOSER_READONLY = re.compile(
    r"^/api/(?:"
    r"providers/resolved|"
    r"providers/active-model|"
    r"knowledge-bases|"
    r"knowledge-bases/capability"
    r")$"
)

# Chat dock browser viewer (peer harness). Install / record-replay stay denied.
_BROWSER_VIEWER_GET = re.compile(r"^/api/browser/(?:env-status|harness-sessions)$")
_BROWSER_HANDOFF = re.compile(r"^/api/browser/sessions/[^/]+/handoff$")

# Experts surfaces that are not under /api/agents/{id} but still agent-scoped
# on the peer (header or /plugins/agents/{id} path).
_PLUGIN_AGENT = re.compile(r"^/api/plugins/agents/(?:bridge:[^/]+|[^/]+)(?:/tools)?$")
_MBTI = re.compile(r"^/api/mbti(?:/.*)?$")
_SUBAGENT_CATALOG = re.compile(r"^/api/subagent-catalog(?:/.*)?$")
_ACP_GLOBAL = re.compile(r"^/api/acp(?:/[^/]+)?$")
_CRON_SETTINGS = re.compile(r"^/api/cron/settings$")
_CONNECTOR_INSTANCES_LIST = re.compile(r"^/api/connector-instances$")


def is_tunnel_path_allowed(method: str, path: str) -> bool:
    """Return True when ``method`` + ``path`` may run via an inbound tunnel."""
    verb = (method or "GET").upper()
    raw = (path or "").split("?", 1)[0].strip() or "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    # Normalize trailing slash except root.
    if len(raw) > 1:
        raw = raw.rstrip("/")

    if _AGENT_COLLECTION.fullmatch(raw):
        return verb == "GET"

    if _COMPOSER_READONLY.fullmatch(raw):
        return verb == "GET"

    if _BROWSER_VIEWER_GET.fullmatch(raw):
        return verb == "GET"

    if _BROWSER_HANDOFF.fullmatch(raw):
        return verb == "POST"

    if _AGENT_RESOURCE.fullmatch(raw):
        return verb in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}

    if _PLUGIN_AGENT.fullmatch(raw):
        return verb in {"GET", "PATCH"}

    if _MBTI.fullmatch(raw):
        return verb in {"GET", "POST"}

    if _SUBAGENT_CATALOG.fullmatch(raw):
        return verb == "GET"

    if _ACP_GLOBAL.fullmatch(raw):
        return verb in {"GET", "PUT", "DELETE"}

    if _CRON_SETTINGS.fullmatch(raw):
        return verb == "GET"

    if _CONNECTOR_INSTANCES_LIST.fullmatch(raw):
        return verb == "GET"

    return False
