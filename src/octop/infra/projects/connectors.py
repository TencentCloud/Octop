"""Project connector declarations — the kind → instance resolution rule.

The contract is PLAN.md §1 (frozen):

* the project declares connector **kinds** only (never an instance id);
* resolution is per **current user**: the newest ``status='active'`` instance of
  that kind, ``id DESC`` — a user's other accounts are never silently broadcast;
* ``shared`` instances are excluded (a global primitive must not let one user's
  credentials serve another's project);
* "declared but not usable" is **not an error**: ``available=false`` with a 200,
  so the UI can grey it out (§1.2 S1/S2).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.db.repos.project_connectors import ProjectConnectorRepo
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import (
    PROJECT_MANAGE_CONFIG,
    PROJECT_READ,
    ProjectActor,
    ProjectService,
)

logger = logging.getLogger(__name__)

#: Instances in these states can serve a project declaration.
_ACTIVE_STATUS = "active"


def _connector_invalid(message: str, *, status: int = 0) -> OctopError:
    return OctopError(ErrorCode.PROJECT_CONNECTOR_INVALID, message, status=status)


@dataclass(frozen=True)
class ResolvedConnector:
    """One declaration plus what it resolves to **for this user**."""

    kind: str
    available: bool
    resolved_instance_id: str | None
    display_name: str | None


class ProjectConnectorService:
    def __init__(
        self,
        services: SharedServices,
        *,
        project_service: ProjectService | None = None,
        repo: ProjectConnectorRepo | None = None,
    ) -> None:
        self._services = services
        self._projects = project_service or ProjectService(services)
        # Injectable for tests; production reads the registered RepoBundle entry.
        self._repo = repo or services.project_connector_repo

    # ── rules ────────────────────────────────────────────────────────────────

    def known_kinds(self) -> list[str]:
        """The catalog's kind vocabulary (PLAN.md §1.1: the single source)."""
        from octop.infra.connectors.catalog import list_catalog  # noqa: PLC0415 - cycle-safe

        return [entry.kind for entry in list_catalog()]

    def assert_kind_known(self, kind: str) -> None:
        if get_catalog_entry(kind) is None:
            raise _connector_invalid(f"Unknown connector kind: {kind!r}")

    def resolve_connector_kind(
        self, project_id: str, kind: str, user: ProjectActor
    ) -> ResolvedConnector | None:
        """Newest active, non-shared instance of *kind* owned by *user*, or ``None``.

        Returning ``None`` means "not usable by you" — deliberately not an error:
        the declaration stands, the UI greys it out (PLAN.md §1.2 S1/S2).
        """
        candidates = [
            row
            for row in self._services.connector_repo.list_by_user(user.id)
            if row.kind == kind and row.status == _ACTIVE_STATUS and not row.shared
        ]
        if not candidates:
            return None
        newest = max(candidates, key=lambda row: row.id)
        return ResolvedConnector(
            kind=kind,
            available=True,
            resolved_instance_id=newest.instance_id,
            display_name=newest.display_name,
        )

    def _resolve_declared(
        self, project_id: str, kinds: Sequence[str], user: ProjectActor
    ) -> list[ResolvedConnector]:
        out: list[ResolvedConnector] = []
        for kind in kinds:
            resolved = self.resolve_connector_kind(project_id, kind, user)
            out.append(
                resolved
                or ResolvedConnector(
                    kind=kind, available=False, resolved_instance_id=None, display_name=None
                )
            )
        return out

    # ── interface ────────────────────────────────────────────────────────────

    def list_connectors(self, project_id: str, *, user: ProjectActor) -> list[ResolvedConnector]:
        """Declared kinds with each one resolved for the **calling** user."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        kinds = [row.kind for row in self._repo.list_by_project(project_id)]
        return self._resolve_declared(project_id, kinds, user)

    def replace_connectors(
        self, project_id: str, *, user: ProjectActor, kinds: Sequence[object]
    ) -> list[ResolvedConnector]:
        """Full replacement (S11): duplicates are a 409, omitted kinds are removed."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)
        wanted = [str(kind).strip() for kind in kinds]
        if any(not kind for kind in wanted):
            raise _connector_invalid("A connector kind must not be empty.")
        if len(set(wanted)) != len(wanted):
            raise _connector_invalid("The same connector kind was sent twice.", status=409)
        for kind in wanted:
            self.assert_kind_known(kind)
        rows = self._repo.replace_all(project_id, wanted, created_by=user.id)
        return self._resolve_declared(project_id, [row.kind for row in rows], user)
