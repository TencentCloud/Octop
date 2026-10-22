"""User-scoped installation of built-in connectors from local CLI clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from octop.i18n import tr
from octop.infra.connectors.builder import mcp_server_name
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.default_open import build_instance_config_json
from octop.infra.connectors.open_design import normalize_credentials
from octop.infra.connectors.service import ConnectorService
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.db.repos.connectors import ConnectorRow
    from octop.infra.db.services import SharedServices


class ConnectorInstaller:
    """Install or remove one owned OpenDesign instance, preserving its identity."""

    def __init__(self, services: SharedServices, *, user_id: int, locale: str) -> None:
        self._services, self._user_id, self._locale = services, user_id, locale
        self._repo = services.connector_repo
        self._service = ConnectorService(
            repo=self._repo,
            secret_repo=services.secret_repo,
            settings_repo=services.settings_repo,
            config=services.config,
        )

    def _find(self, kind: str, name: str) -> ConnectorRow | None:
        if kind != "open-design":
            raise OctopError.localized(ErrorCode.CONNECTOR_KIND_UNSUPPORTED, locale=self._locale)
        if not name.strip():
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                tr("connector.install.invalid_name", self._locale),
            )
        matches = [
            row for row in self._repo.list_by_user(self._user_id) if row.display_name == name
        ]
        if len(matches) > 1 or (matches and matches[0].kind != kind):
            raise OctopError.localized(ErrorCode.CONNECTOR_NAME_TAKEN, locale=self._locale)
        if not matches and any(
            item["display_name"] == name
            and int(item.get("owner_user_id") or self._user_id) == self._user_id
            for item in self._service.list_instances_for_api(self._user_id)
        ):
            raise OctopError.localized(ErrorCode.CONNECTOR_NAME_TAKEN, locale=self._locale)
        return matches[0] if matches else None

    @staticmethod
    def _result(row: ConnectorRow | None, *, action: str) -> dict[str, Any]:
        return {
            "ok": True,
            "action": action,
            "installed": row is not None,
            "instance_id": row.instance_id if row else None,
            "kind": row.kind if row else "open-design",
            "name": row.display_name if row else None,
            "mcp_server_name": row.mcp_server_name if row else None,
        }

    def get(self, kind: str, name: str) -> dict[str, Any]:
        """Return registration metadata without credentials or environment values."""
        row = self._find(kind, name)
        if row is None:
            raise OctopError.localized(ErrorCode.CONNECTOR_NOT_FOUND, locale=self._locale)
        return self._result(row, action="get")

    def install(self, kind: str, name: str, config: dict[str, Any]) -> dict[str, Any]:
        """Validate, encrypt and upsert an owned instance; never execute its command."""
        row = self._find(kind, name)
        try:
            credentials = normalize_credentials(config)
        except ValueError as exc:
            raise OctopError(
                ErrorCode.CONNECTOR_INVALID_CREDENTIALS,
                tr("connector.install.invalid_config", self._locale),
            ) from exc
        instance_id = row.instance_id if row else new_ulid()
        if row is None:
            entry = get_catalog_entry(kind)
            assert entry is not None
            self._repo.create(
                instance_id=instance_id,
                user_id=self._user_id,
                kind=kind,
                display_name=name,
                mcp_server_name=mcp_server_name(kind, instance_id),
                config_json=build_instance_config_json(
                    kind=kind,
                    default_open=False,
                    description=entry.description.resolve(self._locale),
                ),
            )
        self._service.encrypt_and_store(instance_id=instance_id, payload=credentials)
        self._repo.update_status(instance_id, "active")
        self._services.audit_repo.write(
            actor=str(self._user_id),
            action="connector.cli.install",
            target=instance_id,
            payload=kind,
        )
        return self._result(self._repo.get(instance_id), action="updated" if row else "created")

    def remove(self, kind: str, name: str) -> dict[str, Any]:
        """Remove only the matching owned instance; missing instances are a no-op."""
        row = self._find(kind, name)
        if row is not None:
            self._repo.delete(row.instance_id)
            self._services.audit_repo.write(
                actor=str(self._user_id),
                action="connector.cli.remove",
                target=row.instance_id,
                payload=kind,
            )
        result = self._result(None, action="removed" if row else "absent")
        result["name"] = name
        return result
