"""Connector service — MCP config assembly and credential access."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_http_mcp_spec, mcp_server_name
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.connectors.custom_mcp import (
    CUSTOM_MCP_DISPLAY_NAME,
    CUSTOM_MCP_KIND,
    build_oauth_storage,
    enabled_harness_configs,
    expand_custom_instances,
    extract_servers,
    is_custom_mcp_kind,
    mark_oauth_reauth_required,
    merge_preserved_oauth,
    oauth_configured,
    oauth_tokens_from_spec,
    redact_servers_for_api,
    server_enabled,
    set_oauth_required_in_spec,
    validate_servers_map,
    wrap_servers,
)
from octop.infra.connectors.default_open import merge_mcp_servers_with_defaults, read_default_open
from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.feishu_user_auth import (
    complete_user_device_login,
    start_user_device_login,
)
from octop.infra.connectors.oauth import refresh_oauth_credentials
from octop.infra.connectors.oauth.registry import refresh_custom_mcp_oauth
from octop.infra.db.repos.connectors import ConnectorRepo, ConnectorRow
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

_OAUTH_REFRESH_SKEW_SEC = 120


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
        stored = dict(payload)
        stored["instance_id"] = instance_id
        expires_at = stored.get("expires_at")
        exp = int(expires_at) if expires_at is not None else None
        blob = encrypt_credentials(self._secret_repo, stored)
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

    def get_custom_servers_for_api(self, user_id: int) -> dict[str, Any]:
        return redact_servers_for_api(self.get_custom_servers(user_id))

    def put_custom_servers(self, user_id: int, servers: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_custom_servers(user_id)
        merged = merge_preserved_oauth(servers, existing)
        return self._save_custom_servers(user_id, merged)

    def _save_custom_servers(self, user_id: int, servers: dict[str, Any]) -> dict[str, Any]:
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

    def apply_custom_server_oauth(
        self,
        user_id: int,
        server_name: str,
        tokens: dict[str, Any],
        *,
        issuer: str,
        resource: str | None,
    ) -> dict[str, Any]:
        servers = dict(self.get_custom_servers(user_id))
        if server_name not in servers:
            raise KeyError(server_name)
        access = str(tokens.get("access_token") or "").strip()
        if not access:
            raise ValueError("missing access_token")
        spec = dict(servers[server_name])
        spec["oauth"] = build_oauth_storage(tokens, issuer=issuer, resource=resource)
        spec = set_oauth_required_in_spec(spec, required=False)
        servers[server_name] = spec
        return self._save_custom_servers(user_id, servers)

    async def ensure_fresh_custom_servers(self, user_id: int) -> dict[str, Any]:
        servers = dict(self.get_custom_servers(user_id))
        changed = False
        now = int(time.time())
        for name, raw in list(servers.items()):
            if not isinstance(raw, dict):
                continue
            oauth = oauth_tokens_from_spec(raw)
            if not oauth_configured(raw):
                continue
            expires_at_raw = oauth.get("expires_at")
            expires_at = int(expires_at_raw) if expires_at_raw is not None else None
            refresh = str(oauth.get("refresh_token") or "").strip()
            if expires_at is not None and expires_at <= now and not refresh:
                servers[name] = mark_oauth_reauth_required(dict(raw))
                changed = True
                continue
            if not refresh:
                continue
            if expires_at is not None and expires_at > now + _OAUTH_REFRESH_SKEW_SEC:
                continue
            try:
                refreshed = await refresh_custom_mcp_oauth(oauth)
            except Exception:
                logger.warning(
                    "custom MCP oauth refresh failed for %r (user_id=%s)",
                    name,
                    user_id,
                    exc_info=True,
                )
                if expires_at is not None and expires_at <= now:
                    servers[name] = mark_oauth_reauth_required(dict(raw))
                    changed = True
                continue
            spec = dict(raw)
            spec["oauth"] = refreshed
            servers[name] = spec
            changed = True
        if not changed:
            return servers
        return self._save_custom_servers(user_id, servers)

    def patch_custom_server_enabled(
        self,
        user_id: int,
        server_name: str,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        return self.patch_custom_server(user_id, server_name, enabled=enabled)

    def patch_custom_server(
        self,
        user_id: int,
        server_name: str,
        *,
        enabled: bool | None = None,
        default_open: bool | None = None,
    ) -> dict[str, Any]:
        servers = dict(self.get_custom_servers(user_id))
        if server_name not in servers:
            raise KeyError(server_name)
        spec = dict(servers[server_name])
        if enabled is not None:
            spec["enabled"] = enabled
            if not enabled:
                spec.pop("default_open", None)
        if default_open is not None:
            if default_open:
                spec["default_open"] = True
            else:
                spec.pop("default_open", None)
        servers[server_name] = spec
        return self.put_custom_servers(user_id, servers)

    def note_custom_server_oauth_required(
        self,
        user_id: int,
        server_name: str,
        *,
        required: bool,
    ) -> dict[str, Any]:
        servers = dict(self.get_custom_servers(user_id))
        if server_name not in servers:
            raise KeyError(server_name)
        spec = dict(servers[server_name])
        servers[server_name] = set_oauth_required_in_spec(spec, required=required)
        return self._save_custom_servers(user_id, servers)

    def patch_custom_server_default_open(
        self,
        user_id: int,
        server_name: str,
        *,
        default_open: bool,
    ) -> dict[str, Any]:
        return self.patch_custom_server(user_id, server_name, default_open=default_open)

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
                    "default_open": read_default_open(ConnectorRepo.parse_config_json(inst)),
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

    def list_default_open_mcp_server_names(self, user_id: int) -> list[str]:
        """Active connectors marked default_open (dashboard + all IM channels)."""
        names: list[str] = []
        for inst in self._repo.list_by_user(user_id):
            if is_custom_mcp_kind(inst.kind):
                continue
            if inst.status != "active" or not inst.has_credentials:
                continue
            if read_default_open(ConnectorRepo.parse_config_json(inst)):
                names.append(inst.mcp_server_name)
        for name, spec in self.get_custom_servers(user_id).items():
            if not isinstance(spec, dict) or not server_enabled(spec):
                continue
            if spec.get("default_open") is True:
                names.append(name)
        return names

    def merge_turn_mcp_servers(
        self,
        user_id: int,
        explicit: list[str] | None,
        *,
        apply_defaults: bool | None = None,
    ) -> list[str] | None:
        """Resolve turn MCP servers vs the user's default_open set.

        Dashboard passes an explicit list (``apply_defaults=False``) so users can
        opt out for a turn. IM uses ``explicit is None`` + defaults. Cron follows
        defaults when the job has no picks; explicit Cron picks win as-is.
        """
        return merge_mcp_servers_with_defaults(
            explicit,
            self.list_default_open_mcp_server_names(user_id),
            apply_defaults=apply_defaults,
        )

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
        await self.ensure_fresh_custom_servers(user_id)
        configs.update(self.custom_harness_configs(user_id))
        return configs

    def verify_internal_token(self, instance_id: str, token: str) -> dict[str, Any] | None:
        creds = self.decrypt(instance_id)
        expected = str(creds.get("internal_token") or "")
        if not expected or expected != token:
            return None
        return creds

    # --- Feishu CLI device-code user auth (domain orchestration) ---

    @staticmethod
    def feishu_cli_config_dir(cli_config_key: str) -> Path:
        return PathLayout.from_env().ensure_connector_cli_instance_dir("feishu-cli", cli_config_key)

    async def start_feishu_user_auth(
        self,
        *,
        app_id: str,
        app_secret: str,
        cli_config_key: str | None = None,
        domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Begin OAuth device-code login (anonymous / pre-save credentials)."""
        app_id = str(app_id or "").strip()
        app_secret = str(app_secret or "").strip()
        if not app_id or not app_secret:
            raise ValueError("app_id and app_secret are required")
        cli_key = str(cli_config_key or "").strip() or new_ulid()
        config_dir = self.feishu_cli_config_dir(cli_key)
        started = await asyncio.to_thread(
            start_user_device_login,
            config_dir=config_dir,
            app_id=app_id,
            app_secret=app_secret,
            domains=domains,
        )
        return {**started, "cli_config_key": cli_key}

    async def complete_feishu_user_auth(
        self,
        *,
        app_id: str,
        app_secret: str,
        device_code: str,
        cli_config_key: str,
    ) -> dict[str, Any]:
        """Finish device-code login for pre-save credentials (no instance write)."""
        app_id = str(app_id or "").strip()
        app_secret = str(app_secret or "").strip()
        device_code = str(device_code or "").strip()
        cli_key = str(cli_config_key or "").strip()
        if not app_id or not app_secret or not device_code or not cli_key:
            raise ValueError("app_id, app_secret, device_code and cli_config_key are required")
        config_dir = self.feishu_cli_config_dir(cli_key)
        result = await asyncio.to_thread(
            complete_user_device_login,
            config_dir=config_dir,
            app_id=app_id,
            app_secret=app_secret,
            device_code=device_code,
        )
        return {**result, "cli_config_key": cli_key, "default_as": "user"}

    def _require_feishu_cli_instance(
        self, instance_id: str, user_id: int
    ) -> tuple[ConnectorRow, dict[str, Any]]:
        inst = self._repo.get(instance_id)
        if inst is None:
            raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, f"instance {instance_id!r} not found")
        if inst.user_id != user_id:
            raise OctopError(ErrorCode.FORBIDDEN, "not your connector instance")
        if inst.kind != "feishu-cli":
            raise OctopError(
                ErrorCode.CONNECTOR_KIND_UNSUPPORTED,
                "only feishu-cli supports user device login",
            )
        if not inst.has_credentials:
            raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "missing credentials")
        return inst, dict(self.decrypt(instance_id))

    async def start_feishu_user_auth_for_instance(
        self, instance_id: str, user_id: int
    ) -> dict[str, Any]:
        """Start device login using App Secret stored on the instance."""
        _inst, creds = self._require_feishu_cli_instance(instance_id, user_id)
        app_id = str(creds.get("app_id") or "").strip()
        app_secret = str(creds.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                "stored Feishu app credentials incomplete",
                details={"reason": "stored Feishu app credentials incomplete"},
            )
        if not str(creds.get("cli_config_key") or "").strip():
            creds["cli_config_key"] = instance_id
        cli_key = resolve_cli_config_key(creds)
        config_dir = self.feishu_cli_config_dir(cli_key)
        started = await asyncio.to_thread(
            start_user_device_login,
            config_dir=config_dir,
            app_id=app_id,
            app_secret=app_secret,
            domains=None,
        )
        return {**started, "cli_config_key": cli_key}

    async def complete_feishu_user_auth_for_instance(
        self,
        instance_id: str,
        user_id: int,
        *,
        device_code: str,
        cli_config_key: str | None = None,
    ) -> dict[str, Any]:
        """Finish device login and persist ``default_as=user`` on the instance."""
        _inst, creds = self._require_feishu_cli_instance(instance_id, user_id)
        app_id = str(creds.get("app_id") or "").strip()
        app_secret = str(creds.get("app_secret") or "").strip()
        device_code = str(device_code or "").strip()
        if not str(creds.get("cli_config_key") or "").strip():
            creds["cli_config_key"] = instance_id
        override = str(cli_config_key or "").strip()
        if override:
            creds["cli_config_key"] = override
        cli_key = resolve_cli_config_key(creds)
        if not app_id or not app_secret or not device_code:
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                "incomplete Feishu user auth payload",
                details={"reason": "incomplete Feishu user auth payload"},
            )
        config_dir = self.feishu_cli_config_dir(cli_key)
        result = await asyncio.to_thread(
            complete_user_device_login,
            config_dir=config_dir,
            app_id=app_id,
            app_secret=app_secret,
            device_code=device_code,
        )
        creds["default_as"] = "user"
        creds["cli_config_key"] = cli_key
        self.encrypt_and_store(instance_id=instance_id, payload=creds)
        return {**result, "cli_config_key": cli_key, "default_as": "user"}
