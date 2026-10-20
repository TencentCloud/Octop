"""Per-invocation HTTP session header injection.

Some relays require a stable per-conversation header. ``ProviderConfig.session_header``
names that header; the value is the current ``thread_id`` (ContextVar), set for the
duration of ``HarnessAgent.call`` / ``stream`` / ``resume``.

LangChain ``default_headers`` are bound to the cached chat-model client, so this
module attaches an httpx request hook on a *dedicated* client instead of mutating
shared langchain default clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

import httpx

_CURRENT_SESSION_ID: ContextVar[str | None] = ContextVar("harness_session_id", default=None)
_SESSION_HTTP_CLIENTS_ATTR = "_harness_session_http_clients"


def current_session_id() -> str:
    """Return the active invocation session id, or a throwaway UUID if unset."""
    value = _CURRENT_SESSION_ID.get()
    if value:
        return value
    return uuid.uuid4().hex


@contextmanager
def session_header_scope(thread_id: str | None) -> Iterator[str]:
    """Bind *thread_id* for the current task.

    An empty *thread_id* keeps an already-active outer scope instead of minting
    a throwaway id that would stomp the invocation's conversation id.
    """
    incoming = (thread_id or "").strip()
    existing = _CURRENT_SESSION_ID.get()
    if not incoming:
        if existing:
            yield existing
            return
        incoming = uuid.uuid4().hex
    token: Token[str | None] = _CURRENT_SESSION_ID.set(incoming)
    try:
        yield incoming
    finally:
        _CURRENT_SESSION_ID.reset(token)


def _stamp_session_header(request: httpx.Request, name: str, needle: str) -> None:
    if any(key.lower() == needle for key in request.headers):
        return
    request.headers[name] = current_session_id()


def install_request_hook(client: httpx.Client | httpx.AsyncClient, header_name: str) -> None:
    """Append a request hook that sets *header_name* from :func:`current_session_id`.

    Existing values of *header_name* (any casing) are left untouched so user-supplied
    ``ProviderConfig.headers`` always win.

    ``httpx.AsyncClient`` awaits every request hook; a sync hook that returns
    ``None`` becomes ``TypeError: 'NoneType' object can't be awaited`` and the
    OpenAI SDK surfaces that as ``APIConnectionError: Connection error.``
    """
    name = header_name.strip()
    if not name:
        return
    needle = name.lower()

    hooks = client.event_hooks.setdefault("request", [])
    if isinstance(client, httpx.AsyncClient):

        async def _async_hook(request: httpx.Request) -> None:
            _stamp_session_header(request, name, needle)

        hooks.append(_async_hook)
        return

    def _sync_hook(request: httpx.Request) -> None:
        _stamp_session_header(request, name, needle)

    hooks.append(_sync_hook)


def session_http_clients(header_name: str) -> tuple[httpx.Client, httpx.AsyncClient]:
    """Dedicated httpx clients with the session-header hook installed.

    ``timeout=None`` matches langchain-openai / langchain-anthropic (no 5s
    httpx default). ``trust_env=True`` keeps HTTP(S)_PROXY / ALL_PROXY.
    """
    sync_client = httpx.Client(timeout=None, trust_env=True)
    async_client = httpx.AsyncClient(timeout=None, trust_env=True)
    install_request_hook(sync_client, header_name)
    install_request_hook(async_client, header_name)
    return sync_client, async_client


def attach_session_http_clients(
    instance: Any,
    sync_client: httpx.Client,
    async_client: httpx.AsyncClient,
) -> None:
    """Remember dedicated clients on *instance* so shutdown can close them."""
    with contextlib.suppress(AttributeError, TypeError):
        object.__setattr__(instance, _SESSION_HTTP_CLIENTS_ATTR, (sync_client, async_client))


def close_session_http_clients(instance: Any) -> None:
    """Synchronously close dedicated session-header httpx clients on *instance*."""
    pair = getattr(instance, _SESSION_HTTP_CLIENTS_ATTR, None)
    if not isinstance(pair, tuple) or len(pair) != 2:
        return
    with contextlib.suppress(AttributeError, TypeError):
        object.__setattr__(instance, _SESSION_HTTP_CLIENTS_ATTR, None)
    sync_client, async_client = pair
    with contextlib.suppress(Exception):
        sync_client.close()
    aclose = getattr(async_client, "aclose", None)
    if not callable(aclose):
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        with contextlib.suppress(Exception):
            asyncio.run(aclose())


async def aclose_session_http_clients(instance: Any) -> None:
    """Async close dedicated session-header httpx clients on *instance*."""
    pair = getattr(instance, _SESSION_HTTP_CLIENTS_ATTR, None)
    if not isinstance(pair, tuple) or len(pair) != 2:
        return
    with contextlib.suppress(AttributeError, TypeError):
        object.__setattr__(instance, _SESSION_HTTP_CLIENTS_ATTR, None)
    sync_client, async_client = pair
    with contextlib.suppress(Exception):
        sync_client.close()
    aclose = getattr(async_client, "aclose", None)
    if callable(aclose):
        with contextlib.suppress(Exception):
            await aclose()


def bind_anthropic_session_header(instance: Any, header_name: str) -> None:
    """Replace ChatAnthropic cached HTTP clients with hooked dedicated ones.

    langchain-anthropic shares process-wide httpx clients via ``lru_cache``; the
    hook must not be installed on those.
    """
    params = getattr(instance, "_client_params", None)
    if not isinstance(params, dict):
        return
    try:
        import anthropic
    except ImportError:  # pragma: no cover - anthropic ships with langchain-anthropic
        return
    sync_http, async_http = session_http_clients(header_name)
    instance.__dict__["_client"] = anthropic.Client(**params, http_client=sync_http)
    instance.__dict__["_async_client"] = anthropic.AsyncClient(**params, http_client=async_http)
    attach_session_http_clients(instance, sync_http, async_http)


__all__ = [
    "aclose_session_http_clients",
    "attach_session_http_clients",
    "bind_anthropic_session_header",
    "close_session_http_clients",
    "current_session_id",
    "install_request_hook",
    "session_header_scope",
    "session_http_clients",
]
