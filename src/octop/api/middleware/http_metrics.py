"""HTTP server request metrics (``http.server.request.duration``)."""

from __future__ import annotations

import re
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from octop.infra.telemetry import exception_type, record_http_request

_CONVERTER = re.compile(r"\{(\w+):\w+\}")

# FastAPI's private scope keys (only used to read the prefixed route template).
try:
    from fastapi.routing import _FASTAPI_EFFECTIVE_ROUTE_CONTEXT_KEY as _EFFECTIVE_ROUTE_CONTEXT_KEY
    from fastapi.routing import _FASTAPI_SCOPE_KEY
except ImportError:  # older FastAPI: ``route.path`` already carries the prefix
    _FASTAPI_SCOPE_KEY = "fastapi"
    _EFFECTIVE_ROUTE_CONTEXT_KEY = "effective_route_context"


class HttpMetricsMiddleware:
    """Pure-ASGI so streaming responses (SSE) are timed to the end without buffering."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status: int | None = None
        error: BaseException | None = None

        async def _send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except BaseException as exc:
            error = exc
            raise
        finally:
            _record(scope, time.perf_counter() - started, status, error)


def _record(
    scope: Scope, duration_s: float, status: int | None, error: BaseException | None
) -> None:
    error_type = ""
    if error is not None and isinstance(error, Exception):
        error_type = exception_type(error)
        if status is None:
            status = 500  # the server-error handler answers with a 500
    elif status is not None and status >= 500:
        error_type = str(status)
    record_http_request(
        method=str(scope.get("method", "")),
        scheme=str(scope.get("scheme", "http")),
        duration_s=duration_s,
        route=_route_template(scope),
        status_code=status,
        error_type=error_type,
    )


def _route_template(scope: Scope) -> str:
    """Matched route template including router prefixes (low cardinality); ``""`` if unmatched.

    Newer FastAPI keeps router prefixes outside ``route.path`` and records the fully
    prefixed template on a private scope entry; older versions bake the prefix into
    ``route.path``. Prefer the former, fall back to the latter.
    """
    fastapi_scope: Any = scope.get(_FASTAPI_SCOPE_KEY)
    if isinstance(fastapi_scope, dict):
        context = fastapi_scope.get(_EFFECTIVE_ROUTE_CONTEXT_KEY)
        path_format = getattr(context, "path_format", None)
        if isinstance(path_format, str) and path_format:
            return path_format
    path = getattr(scope.get("route"), "path", None)
    # ``{name:path}`` -> ``{name}``, matching the prefixed form above.
    return _CONVERTER.sub(r"{\1}", path) if isinstance(path, str) else ""


def install(app: Any) -> None:
    app.add_middleware(HttpMetricsMiddleware)
