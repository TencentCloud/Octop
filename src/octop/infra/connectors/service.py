"""Connector service — MCP config assembly and credential access."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from octop.config import OctopConfig
from octop.infra.connectors import qcc
from octop.infra.connectors.auth_status import (
    AUTH_EXPIRED,
    AUTH_OK,
    NEEDS_AUTH,
    custom_auth_status,
)
from octop.infra.connectors.builder import build_http_mcp_spec, mcp_server_name, new_internal_token
from octop.infra.connectors.catalog import get_catalog_entry, uses_internal_http_mcp
from octop.infra.connectors.crypto import decrypt_credentials, encrypt_credentials
from octop.infra.connectors.custom_mcp import (
    CUSTOM_MCP_DISPLAY_NAME,
    CUSTOM_MCP_KIND,
    build_oauth_storage,
    expand_custom_instances,
    extract_servers,
    harness_spec_for_server,
    is_custom_mcp_kind,
    mark_oauth_reauth_required,
    merge_preserved_oauth,
    oauth_configured,
    oauth_tokens_from_spec,
    redact_servers_for_api,
    server_display_name,
    server_enabled,
    set_oauth_required_in_spec,
    shared_mcp_server_name,
    validate_servers_map,
    wrap_servers,
)
from octop.infra.connectors.default_open import merge_mcp_servers_with_defaults, read_default_open
from octop.infra.connectors.gateway import agently_auth
from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.feishu_user_auth import (
    complete_user_device_login,
    start_user_device_login,
)
from octop.infra.connectors.oauth import refresh_oauth_credentials
from octop.infra.connectors.oauth.mcp import OAuthRefreshRejected
from octop.infra.connectors.oauth.registry import refresh_custom_mcp_oauth
from octop.infra.db.repos.connectors import ConnectorRepo, ConnectorRow
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)

_OAUTH_REFRESH_SKEW_SEC = 120

# Shared only within one process and application repository.
_QCC_LOCKS: WeakKeyDictionary[ConnectorRepo, dict[str, asyncio.Lock]] = WeakKeyDictionary()
_AGENTLY_LOCKS: WeakKeyDictionary[ConnectorRepo, dict[str, asyncio.Lock]] = WeakKeyDictionary()
_CUSTOM_MCP_LOCKS: WeakKeyDictionary[ConnectorRepo, dict[tuple[int, str], asyncio.Lock]] = (
    WeakKeyDictionary()
)


class ConnectorNameTakenError(ValueError):
    """Raised when a connector display name is already owned by the user."""


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
        row = self._repo.get(instance_id)
        if row is not None:
            entry = get_catalog_entry(row.kind)
            if entry is not None and uses_internal_http_mcp(entry):
                existing = (
                    decrypt_credentials(self._secret_repo, row.credential_blob)
                    if row.credential_blob
                    else {}
                )
                stored["internal_token"] = (
                    existing.get("internal_token")
                    or stored.get("internal_token")
                    or new_internal_token()
                )
            if row.kind == "agently-cli" and row.credential_blob:
                # Editing a connector must never switch to another instance's grant.
                existing = decrypt_credentials(self._secret_repo, row.credential_blob)
                stored["cli_config_key"] = resolve_cli_config_key(existing)
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
        if kind == "qcc":
            return await self._fresh_qcc(instance_id)
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

    def _qcc_lock(self, instance_id: str) -> asyncio.Lock:
        locks = _QCC_LOCKS.setdefault(self._repo, {})
        return locks.setdefault(instance_id, asyncio.Lock())

    async def _fresh_qcc(
        self, instance_id: str, *, rejected_token: str | None = None
    ) -> dict[str, Any]:
        async with self._qcc_lock(instance_id):
            row = self._repo.get(instance_id)
            if row is None or row.kind != "qcc" or row.status != "active":
                return {}
            creds = self.decrypt(instance_id)
            if not qcc.is_oauth_grant(creds):
                return creds
            token = qcc.bearer_token(creds)
            # Another request may already have rotated the token rejected by a 401.
            force = rejected_token is not None and rejected_token == token
            expires = int(creds.get("expires_at") or 0)
            if not force and expires > int(time.time()) + _OAUTH_REFRESH_SKEW_SEC:
                return creds
            if not creds.get("refresh_token"):
                if force or (expires and expires <= int(time.time())):
                    raise ValueError("QCC authorization expired; please authorize again")
                return creds
            if not creds.get("oauth_client_id"):
                raise ValueError("QCC client registration missing; please authorize again")
            refreshed = await refresh_oauth_credentials(
                kind="qcc", creds=creds, settings_repo=self._settings_repo
            )
            creds.update(refreshed)
            self.encrypt_and_store(instance_id=instance_id, payload=creds)
            return creds

    async def _qcc_request(
        self, instance_id: str, resource: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        creds = await self._fresh_qcc(instance_id)
        token = qcc.bearer_token(creds)
        if not token:
            raise ValueError("QCC connector is disconnected")
        try:
            return await qcc.request_resource(resource, token, method, params)
        except Exception as exc:
            if not qcc.is_oauth_grant(creds) or not qcc.unauthorized(exc):
                raise
        creds = await self._fresh_qcc(instance_id, rejected_token=token)
        token = qcc.bearer_token(creds)
        if not token:
            raise ValueError("QCC connector is disconnected")
        return await qcc.request_resource(resource, token, method, params)

    async def handle_qcc_request(self, instance_id: str, body: dict[str, Any]) -> dict[str, Any]:
        from octop.infra.connectors.gateway.protocol import handle_mcp_request

        method = body.get("method")
        if method not in ("tools/list", "tools/call"):
            return handle_mcp_request(kind="qcc", creds={}, body=body)
        try:
            if method == "tools/list":
                listed = await asyncio.gather(
                    *[
                        self._qcc_request(instance_id, resource, "tools/list", {})
                        for resource in qcc.RESOURCES
                    ],
                    return_exceptions=True,
                )
                tools: list[dict[str, Any]] = []
                for resource, item in zip(qcc.RESOURCES, listed, strict=True):
                    if isinstance(item, BaseException):
                        continue
                    tools.extend(qcc.namespace_tools(resource, item))
                if not tools:
                    raise ValueError("QCC MCP request failed; check connection or authorize again")
                result: dict[str, Any] = {"tools": tools}
            else:
                params = dict(body.get("params") or {})
                resource, sep, name = str(params.get("name") or "").partition("__")
                if not sep or resource not in qcc.RESOURCES or not name:
                    raise ValueError("Unknown QCC tool")
                result = await self._qcc_request(
                    instance_id, resource, "tools/call", {**params, "name": name}
                )
            return {"jsonrpc": "2.0", "id": body.get("id"), "result": result}
        except Exception:
            # Upstream exceptions may include credential-bearing request details.
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32603,
                    "message": "QCC MCP request failed; check connection or authorize again",
                },
            }

    async def disconnect_qcc(self, instance_id: str) -> None:
        async with self._qcc_lock(instance_id):
            row = self._repo.get(instance_id)
            if row is None:
                return
            if row.kind != "qcc":
                raise ValueError("Not a QCC connector")
            try:
                creds = self.decrypt(instance_id)
                if qcc.is_oauth_grant(creds):
                    await qcc.revoke(creds)
            except Exception as exc:
                # Keep the encrypted grant so the user can retry remote revocation.
                raise ValueError("QCC revocation failed; retry disconnect") from exc
            self._repo.delete(instance_id)

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
        display_names: set[str] = set()
        for name, spec in normalized.items():
            display_name = (
                str(spec.get("display_name") or "").strip() if isinstance(spec, dict) else ""
            ) or name
            if display_name in display_names or self._repo.name_exists(user_id, display_name):
                raise ConnectorNameTakenError(display_name)
            display_names.add(display_name)
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
        for name in self.get_custom_servers(user_id):
            await self.ensure_fresh_custom_server(user_id, name)
        return self.get_custom_servers(user_id)

    def _store_custom_server_oauth(
        self,
        user_id: int,
        server_name: str,
        previous: dict[str, Any],
        oauth: dict[str, Any],
    ) -> dict[str, Any]:
        # Re-read after network I/O: preserve other servers, edits and newer grants.
        servers = self.get_custom_servers(user_id)
        current: dict[str, Any] = servers.get(server_name, {})
        if (
            not current
            or current.get("url") != previous.get("url")
            or current.get("oauth") != previous.get("oauth")
        ):
            return current
        servers[server_name] = {**current, "oauth": oauth}
        return dict(self._save_custom_servers(user_id, servers)[server_name])

    def _mark_custom_server_lapsed(
        self, user_id: int, server_name: str, previous: dict[str, Any]
    ) -> dict[str, Any]:
        # Same marker as the pre-turn check, so the grant reads as expired, not never authorized.
        lapsed = mark_oauth_reauth_required(previous)["oauth"]
        return self._store_custom_server_oauth(user_id, server_name, previous, lapsed)

    def reject_custom_server_token(self, user_id: int, server_name: str, token: str) -> None:
        spec = self.get_custom_servers(user_id).get(server_name, {})
        if oauth_tokens_from_spec(spec).get("access_token") == token:
            self._mark_custom_server_lapsed(user_id, server_name, spec)

    async def ensure_fresh_custom_server(
        self, user_id: int, server_name: str, *, rejected_token: str | None = None
    ) -> dict[str, Any]:
        locks = _CUSTOM_MCP_LOCKS.setdefault(self._repo, {})
        lock = locks.setdefault((user_id, server_name), asyncio.Lock())
        async with lock:
            raw: dict[str, Any] = self.get_custom_servers(user_id).get(server_name, {})
            oauth = oauth_tokens_from_spec(raw)
            if not oauth_configured(raw):
                return raw
            # Concurrent 401 responses can reuse the token another request refreshed.
            if rejected_token is not None and rejected_token != oauth.get("access_token"):
                return raw
            now = int(time.time())
            expires_at_raw = oauth.get("expires_at")
            expires_at = int(expires_at_raw) if expires_at_raw is not None else None
            expired = expires_at is not None and expires_at <= now
            force = rejected_token is not None
            if not force and (expires_at is None or expires_at > now + _OAUTH_REFRESH_SKEW_SEC):
                return raw
            refresh = str(oauth.get("refresh_token") or "").strip()
            if not refresh or not oauth.get("oauth_client_id") or not oauth.get("oauth_issuer"):
                if expired or force:
                    return self._mark_custom_server_lapsed(user_id, server_name, raw)
                return raw
            try:
                refreshed = await refresh_custom_mcp_oauth(oauth)
            except Exception as exc:
                logger.warning(
                    "custom MCP oauth refresh failed for %r (user_id=%s)",
                    server_name,
                    user_id,
                )
                if (
                    (expires_at is not None and expires_at <= int(time.time()))
                    or force
                    or isinstance(exc, OAuthRefreshRejected)
                ):
                    return self._mark_custom_server_lapsed(user_id, server_name, raw)
                return dict(self.get_custom_servers(user_id).get(server_name, {}))
            return self._store_custom_server_oauth(user_id, server_name, raw, refreshed)

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
        shared: bool | None = None,
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
        if shared is not None:
            if shared:
                spec["shared"] = True
            else:
                spec.pop("shared", None)
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
        visible = self._repo.list_visible(user_id)
        custom_row = self._repo.get_by_user_kind(user_id, CUSTOM_MCP_KIND)
        custom_specs: dict[str, dict[str, Any]] = {}
        for inst in visible:
            if is_custom_mcp_kind(inst.kind):
                continue
            config = ConnectorRepo.parse_config_json(inst)
            out.append(
                {
                    "instance_id": inst.instance_id,
                    "kind": inst.kind,
                    "display_name": inst.display_name,
                    "description": config.get("description"),
                    "status": inst.status,
                    "mcp_server_name": inst.mcp_server_name,
                    "has_credentials": inst.has_credentials,
                    "default_open": read_default_open(config),
                    "shared": inst.shared,
                    "owner_user_id": inst.user_id,
                    "created_at": inst.created_at,
                    "updated_at": inst.updated_at,
                }
            )
        if custom_row is not None and custom_row.has_credentials:
            own = extract_servers(self.decrypt(custom_row.instance_id))
            custom_specs.update(own)
            out.extend(expand_custom_instances(parent=custom_row, servers=own))
        # Per-server ``shared`` lives in the encrypted bag, not on the parent row.
        for parent in self._repo.list_by_kind(CUSTOM_MCP_KIND):
            if parent.user_id == user_id or not parent.has_credentials:
                continue
            servers = extract_servers(self.decrypt(parent.instance_id))
            custom_specs.update(
                {
                    shared_mcp_server_name(parent.instance_id, name): spec
                    for name, spec in servers.items()
                    if isinstance(spec, dict)
                }
            )
            out.extend(expand_custom_instances(parent=parent, servers=servers, shared_view=True))
        for item in out:
            spec = custom_specs.get(str(item.get("mcp_server_name") or ""))
            if is_custom_mcp_kind(str(item.get("kind") or "")) and isinstance(spec, dict):
                status = custom_auth_status(spec)
                if status:
                    item["auth_status"] = status
            item.setdefault("owner_user_id", user_id)
            item.setdefault("shared", False)
            # list_visible already applied the per-instance group layer.
            item["usable"] = True
        return out

    async def auth_blocked_servers(
        self, user_id: int, server_names: list[str], *, probe: bool = True
    ) -> list[dict[str, Any]]:
        """Which custom MCP servers in *server_names* need the user to authorize.

        Called after MCP tools could not be loaded. A stored token whose status
        still looks fine is probed once: a 401/403 from the MCP server means it
        was revoked, and the server is marked so the dashboard prompts too.
        """
        wanted = set(server_names)
        blocked: list[dict[str, Any]] = []
        own = self.get_custom_servers(user_id)
        candidates: list[tuple[str, int, str, dict[str, Any]]] = [
            (name, user_id, name, spec)
            for name, spec in own.items()
            if name in wanted and isinstance(spec, dict)
        ]
        for parent in self._repo.list_by_kind(CUSTOM_MCP_KIND):
            if parent.user_id == user_id or not parent.has_credentials:
                continue
            for name, spec in extract_servers(self.decrypt(parent.instance_id)).items():
                shown = shared_mcp_server_name(parent.instance_id, name)
                if shown in wanted and isinstance(spec, dict) and spec.get("shared") is True:
                    candidates.append((shown, parent.user_id, name, spec))
        for shown, owner_id, name, spec in candidates:
            status = custom_auth_status(spec)
            if (
                status == AUTH_OK
                and probe
                and str(spec.get("transport") or "") in ("streamable_http", "http")
            ):
                harness = harness_spec_for_server(spec)
                if await _token_rejected(
                    str(harness.get("url") or ""),
                    dict(harness.get("headers") or {}),
                    kind=CUSTOM_MCP_KIND,
                ):
                    servers = dict(self.get_custom_servers(owner_id))
                    if isinstance(servers.get(name), dict):
                        servers[name] = mark_oauth_reauth_required(dict(servers[name]))
                        self._save_custom_servers(owner_id, servers)
                    status = AUTH_EXPIRED
            if status in NEEDS_AUTH:
                blocked.append(
                    {
                        "server": shown,
                        "display_name": server_display_name(name, spec),
                        "auth_status": status,
                        "can_authorize": owner_id == user_id,
                        "target": {"type": "custom_mcp", "server_name": name},
                    }
                )
        return blocked

    def shared_custom_harness_aliases(self, owner_user_id: int) -> dict[str, str]:
        """Map a viewer's collision-safe name to the owner's harness server name.

        The owner's custom server is registered as ``doris``. Everyone else
        addresses the same shared server as ``custom__{instance}__doris``.
        A shared expert's harness only knows the short name.
        """
        if not self._repo.connector_feature_allows(owner_user_id):
            return {}
        parent = self._repo.get_by_user_kind(owner_user_id, CUSTOM_MCP_KIND)
        if parent is None or not parent.has_credentials:
            return {}
        aliases: dict[str, str] = {}
        for name, spec in extract_servers(self.decrypt(parent.instance_id)).items():
            if (
                not isinstance(spec, dict)
                or spec.get("shared") is not True
                or not server_enabled(spec)
            ):
                continue
            aliases[shared_mcp_server_name(parent.instance_id, name)] = name
        return aliases

    def align_mcp_names_to_harness(
        self,
        *,
        owner_user_id: int | None,
        viewer_user_id: int,
        names: list[str],
    ) -> list[str]:
        """Rewrite viewer-facing shared custom names onto the agent's harness.

        Other names are left unchanged. The owner already speaks harness names.
        """
        if owner_user_id is None or owner_user_id == viewer_user_id or not names:
            return list(names)
        aliases = self.shared_custom_harness_aliases(owner_user_id)
        if not aliases:
            return list(names)
        out: list[str] = []
        for name in names:
            mapped = aliases.get(name, name)
            if mapped not in out:
                out.append(mapped)
        return out

    def present_mcp_names_for_viewer(
        self,
        *,
        owner_user_id: int | None,
        viewer_user_id: int,
        names: list[str],
    ) -> list[str]:
        """Show a non-owner the catalog names they can actually select.

        Owner short names of shared custom servers become the collision-safe
        name. Servers the viewer cannot use are omitted.
        """
        if owner_user_id is None or owner_user_id == viewer_user_id:
            return list(names)
        aliases = self.shared_custom_harness_aliases(owner_user_id)
        reverse: dict[str, str] = {}
        for long_name, short_name in aliases.items():
            reverse.setdefault(short_name, long_name)
        allowed = set(self.list_active_mcp_server_names(viewer_user_id))
        out: list[str] = []
        for name in names:
            shown = reverse.get(name, name)
            if shown in allowed and shown not in out:
                out.append(shown)
        return out

    def mcp_names_for_chips(
        self,
        *,
        owner_user_id: int | None,
        viewer_user_id: int,
        requested: list[str],
        harness_names: list[str],
    ) -> list[str]:
        """Catalog names for the servers that will actually run this turn.

        A viewer's own server keeps its short name. The owner's shared server
        shows the collision-safe name when that is what was selected. Selecting
        both collapses to the shared server, so only that chip is returned.
        """
        if owner_user_id is None or owner_user_id == viewer_user_id:
            return list(requested)
        aliases = self.shared_custom_harness_aliases(owner_user_id)
        short_to_long = {short: long for long, short in aliases.items()}
        active = set(harness_names)
        out: list[str] = []
        for name in requested:
            mapped = aliases.get(name, name)
            if mapped not in active:
                continue
            shared_label = short_to_long.get(mapped)
            shown = shared_label if shared_label is not None and shared_label in requested else name
            if shown not in out:
                out.append(shown)
        return out

    def list_active_mcp_server_names(self, user_id: int) -> list[str]:
        if not self._repo.connector_feature_allows(user_id):
            return []
        names: list[str] = []
        for inst in self._repo.list_visible(user_id):
            if is_custom_mcp_kind(inst.kind):
                continue
            if inst.status != "active" or not inst.has_credentials:
                continue
            names.append(inst.mcp_server_name)
        for name, spec in self.get_custom_servers(user_id).items():
            if isinstance(spec, dict) and server_enabled(spec):
                names.append(name)
        for parent in self._repo.list_by_kind(CUSTOM_MCP_KIND):
            if parent.user_id == user_id or not parent.has_credentials:
                continue
            for name, spec in extract_servers(self.decrypt(parent.instance_id)).items():
                if isinstance(spec, dict) and spec.get("shared") is True and server_enabled(spec):
                    names.append(shared_mcp_server_name(parent.instance_id, name))
        return sorted(names)

    def list_default_open_mcp_server_names(self, user_id: int) -> list[str]:
        """Active connectors marked default_open (dashboard + all IM channels)."""
        if not self._repo.connector_feature_allows(user_id):
            return []
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
        extra_defaults: list[str] | None = None,
        agent_owner_id: int | None = None,
    ) -> list[str] | None:
        """Resolve turn MCP servers vs the user's default_open set.

        Dashboard passes an explicit list (``apply_defaults=False``) so users can
        opt out for a turn. IM uses ``explicit is None`` + defaults. Cron follows
        defaults when the job has no picks; explicit Cron picks win as-is.
        ``extra_defaults`` (expert composer picks) are unioned with default_open
        when defaults apply, but only names still available to *user_id*.

        When ``agent_owner_id`` is another user, an expert pick stored under the
        owner's short custom-MCP name is returned as the viewer's catalog name
        (``custom__...``) when that server is shared. Callers translate to the
        harness short name only when building the model request.
        """
        aliases: dict[str, str] = {}
        if agent_owner_id is not None and agent_owner_id != user_id:
            aliases = self.shared_custom_harness_aliases(agent_owner_id)
        defaults = list(self.list_default_open_mcp_server_names(user_id))
        if extra_defaults:
            allowed = set(self.list_active_mcp_server_names(user_id))
            short_to_long = {short: long for long, short in aliases.items()}
            for name in extra_defaults:
                text = str(name).strip()
                if not text:
                    continue
                viewer_name = short_to_long.get(text)
                # The viewer's own server can share the short name. Keep the
                # shared server under its catalog name instead of skipping it.
                if viewer_name is not None and viewer_name in allowed:
                    if viewer_name not in defaults:
                        defaults.append(viewer_name)
                elif text in allowed and text not in defaults:
                    defaults.append(text)
        return merge_mcp_servers_with_defaults(
            explicit,
            defaults,
            apply_defaults=apply_defaults,
        )

    def validate_mcp_servers_for_user(self, user_id: int, names: list[str]) -> list[str]:
        allowed = set(self.list_active_mcp_server_names(user_id))
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValueError(f"mcp_servers not available for user: {unknown}")
        return list(names)

    def custom_harness_configs(self, user_id: int) -> dict[str, Any]:
        if not self._repo.connector_feature_allows(user_id):
            return {}
        configs = {
            name: self._custom_harness_spec(user_id, user_id, name, spec)
            for name, spec in self.get_custom_servers(user_id).items()
            if isinstance(spec, dict) and server_enabled(spec)
        }
        for parent in self._repo.list_by_kind(CUSTOM_MCP_KIND):
            if parent.user_id == user_id or not parent.has_credentials:
                continue
            servers = extract_servers(self.decrypt(parent.instance_id))
            for name, spec in servers.items():
                if (
                    not isinstance(spec, dict)
                    or spec.get("shared") is not True
                    or not server_enabled(spec)
                ):
                    continue
                configs[shared_mcp_server_name(parent.instance_id, name)] = (
                    self._custom_harness_spec(parent.user_id, user_id, name, spec)
                )
        return configs

    def _custom_harness_spec(
        self, owner_user_id: int, user_id: int, name: str, spec: dict[str, Any]
    ) -> dict[str, Any]:
        from octop.infra.connectors.oauth.runtime import CustomMcpOAuthAuth

        built = harness_spec_for_server(spec)
        # A discovery hint alone must not replace a user's fixed authentication headers.
        if spec.get("transport") == "streamable_http" and oauth_configured(spec):
            # Cached tools retain this auth provider, never a snapshot of the token.
            built["headers"] = {
                key: value
                for key, value in built["headers"].items()
                if key.lower() != "authorization"
            }
            built["auth"] = CustomMcpOAuthAuth(
                self,
                owner_user_id=owner_user_id,
                user_id=user_id,
                server_name=name,
                url=str(spec["url"]),
            )
        return built

    async def mcp_configs_for_user(self, user_id: int) -> dict[str, Any]:
        if not self._repo.connector_feature_allows(user_id):
            return {}
        configs: dict[str, Any] = {}
        for inst in self._repo.list_visible(user_id):
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
        for parent in self._repo.list_by_kind(CUSTOM_MCP_KIND):
            if parent.user_id == user_id or not parent.has_credentials:
                continue
            servers = extract_servers(self.decrypt(parent.instance_id))
            if any(
                isinstance(spec, dict) and spec.get("shared") is True for spec in servers.values()
            ):
                await self.ensure_fresh_custom_servers(parent.user_id)
        configs.update(self.custom_harness_configs(user_id))
        return configs

    def verify_internal_token(self, instance_id: str, token: str) -> dict[str, Any] | None:
        creds = self.decrypt(instance_id)
        expected = str(creds.get("internal_token") or "")
        if not expected or expected != token:
            return None
        return creds

    async def agently_auth_for_instance(
        self,
        instance_id: str,
        user_id: int,
        action: agently_auth.AuthAction,
        *,
        locale: str = "en",
    ) -> agently_auth.AuthResult:
        locks = _AGENTLY_LOCKS.setdefault(self._repo, {})
        async with locks.setdefault(instance_id, asyncio.Lock()):
            inst = self._repo.get(instance_id)
            if inst is None:
                raise OctopError.localized(ErrorCode.CONNECTOR_NOT_FOUND, locale)
            if inst.user_id != user_id:
                raise OctopError.localized(ErrorCode.FORBIDDEN, locale)
            if inst.kind not in ("agently-cli", "dingtalk-cli"):
                raise OctopError.localized(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, locale)
            creds = self.decrypt(instance_id)
            creds.setdefault("instance_id", instance_id)
            result = await agently_auth.authorize(creds, action, kind=inst.kind, locale=locale)
            if action == "disconnect" and result["status"] == "idle":
                self._repo.delete(instance_id)
            return result

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


async def _token_rejected(url: str, headers: dict[str, str], *, kind: str) -> bool:
    """True only when the MCP server answers 401/403; anything else is not an auth problem."""
    if not url:
        return False
    from octop.infra.connectors.probe import probe_streamable_http_mcp

    try:
        result = await asyncio.wait_for(
            probe_streamable_http_mcp(url, headers, kind=kind), timeout=30
        )
    except Exception:
        logger.warning("auth probe failed for %s", kind, exc_info=True)
        return False
    return result.get("error_type") == "auth"
