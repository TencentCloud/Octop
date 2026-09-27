"""HTTP surface for a project's connector declarations (PLAN.md §1.4).

Two routes: read the declared kinds **with each one resolved for the caller**, and
replace the whole set. The resolution result is what makes "declared but not
usable for me" visible instead of silently doing nothing.

`tags` / mount registration belong to the integration task (T-INT2); these
handlers carry their own ``summary``, typed ``response_model`` and permission
gate, which is what the OpenAPI contract test asserts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.projects.connectors import ProjectConnectorService, ResolvedConnector
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


class ConnectorDeclarationOut(BaseModel):
    """One declared kind plus its resolution **for the calling user**."""

    kind: str
    available: bool = Field(description="False when this user has no active instance of that kind.")
    resolved_instance_id: str | None = Field(
        description="The instance that would be used; always the caller's own."
    )
    display_name: str | None = Field(description="That instance's display name.")

    @classmethod
    def of(cls, resolved: ResolvedConnector) -> ConnectorDeclarationOut:
        return cls(
            kind=resolved.kind,
            available=resolved.available,
            resolved_instance_id=resolved.resolved_instance_id,
            display_name=resolved.display_name,
        )


class ConnectorKindsIn(BaseModel):
    kinds: list[str] = Field(
        default_factory=list,
        description="The project's complete connector kind set; omitted kinds are removed.",
    )


def _service(server: OctopServer) -> ProjectConnectorService:
    assert server.services is not None
    return ProjectConnectorService(server.services)


@router.get(
    "/{project_id}/connectors",
    summary="List a project's connector declarations",
    response_model=list[ConnectorDeclarationOut],
)
async def list_project_connectors(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[ConnectorDeclarationOut]:
    """Declared connector kinds, each resolved against the **caller's** instances.

    A kind with no usable instance is still returned, with ``available=false``:
    that is a UI state, not an error.
    """
    resolved = _service(server).list_connectors(project_id, user=user)
    return [ConnectorDeclarationOut.of(item) for item in resolved]


@router.put(
    "/{project_id}/connectors",
    summary="Replace a project's connector declarations",
    response_model=list[ConnectorDeclarationOut],
)
async def replace_project_connectors(
    project_id: str,
    body: ConnectorKindsIn,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[ConnectorDeclarationOut]:
    """Full replacement: the body is the project's whole declaration set.

    An unknown kind is a 400; the same kind twice in one request is a 409. The
    response resolves every surviving kind for the caller.
    """
    resolved = _service(server).replace_connectors(project_id, user=user, kinds=body.kinds)
    return [ConnectorDeclarationOut.of(item) for item in resolved]
