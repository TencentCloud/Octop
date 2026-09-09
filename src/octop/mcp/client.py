"""Authenticated HTTP client for the Octop connector-management MCP server."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

_TOKEN_RESPONSE_HEADER = "X-Octop-Access-Token"


class OctopApiError(RuntimeError):
    """An Octop API request failed."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"Octop API error {status_code} {code}: {message}")


class OctopApiClient:
    """Call the running Octop API without bypassing its permission checks."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Accept-Language": "zh"}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout or self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"cannot reach Octop at {self.base_url}; make sure `octop run` is active: {exc}"
            ) from exc

        renewed = response.headers.get(_TOKEN_RESPONSE_HEADER)
        if renewed:
            self.token = renewed
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return {"ok": True}
            return response.json()

        code = "HTTP_ERROR"
        message = response.text or response.reason_phrase
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                message = str(error.get("message") or message)
            else:
                code = str(payload.get("code") or code)
                message = str(payload.get("message") or payload.get("detail") or message)
        raise OctopApiError(status_code=response.status_code, code=code, message=message)

    async def get_status(self) -> dict[str, Any]:
        health = self._as_dict(await self.request("GET", "/api/health"))
        user = self._as_dict(await self.request("GET", "/api/auth/me"))
        return {
            "ok": bool(health.get("ok")),
            "database_ready": bool(health.get("db")),
            "user": {
                "id": user.get("id"),
                "username": user.get("username"),
                "role": user.get("role"),
                "permissions": user.get("permissions", []),
            },
            "base_url": self.base_url,
        }

    async def list_connectors(self) -> list[dict[str, Any]]:
        rows = self._as_list(await self.request("GET", "/api/connector-instances"))
        return [self._safe_connector(row) for row in rows]

    async def add_http_mcp_connector(
        self,
        *,
        name: str,
        url: str,
        display_name: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
        default_open: bool = False,
        shared: bool = False,
    ) -> dict[str, Any]:
        servers = await self._custom_servers()
        if name in servers:
            raise ValueError(f"custom MCP connector already exists: {name}")
        spec: dict[str, Any] = {
            "transport": "streamable_http",
            "url": url,
            "enabled": enabled,
        }
        if display_name is not None:
            spec["display_name"] = display_name
        if headers:
            spec["headers"] = headers
        if default_open:
            spec["default_open"] = True
        if shared:
            spec["shared"] = True
        servers[name] = spec
        payload = self._as_dict(
            await self.request("PUT", "/api/connectors/custom-mcp", json={"servers": servers})
        )
        saved = self._servers_from_payload(payload)
        return self._safe_custom_server(name, self._as_dict(saved.get(name)))

    async def patch_mcp_connector(
        self,
        name: str,
        *,
        enabled: bool | None = None,
        default_open: bool | None = None,
        shared: bool | None = None,
    ) -> dict[str, Any]:
        values = {
            "enabled": enabled,
            "default_open": default_open,
            "shared": shared,
        }
        body = {key: value for key, value in values.items() if value is not None}
        if not body:
            raise ValueError("at least one connector setting must be provided")
        payload = self._as_dict(
            await self.request(
                "PATCH",
                f"/api/connectors/custom-mcp/servers/{self._segment(name)}",
                json=body,
            )
        )
        servers = self._servers_from_payload(payload)
        return self._safe_custom_server(name, self._as_dict(servers.get(name)))

    async def test_mcp_connector(self, name: str) -> dict[str, Any]:
        return self._as_dict(
            await self.request(
                "POST",
                "/api/connectors/custom-mcp/test",
                json={"name": name},
                timeout=60.0,
            )
        )

    async def delete_mcp_connector(self, name: str) -> dict[str, Any]:
        await self.request("DELETE", f"/api/connector-instances/{self._segment(f'custom:{name}')}")
        return {"ok": True, "name": name, "deleted": True}

    async def _custom_servers(self) -> dict[str, Any]:
        payload = self._as_dict(await self.request("GET", "/api/connectors/custom-mcp"))
        return self._servers_from_payload(payload)

    @staticmethod
    def _servers_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
        servers = payload.get("servers")
        if not isinstance(servers, dict):
            raise RuntimeError("Octop API returned an invalid custom MCP server map")
        return dict(servers)

    @staticmethod
    def _safe_connector(row: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "instance_id",
            "kind",
            "display_name",
            "description",
            "status",
            "mcp_server_name",
            "has_credentials",
            "default_open",
            "shared",
            "owner_username",
            "can_manage",
        )
        return {key: row.get(key) for key in keys if key in row}

    @staticmethod
    def _safe_custom_server(name: str, spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "display_name": spec.get("display_name") or name,
            "transport": spec.get("transport"),
            "url": spec.get("url"),
            "enabled": spec.get("enabled", True) is not False,
            "default_open": spec.get("default_open") is True,
            "shared": spec.get("shared") is True,
            "has_headers": bool(spec.get("headers")),
            "oauth_configured": bool(
                isinstance(spec.get("oauth"), dict) and spec["oauth"].get("configured")
            ),
        }

    @staticmethod
    def _segment(value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier must not be empty")
        return quote(cleaned, safe="")

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise RuntimeError("Octop API returned an unexpected non-object response")
        return value

    @staticmethod
    def _as_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise RuntimeError("Octop API returned an unexpected non-list response")
        return value
