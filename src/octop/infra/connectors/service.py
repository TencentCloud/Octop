"""Connector service — MCP config assembly and credential access."""

from __future__ import annotations

import time
from typing import Any

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_http_mcp_spec, mcp_server_name
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.connectors.custom_mcp import (
    CUSTOM_MCP_DISPLAY_NAME,
    CUSTOM_MCP_KIND,
    enabled_harness_configs,
    expand_custom_instances,
    extract_servers,
    is_custom_mcp_kind,
    server_enabled,
    validate_servers_map,
    wrap_servers,
)
from octop.infra.connectors.oauth import refresh_oauth_credentials
from octop.infra.db.repos.connectors import ConnectorRepo, ConnectorRow
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.utils.ulid import new_ulid


def list_user_connector_instances(
    repo: ConnectorRepo,
    user_id: int,
    *,
    active_only: bool = False,
    with_credentials: bool = False,
) -> list[ConnectorRow]:
    """List connector instances for *user_id* with optional filters."""
    rows = repo.list_by_user(user_id)
    if active_only:
        rows = [r for r in rows if r.status == "active"]
    if with_credentials:
        rows = [r for r in rows if r.has_credentials]
    return rows


class ConnectorService:
    def __init__(
        self,
        *,
        repo: ConnectorRepo,
        secret_repo: SecretRepo,
        settings_repo: Any,
        config: OctopConfig,
    ) -> None:
        self._repo = repo
        self._secret_repo = secret_repo
        self._settings_repo = settings_repo
        self._config = config

    def list_user_instances(
        self,
        user_id: int,
        *,
        active_only: bool = False,
        with_credentials: bool = False,
    ) -> list[ConnectorRow]:
        return list_user_connector_instances(
            self._repo,
            user_id,
            active_only=active_only,
            with_credentials=with_credentials,
        )

    def decrypt(self, instance_id: str) -> dict[str, Any]:
        row = self._repo.get(instance_id)
        if row is None or not row.credential_blob:
            return {}
        return decrypt_credentials(self._secret_repo, row.credential_blob)

    def encrypt_and_store(
        self,
        *,
        instance_id: str,
        payload: dict[str, Any],
    ) -> None:
        expires_at = payload.get("expires_at")
        exp = int(expires_at) if expires_at is not None else None
        blob = encrypt_credentials(self._secret_repo, payload)
        self._repo.upsert_credentials(instance_id=instance_id, blob=blob, expires_at=exp)

    async def ensure_fresh_credentials(
        self,
        instance_id: str,
        kind: str,
    ) -> dict[str, Any]:
        creds = self.decrypt(instance_id)
        entry = get_catalog_entry(kind)
        if entry is None or entry.auth_kind != "oauth2":
            return creds
        expires_at = creds.get("expires_at")
        if expires_at and int(expires_at) > int(time.time()) + 120:
            return creds
        refresh = str(creds.get("refresh_token") or "")
        if not refresh:
            return creds
        try:
            refreshed = await refresh_oauth_credentials(
                kind=kind,
                creds=creds,
                settings_repo=self._settings_repo,
            )
        except Exception:
            return creds
        creds.update(refreshed)
        self.encrypt_and_store(instance_id=instance_id, payload=creds)
        return creds

    def reserved_builtin_mcp_names(self, user_id: int) -> set[str]:
        names: set[str] = set()
        for inst in self._repo.list_by_user(user_id):
            if is_custom_mcp_kind(inst.kind):
                continue
            names.add(inst.mcp_server_name)
        return names

    def get_custom_servers(self, user_id: int) -> dict[str, Any]:
        row = self._repo.get_by_user_kind(user_id, CUSTOM_MCP_KIND)
        if row is None or not row.has_credentials:
            return {}
        return extract_servers(self.decrypt(row.instance_id))

    def put_custom_servers(self, user_id: int, servers: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_servers_map(
            servers,
            reserved_names=self.reserved_builtin_mcp_names(user_id),
        )
        row = self._repo.get_by_user_kind(user_id, CUSTOM_MCP_KIND)
        if not normalized:
            if row is not None:
                self._repo.delete(row.instance_id)
            return {}
        if row is None:
            instance_id = new_ulid()
            self._repo.create(
                instance_id=instance_id,
                user_id=user_id,
                kind=CUSTOM_MCP_KIND,
                display_name=CUSTOM_MCP_DISPLAY_NAME,
                mcp_server_name=mcp_server_name(CUSTOM_MCP_KIND, instance_id),
            )
        else:
            instance_id = row.instance_id
        self.encrypt_and_store(
            instance_id=instance_id,
            payload=wrap_servers(normalized),
        )
        return normalized

    def patch_custom_server_enabled(
        self,
        user_id: int,
        server_name: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        servers = dict(self.get_custom_servers(user_id))
        if server_name not in servers:
            raise KeyError(server_name)
        spec = dict(servers[server_name])
        spec["enabled"] = enabled
        servers[server_name] = spec
        return self.put_custom_servers(user_id, servers)

    def list_instances_for_api(self, user_id: int) -> list[dict[str, Any]]:
        """Built-in rows + expanded custom servers (hide parent custom-mcp row)."""
        out: list[dict[str, Any]] = []
        custom_row = self._repo.get_by_user_kind(user_id, CUSTOM_MCP_KIND)
        for inst in self._repo.list_by_user(user_id):
            if is_custom_mcp_kind(inst.kind):
                continue
            out.append(
                {
                    "instance_id": inst.instance_id,
                    "kind": inst.kind,
                    "display_name": inst.display_name,
                    "status": inst.status,
                    "mcp_server_name": inst.mcp_server_name,
                    "has_credentials": inst.has_credentials,
                    "created_at": inst.created_at,
                    "updated_at": inst.updated_at,
                }
            )
        if custom_row is not None and custom_row.has_credentials:
            out.extend(
                expand_custom_instances(
                    parent=custom_row,
                    servers=extract_servers(self.decrypt(custom_row.instance_id)),
                )
            )
        return out

    def list_active_mcp_server_names(self, user_id: int) -> list[str]:
        names: list[str] = []
        for inst in self._repo.list_by_user(user_id):
            if is_custom_mcp_kind(inst.kind):
                continue
            if inst.status != "active" or not inst.has_credentials:
                continue
            names.append(inst.mcp_server_name)
        for name, spec in self.get_custom_servers(user_id).items():
            if isinstance(spec, dict) and server_enabled(spec):
                names.append(name)
        return sorted(names)

    def validate_mcp_servers_for_user(self, user_id: int, names: list[str]) -> list[str]:
        allowed = set(self.list_active_mcp_server_names(user_id))
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValueError(f"mcp_servers not available for user: {unknown}")
        return list(names)

    def custom_harness_configs(self, user_id: int) -> dict[str, Any]:
        return enabled_harness_configs(self.get_custom_servers(user_id))

    async def mcp_configs_for_user(self, user_id: int) -> dict[str, Any]:
        configs: dict[str, Any] = {}
        for inst in self._repo.list_by_user(user_id):
            if inst.status != "active":
                continue
            if is_custom_mcp_kind(inst.kind):
                continue
            entry = get_catalog_entry(inst.kind)
            if entry is None:
                continue
            creds = await self.ensure_fresh_credentials(inst.instance_id, inst.kind)
            if not creds:
                continue
            configs[inst.mcp_server_name] = build_http_mcp_spec(
                entry=entry,
                instance_id=inst.instance_id,
                creds=creds,
                config=self._config,
            )
        configs.update(self.custom_harness_configs(user_id))
        return configs

    def verify_internal_token(self, instance_id: str, token: str) -> dict[str, Any] | None:
        creds = self.decrypt(instance_id)
        expected = str(creds.get("internal_token") or "")
        if not expected or expected != token:
            return None
        return creds
