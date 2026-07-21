"""Require JWT for all /api/* routes except an explicit allowlist.

Validated users are cached on ``request.state.octop_user`` so route-level
``Depends(current_user)`` can reuse the result without re-decoding.

When the access token is past the sliding-renew threshold, a fresh token is
attached as ``X-Octop-Access-Token`` on the response.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from octop.api.deps import (
    ACCESS_TOKEN_RESPONSE_HEADER,
    authenticate_request,
    extract_raw_token,
    is_jwt_exempt_request,
    maybe_sliding_renew_token,
)
from octop.infra.errors import OctopError

_INSTALL_ATTR = "_octop_jwt_auth_installed"


def install(app: Any, server: Any) -> None:
    if getattr(app, _INSTALL_ATTR, False):
        return
    setattr(app, _INSTALL_ATTR, True)

    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def _jwt_auth(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        path = request.url.path
        if not path.startswith("/api/") or is_jwt_exempt_request(request):
            return await call_next(request)

        raw = extract_raw_token(
            authorization=request.headers.get("authorization"),
            access_token=request.query_params.get("access_token"),
        )
        try:
            request.state.octop_user = authenticate_request(request, server)
        except OctopError as exc:
            return JSONResponse(status_code=exc.status, content=exc.to_envelope())

        response = await call_next(request)
        if raw is not None:
            try:
                renewed = maybe_sliding_renew_token(server, raw, request.state.octop_user)
            except OctopError:
                renewed = None
            if renewed:
                response.headers[ACCESS_TOKEN_RESPONSE_HEADER] = renewed
        return response
