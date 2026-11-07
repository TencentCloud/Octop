"""Request-time OAuth for cached custom Streamable HTTP MCP tools."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import httpx

from octop.infra.connectors.custom_mcp import oauth_tokens_from_spec, server_enabled
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop.infra.connectors.service import ConnectorService


class CustomMcpOAuthAuth(httpx.Auth):
    """Read the encrypted grant on every request, including from already loaded tools."""

    def __init__(
        self,
        service: ConnectorService,
        *,
        owner_user_id: int,
        user_id: int,
        server_name: str,
        url: str,
    ) -> None:
        self._service = service
        self._owner_user_id = owner_user_id
        self._user_id = user_id
        self._server_name = server_name
        self._url = url

    def _check_access(self, spec: dict[str, Any]) -> None:
        if (
            not spec
            or not server_enabled(spec)
            or spec.get("transport") != "streamable_http"
            or spec.get("url") != self._url
            or (self._user_id != self._owner_user_id and spec.get("shared") is not True)
        ):
            raise OctopError.localized(ErrorCode.FORBIDDEN)

    async def _token(self, *, rejected_token: str | None = None) -> str:
        spec = self._service.get_custom_servers(self._owner_user_id).get(self._server_name, {})
        self._check_access(spec)
        spec = await self._service.ensure_fresh_custom_server(
            self._owner_user_id, self._server_name, rejected_token=rejected_token
        )
        # Configuration or sharing may have changed while the refresh was in flight.
        self._check_access(spec)
        token = str(oauth_tokens_from_spec(spec).get("access_token") or "").strip()
        if not token:
            raise OctopError.localized(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                details={"server_name": self._server_name, "oauth_required": True},
            )
        return token

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        if request.url != httpx.URL(self._url):
            raise OctopError.localized(ErrorCode.FORBIDDEN)
        await request.aread()
        token = await self._token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return

        await response.aread()
        token = await self._token(rejected_token=token)
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code == 401:
            self._service.reject_custom_server_token(self._owner_user_id, self._server_name, token)
