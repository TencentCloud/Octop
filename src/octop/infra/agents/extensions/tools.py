"""LangChain tools available only to the Octop Extension Builder expert."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.infra.agents.extensions.catalog import ExtensionCatalog
from octop.infra.agents.extensions.service import ExtensionBuilderService


def _result(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _error(exc: Exception) -> str:
    return _result({"error": str(exc)})


def _require_owner(*, agent_id: str, owner_user_id: int | None) -> None:
    cfg = get_config().get("configurable") or {}
    current_agent_id = str(cfg.get("agent_id") or "")
    current_user = cfg.get("user")
    if current_agent_id != agent_id or owner_user_id is None or current_user is None:
        raise ValueError("extension builder context is unavailable")
    if int(current_user) != owner_user_id:
        raise ValueError("only the extension builder owner can create artifacts")


def build_extension_builder_tools(
    workspace: Any,
    *,
    agent_id: str,
    owner_user_id: int | None,
    catalog: ExtensionCatalog | None = None,
) -> list[StructuredTool]:
    """Return safe draft tools for one Extension Builder agent."""
    service = ExtensionBuilderService(
        workspace,
        catalog=catalog,
        owner_user_id=owner_user_id,
    )

    async def octop_extension_scaffold(
        artifact_type: Annotated[
            str,
            Field(description="Artifact type: skill, plugin, or hybrid."),
        ],
        slug: Annotated[
            str,
            Field(description="Lowercase artifact identifier with letters, digits, and hyphens."),
        ],
        goal: Annotated[
            str,
            Field(description="Short statement of the user-visible capability to create."),
        ],
    ) -> str:
        try:
            _require_owner(agent_id=agent_id, owner_user_id=owner_user_id)
            return _result(
                await service.scaffold(artifact_type=artifact_type, slug=slug, goal=goal)
            )
        except Exception as exc:
            return _error(exc)

    async def octop_extension_validate(
        project_id: Annotated[str, Field(description="Project id returned by scaffold.")],
    ) -> str:
        try:
            _require_owner(agent_id=agent_id, owner_user_id=owner_user_id)
            return _result(await service.validate(project_id))
        except Exception as exc:
            return _error(exc)

    async def octop_extension_package(
        project_id: Annotated[str, Field(description="Validated extension project id.")],
        expected_revision: Annotated[
            str,
            Field(description="Exact source revision returned by the latest validation."),
        ],
    ) -> str:
        try:
            _require_owner(agent_id=agent_id, owner_user_id=owner_user_id)
            return _result(await service.package(project_id, expected_revision=expected_revision))
        except Exception as exc:
            return _error(exc)

    return [
        StructuredTool.from_function(
            coroutine=octop_extension_scaffold,
            name="octop_extension_scaffold",
            description=(
                "Create a safe Octop Skill, Plugin, or hybrid draft in the current builder "
                "workspace. The draft contains placeholders and is not installed."
            ),
        ),
        StructuredTool.from_function(
            coroutine=octop_extension_validate,
            name="octop_extension_validate",
            description=(
                "Validate an Octop extension draft without importing or executing generated code."
            ),
        ),
        StructuredTool.from_function(
            coroutine=octop_extension_package,
            name="octop_extension_package",
            description=(
                "Package a valid Octop extension draft as a ZIP and publish it to the owner's "
                "private catalog. The source revision must match the latest validation. "
                "Packaging does not install or activate the artifact."
            ),
        ),
    ]
