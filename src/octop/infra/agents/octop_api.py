"""``octop_api``: call the Octop HTTP API as the user of the current conversation.

Identity comes from the turn (``configurable.user`` / ``configurable.agent_id``,
set by Octop, never by the model). Each call mints a short-lived ``agent`` token
for that user (:mod:`octop.infra.auth.agent_access`) and sends the request to the
running app in-process, so the token never enters the model context and no port
or TLS setup is involved. Reads run freely; writes go through tool approval.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import httpx
from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.infra.auth.agent_access import READ_METHODS, agent_request_allowed, mint_agent_token

TOOL_NAME = "octop_api"

_TIMEOUT_SECONDS = 60.0
_MAX_RESPONSE_CHARS = 20_000
_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

_DESCRIPTION = (
    "Call the Octop HTTP API as the user you are talking to, with exactly that user's "
    "permissions. path starts with /api/ and may include a query string, e.g. "
    "GET /api/agents or GET /api/cron/jobs?agent_id=... . "
    "GET /api/openapi.json lists every route (it is large; read it once and keep what you need). "
    "Sign-in, passwords, MFA, setup, TLS, security settings, and the terminal are not available. "
    "GET runs at once; POST, PUT, PATCH, and DELETE ask the user to approve first, so say "
    "what the call will change before making it."
)

_app: Any = None


def bind_loopback_app(app: Any) -> None:
    """Remember the running ASGI app (called once by the HTTP layer at build time)."""
    global _app
    _app = app


def _turn_identity() -> tuple[int, str]:
    cfg = get_config().get("configurable") or {}
    user_raw = cfg.get("user")
    agent_id = cfg.get("agent_id")
    if user_raw is None or not agent_id:
        raise PermissionError("no signed-in user for this conversation")
    return int(user_raw), str(agent_id)


def is_write_call(req: Any) -> bool:
    """``interrupt_on`` predicate: approve everything except reads."""
    tool_call = getattr(req, "tool_call", None) or {}
    args = tool_call.get("args") if isinstance(tool_call, dict) else None
    method = args.get("method") if isinstance(args, dict) else None
    return str(method or "GET").upper() not in READ_METHODS


def write_interrupt_on() -> dict[str, Any]:
    """Always ask before a write, even when global HITL is off."""
    return {TOOL_NAME: {"allowed_decisions": ["approve", "reject"], "when": is_write_call}}


def _render(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    text = json.dumps({"status": response.status_code, "body": body}, ensure_ascii=False)
    if len(text) > _MAX_RESPONSE_CHARS:
        text = text[:_MAX_RESPONSE_CHARS] + "… (truncated; narrow the request with query params)"
    return text


def build_octop_api_tool(repos: Any) -> StructuredTool:
    """Build the tool; ``repos`` needs ``user_repo`` and ``secret_repo``."""

    async def octop_api(
        method: Annotated[str, Field(description="HTTP method: " + ", ".join(_METHODS))],
        path: Annotated[str, Field(description="API path starting with /api/, query allowed")],
        body: Annotated[
            dict[str, Any] | list[Any] | None,
            Field(description="JSON request body for POST, PUT, or PATCH"),
        ] = None,
    ) -> str:
        verb = method.strip().upper()
        route = path.strip()
        if verb not in _METHODS:
            return json.dumps({"error": f"method must be one of {', '.join(_METHODS)}"})
        if not agent_request_allowed(verb, route.split("?", 1)[0]):
            return json.dumps({"error": f"{route} is not available to agents"})
        if _app is None:
            return json.dumps({"error": "the Octop API is not running in this process"})
        try:
            user_id, agent_id = _turn_identity()
            token = mint_agent_token(repos, user_id=user_id, agent_id=agent_id)
        except (PermissionError, RuntimeError) as exc:
            return json.dumps({"error": str(exc)})
        transport = httpx.ASGITransport(app=_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://octop.internal") as c:
            try:
                response = await asyncio.wait_for(
                    c.request(
                        verb,
                        route,
                        json=body,
                        headers={"Authorization": f"Bearer {token}"},
                    ),
                    timeout=_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                return json.dumps({"error": f"no response within {int(_TIMEOUT_SECONDS)} s"})
        return _render(response)

    return StructuredTool.from_function(
        coroutine=octop_api,
        name=TOOL_NAME,
        description=_DESCRIPTION,
    )
