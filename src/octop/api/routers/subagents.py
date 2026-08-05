"""Subagents router — per-agent ``agents/**/*.md`` definitions and bundled catalog.

Each agent's subagents live under its harness workspace at
``agents/<slug>.md``. This router exposes summaries for the dashboard;
editing uses the workspace file API (``PUT .../workspace/file``) and
``POST .../reload`` to recompile the graph.

Catalog (bundled agency-agents library):

  GET  /api/subagent-catalog/divisions
  GET  /api/subagent-catalog
  GET  /api/subagent-catalog/{slug}

Per-agent:

  GET  /api/agents/{aid}/subagents
  POST /api/agents/{aid}/subagents/install
"""
# ruff: noqa: UP006,UP007  (modern X | None annotations throughout)

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_row
from octop.api.common.workspace import require_running_workspace
from octop.api.deps import current_user, get_server
from octop.infra.agents.subagents.catalog import SubagentDefinition
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import (
    Locale,
    normalize_locale,
    resolve_request_locale,
    resolve_user_locale,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class InstallSubagentBody(BaseModel):
    slug: str = Field(..., min_length=1, description="Catalog slug (from frontmatter name)")
    locale: str | None = Field(
        default=None,
        description="Override the installed language (zh|en). Defaults to the caller's locale.",
    )


def _localized_text(defn: SubagentDefinition, field: str) -> dict[str, str]:
    getter = defn.name_for if field == "name" else defn.description_for
    out: dict[str, str] = {}
    for loc in defn.summary.available_locales:
        val = getter(loc)
        if val:
            out[loc] = val
    return out


def _summary_dict(defn: SubagentDefinition) -> dict[str, Any]:
    s = defn.summary
    return {
        "slug": s.slug,
        "division": s.division,
        "name": _localized_text(defn, "name"),
        "description": _localized_text(defn, "description"),
        "emoji": s.emoji,
        "color": s.color,
        "source_path": s.source_path,
        "available_locales": list(s.available_locales),
    }


def _require_catalog(server: Any) -> Any:
    catalog = server.subagent_catalog
    if catalog is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "subagent catalog not loaded")
    return catalog


def _resolve_install_locale(
    *,
    user: Any,
    server: Any,
    request: Request,
    override: str | None,
) -> Locale:
    """Install locale: explicit override, then stored user preference, then request."""
    if override:
        return normalize_locale(override)
    if user is not None:
        return resolve_user_locale(
            user_repo=server.services.user_repo,
            user_id=int(getattr(user, "id", 0) or 0),
        )
    return resolve_request_locale(request)


@router.get("/subagent-catalog/divisions", summary="List subagent catalog divisions")
async def list_subagent_divisions(
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    catalog = _require_catalog(server)
    return cast(list[dict[str, Any]], catalog.list_divisions())


@router.get("/subagent-catalog", summary="List bundled subagent definitions")
async def list_subagent_catalog(
    division: str | None = Query(None, description="Filter by division id"),
    q: str | None = Query(None, description="Search name, description, or slug"),
    locale: str | None = Query(
        None,
        description="When set, only return agents available in this locale (zh|en).",
    ),
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    catalog = _require_catalog(server)
    locale_filter = normalize_locale(locale) if locale else None
    rows = catalog.list_summaries(division=division, query=q, locale=locale_filter)
    out: list[dict[str, Any]] = []
    for summary in rows:
        defn = catalog.get(summary.slug)
        if defn is not None:
            out.append(_summary_dict(defn))
    return out


@router.get("/subagent-catalog/{slug}", summary="Get bundled subagent definition")
async def get_subagent_catalog_item(
    slug: str,
    _: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    catalog = _require_catalog(server)
    item = catalog.get(slug)
    if item is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"subagent {slug!r} not found")
    contents: dict[str, str] = {}
    for loc in item.summary.available_locales:
        body = item.content_for(loc)
        if body:
            contents[loc] = body
    return {
        **_summary_dict(item),
        "content": contents,
    }


@router.get("/agents/{agent_id}/subagents", summary="List subagents")
async def list_subagents(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    return cast(list[dict[str, Any]], await registry.list_subagent_summaries(agent_id))


@router.post(
    "/agents/{agent_id}/subagents/install", status_code=201, summary="Install catalog subagent"
)
async def install_subagent(
    agent_id: str,
    body: InstallSubagentBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Copy a bundled subagent definition into the agent workspace ``agents/`` directory.

    The ``locale`` body field (or, when omitted, the caller's stored
    preference / ``Accept-Language``) decides which language version is
    installed. Missing translations fall back to English and are logged
    so translation progress can be tracked.
    """
    slug = body.slug.strip()
    if not slug or "/" in slug or slug.startswith("."):
        raise HTTPException(
            status_code=400,
            detail="slug is required and must not contain / or start with .",
        )

    catalog = _require_catalog(server)
    item = catalog.get(slug)
    if item is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"subagent {slug!r} not found")

    requested = _resolve_install_locale(
        user=user,
        server=server,
        request=request,
        override=body.locale,
    )
    available = item.summary.available_locales
    if requested not in available and "en" not in available:
        # No English fallback available — honor the requested locale
        # even if the slug has no translation yet, matching the catalog
        # behavior of returning whatever file is on disk.
        installed_locale = requested
    elif requested in available:
        installed_locale = requested
    else:
        installed_locale = "en"
    content = item.content_for(installed_locale)
    if installed_locale != requested:
        logger.info(
            "subagent %r: no %s translation available (have %s); installing en",
            slug,
            requested,
            ",".join(available) or "none",
        )

    workspace = await require_running_workspace(
        agent_id,
        user=user,
        as_user=as_user,
        server=server,
    )
    dest = f"agents/{slug}.md"
    await workspace.aupload_bytes(dest, content.encode("utf-8"))

    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.reload(agent_id)

    return {
        "installed": True,
        "slug": slug,
        "path": dest,
        "locale": installed_locale,
        "requested_locale": requested,
        "available_locales": list(available),
    }
