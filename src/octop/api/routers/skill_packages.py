"""HTTP API for instance-global skill packages."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from octop.api.common.content_disposition import content_disposition
from octop.api.common.workspace import coerce_read_content
from octop.api.deps import get_server, require_permission
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    SkillHubMarketErrorKind,
)
from octop.infra.db.repos.skill_packages import SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.skills.install import valid_skillhub_icon_url
from octop.infra.skills.skill_archive import build_skills_zip
from octop.infra.skills.skill_package_from_skillhub import create_package_from_skillhub
from octop.infra.skills.skill_package_store import (
    SkillPackageStore,
    is_skill_package_name_conflict,
    raise_skill_package_name_taken,
)
from octop.infra.skills.skill_packages import SkillPackageError, read_skill_directory
from octop.infra.skills.skillhub_market import SkillHubMarketError as SkillHubDownloadError
from octop.infra.users.groups import (
    RESOURCE_SKILL_PACKAGE,
    GroupAccess,
)
from octop.infra.users.identity import User
from octop.infra.utils.frontmatter import parse_frontmatter
from octop.infra.utils.locale import Locale, resolve_request_locale

router = APIRouter(prefix="/skill-packages")

_SAFE_SKILLHUB_REASONS: dict[SkillHubMarketErrorKind, str] = {
    SkillHubMarketErrorKind.NOT_FOUND: "skillset not found",
    SkillHubMarketErrorKind.INVALID_SLUG: "invalid skillset id",
    SkillHubMarketErrorKind.UPSTREAM_TIMEOUT: "upstream timeout",
    SkillHubMarketErrorKind.UPSTREAM_BAD_PAYLOAD: "invalid upstream response",
    SkillHubMarketErrorKind.PACKAGE_INVALID: "invalid skillset package",
    SkillHubMarketErrorKind.PACKAGE_TOO_LARGE: "skillset package too large",
    SkillHubMarketErrorKind.UPSTREAM_FAILED: "upstream request failed",
    SkillHubMarketErrorKind.SSL_ERROR: "ssl error",
}


class CreateSkillPackageBody(BaseModel):
    name: str
    description: str = ""
    icon_name: str = ""
    icon_url: str = ""
    shared: bool = False
    visibility: Literal["all", "groups", "owner"] | None = None
    group_ids: list[str] | None = None
    copy_policy: Literal["snapshot", "lock", "deny"] = "snapshot"
    allow_download: bool = True


class UpdateSkillPackageBody(BaseModel):
    name: str | None = None
    description: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    shared: bool | None = None
    copy_policy: Literal["snapshot", "lock", "deny"] | None = Field(
        default=None,
        description=(
            "Controls copying package skills into an agent workspace for users who "
            "can already view the package (including the owner's other experts)."
        ),
    )
    allow_download: bool | None = Field(
        default=None,
        description="When false, non-owner users who can view the package cannot export a ZIP.",
    )
    visibility: Literal["all", "groups", "owner"] | None = None
    group_ids: list[str] | None = None


class FromSkillHubBody(BaseModel):
    slug: str
    name: str | None = None
    description: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None
    shared: bool = False


class SkillFilePart(BaseModel):
    path: str
    content_base64: str


class CreatePackageSkillBody(BaseModel):
    name: str
    content: str = ""
    files: list[SkillFilePart] | None = None
    overwrite: bool = False


class UpdatePackageSkillBody(BaseModel):
    content: str = ""
    files: list[SkillFilePart] | None = None


class ImportPackageSkillBody(BaseModel):
    bundle_url: str
    version: str = ""
    overwrite: bool = False


def _files_from_package_skill_body(
    *,
    content: str,
    files: list[SkillFilePart] | None,
) -> list[tuple[str, bytes]]:
    if files:
        decoded: list[tuple[str, bytes]] = []
        for part in files:
            try:
                decoded.append((part.path, base64.b64decode(part.content_base64, validate=True)))
            except Exception as exc:
                raise OctopError(
                    ErrorCode.SLASH_BAD_ARGS,
                    f"invalid base64 content for {part.path!r}",
                ) from exc
        return decoded
    if not content:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "content or files is required")
    return [("SKILL.md", content.encode("utf-8"))]


def _package_skill_exists(store: SkillPackageStore, package_id: str, slug: str) -> bool:
    return (store.package_skills_dir(package_id) / slug / "SKILL.md").is_file()


class LocalizedSkillCopy(BaseModel):
    zh: str | None = None
    en: str | None = None


class HubInstallPackageSkillBody(BaseModel):
    skill_name: str
    display_name: str | None = None
    icon_url: str | None = None
    label: LocalizedSkillCopy | None = None
    summary: LocalizedSkillCopy | None = None
    overwrite: bool = False


def _store(server: OctopServer) -> SkillPackageStore:
    if server.services is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "skill package store not initialized")
    return SkillPackageStore(
        repo=server.services.skill_package_repo,
        root=server.paths.skill_packages_dir,
    )


def _package_or_404(
    store: SkillPackageStore,
    package_id: str,
    *,
    locale: str,
) -> SkillPackageRow:
    row = store.repo.get(package_id)
    if row is None:
        raise OctopError.localized(ErrorCode.SKILL_PACKAGE_NOT_FOUND, locale)
    return row


def _package_avatar_api_path(package_id: str) -> str:
    return f"/api/skill-packages/{package_id}/avatar"


def _is_package_avatar_url(value: str, package_id: str | None = None) -> bool:
    path = value.strip().split("?", 1)[0]
    if package_id:
        return path == _package_avatar_api_path(package_id)
    return path.startswith("/api/skill-packages/") and path.endswith("/avatar")


def _display_package_icon_url(server: OctopServer, row: SkillPackageRow) -> str:
    from octop.infra.users.profile_avatar import profile_avatar_url  # noqa: PLC0415

    text = str(row.icon_url or "").strip()
    api = _package_avatar_api_path(row.id)
    if text.split("?", 1)[0] == api:
        return profile_avatar_url(server.paths.skill_package_avatars_dir, row.id, api) or api
    return text


def _row_public_dict(server: OctopServer, row: SkillPackageRow) -> dict[str, Any]:
    payload = asdict(row)
    payload.pop("pk", None)
    payload["icon_url"] = _display_package_icon_url(server, row)
    return payload


def _package_payload(
    store: SkillPackageStore,
    row: SkillPackageRow,
    *,
    locale: Locale | None = None,
    server: OctopServer | None = None,
) -> dict[str, Any]:
    if server is None:
        payload = asdict(row)
        payload.pop("pk", None)
    else:
        payload = _row_public_dict(server, row)
    return {
        **payload,
        "skills": store.list_skill_summaries(row.id, locale=locale),
    }


def _package_access(server: OctopServer) -> GroupAccess:
    assert server.services is not None
    return GroupAccess(server.services.repos)


def _package_owner(user: User, row: SkillPackageRow) -> bool:
    return str(user.id) == str(row.created_by)


def _creator_fields(server: OctopServer, created_by: str) -> dict[str, str | None]:
    raw = str(created_by or "").strip()
    if not raw.isdigit():
        return {"creator_username": None, "creator_display_name": None}
    if server.services is None:
        return {"creator_username": None, "creator_display_name": None}
    owner = server.services.user_repo.get(int(raw))
    if owner is None:
        return {"creator_username": None, "creator_display_name": None}
    return {
        "creator_username": owner.username,
        "creator_display_name": owner.display_name or owner.username,
    }


def _package_payload_with_creator(
    server: OctopServer,
    store: SkillPackageStore,
    row: SkillPackageRow,
    *,
    locale: Locale | None = None,
) -> dict[str, Any]:
    return {
        **_package_payload(store, row, locale=locale, server=server),
        **_creator_fields(server, row.created_by),
    }


def _required(value: str, field: str) -> str:
    value = value.strip()
    if not value:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"{field} is required")
    return value


def _icon_url(value: str, *, package_id: str | None = None) -> str:
    value = value.strip()
    if len(value) > 2048:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "icon_url is too long")
    if (
        value
        and not valid_skillhub_icon_url(value)
        and not _is_package_avatar_url(value, package_id)
    ):
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            "icon_url must be an HTTP(S) URL or package avatar path",
        )
    return value


def _visible_packages(store: SkillPackageStore, user: User) -> list[SkillPackageRow]:
    if user.is_admin:
        return store.repo.list_all()
    return store.repo.list_visible(user.id)


def _assert_group_visible(
    server: OctopServer,
    user: User,
    row: SkillPackageRow,
    *,
    locale: str,
) -> None:
    """User groups only narrow packages the shared flag already exposes."""
    if _package_access(server).allows(
        user_id=user.id,
        is_admin=user.is_admin,
        resource_type=RESOURCE_SKILL_PACKAGE,
        resource_key=row.id,
        is_owner=_package_owner(user, row),
    ):
        return
    raise OctopError.localized(ErrorCode.SKILL_PACKAGE_NOT_FOUND, locale)


def _package_visible_or_404(
    store: SkillPackageStore,
    package_id: str,
    user: User,
    server: OctopServer,
    *,
    locale: str,
) -> SkillPackageRow:
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_view(row, user)
    _assert_group_visible(server, user, row, locale=locale)
    return row


def _map_skillhub_error(exc: BaseException) -> OctopError:
    kind = getattr(exc, "kind", SkillHubMarketErrorKind.UPSTREAM_FAILED)
    if kind in (
        SkillHubMarketErrorKind.NOT_FOUND,
        SkillHubMarketErrorKind.INVALID_SLUG,
    ):
        return OctopError(ErrorCode.NOT_FOUND, "skillhub skillset not found")
    if kind == SkillHubMarketErrorKind.SSL_ERROR:
        return OctopError(
            ErrorCode.SKILLHUB_SSL_FAILED,
            "skillhub ssl error",
            details={"reason": "ssl_error", "kind": kind.value},
        )
    reason = _SAFE_SKILLHUB_REASONS.get(
        kind,
        _SAFE_SKILLHUB_REASONS[SkillHubMarketErrorKind.UPSTREAM_FAILED],
    )
    return OctopError(
        ErrorCode.EXPERT_MARKET_FAILED,
        f"skillhub market failed: {reason}",
        details={"reason": reason, "kind": kind.value},
    )


def _package_skill_or_404(
    store: SkillPackageStore,
    package_id: str,
    slug: str,
    *,
    locale: Locale | None = None,
) -> dict[str, Any]:
    for skill in store.list_skill_summaries(
        package_id,
        locale=locale,
    ):
        if skill["slug"] == slug:
            return skill
    raise OctopError(ErrorCode.NOT_FOUND, f"skill {slug!r} not found")


@router.get("", summary="List global skill packages")
async def list_skill_packages(
    writable_only: bool = False,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    store = _store(server)
    access = _package_access(server)
    rows = access.filter_rows(
        _visible_packages(store, user),
        user_id=user.id,
        is_admin=user.is_admin,
        resource_type=RESOURCE_SKILL_PACKAGE,
        key_of=lambda row: row.id,
        is_owner=lambda row: _package_owner(user, row),
    )
    return [
        {
            **_row_public_dict(server, row),
            **_creator_fields(server, row.created_by),
            **access.visibility(RESOURCE_SKILL_PACKAGE, row.id, shared=bool(row.shared)),
            "can_write": store.can_mutate(row, user),
            "can_copy": store.can_copy(row, user),
            "can_download": store.can_download(row, user),
        }
        for row in rows
        if not writable_only or store.can_mutate(row, user)
    ]


@router.get("/hub/search", summary="Search SkillHub for installing into packages")
async def package_hub_search(
    q: str = "",
    limit: int = 50,
    _user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    from fastapi import HTTPException  # noqa: PLC0415

    from octop.infra.skills.skillhub_market import (  # noqa: PLC0415
        SkillHubMarketError,
        search_skillhub,
    )

    query = q.strip() or "a"
    effective_limit = max(1, min(limit, 100))
    try:
        return await search_skillhub(query, limit=effective_limit)
    except SkillHubMarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/hub/rankings", summary="SkillHub rankings for installing into packages")
async def package_hub_rankings(
    type: str = "all",
    _user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    from fastapi import HTTPException  # noqa: PLC0415

    from octop.infra.skills.skillhub_market import (  # noqa: PLC0415
        SkillHubMarketError,
        SkillHubMarketTimeout,
        fetch_skillhub_rankings,
    )

    ranking_types = {"all", "hot", "featured", "newest", "recommended", "trending", "paid"}
    rtype = type if type in ranking_types else "all"
    try:
        return await fetch_skillhub_rankings(rtype)
    except SkillHubMarketTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except SkillHubMarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("", summary="Create a global skill package")
async def create_skill_package(
    body: CreateSkillPackageBody,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    name = _required(body.name, "name")
    try:
        shared = bool(body.shared)
        if body.visibility == "owner":
            shared = False
        elif body.visibility in {"all", "groups"}:
            shared = True
        row = store.create(
            name=name,
            description=body.description.strip(),
            created_by=str(user.id),
            icon_name=body.icon_name.strip(),
            icon_url=_icon_url(body.icon_url),
            shared=shared,
            copy_policy=body.copy_policy,
            allow_download=bool(body.allow_download),
        )
    except Exception as exc:
        if is_skill_package_name_conflict(exc):
            raise_skill_package_name_taken(name)
        raise
    if body.visibility is not None:
        _package_access(server).set_visibility(
            RESOURCE_SKILL_PACKAGE,
            row.id,
            body.visibility,
            body.group_ids,
        )
    return {
        **_package_payload_with_creator(server, store, row),
        **_package_access(server).visibility(
            RESOURCE_SKILL_PACKAGE, row.id, shared=bool(row.shared)
        ),
    }


@router.post(
    "/from-skillhub",
    status_code=status.HTTP_201_CREATED,
    summary="Create a skill package from a SkillHub skillset",
)
async def create_from_skillhub(
    body: FromSkillHubBody,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    try:
        result = await asyncio.to_thread(
            create_package_from_skillhub,
            store,
            slug=_required(body.slug, "slug"),
            created_by=str(user.id),
            name=body.name.strip() if body.name is not None else None,
            description=body.description.strip() if body.description is not None else None,
            icon_name=body.icon_name.strip() if body.icon_name is not None else None,
            icon_url=_icon_url(body.icon_url) if body.icon_url is not None else None,
            shared=bool(body.shared),
        )
    except (SkillHubMarketError, SkillHubDownloadError) as exc:
        raise _map_skillhub_error(exc) from exc
    payload = _package_payload_with_creator(server, store, result.row)
    if result.skipped_slugs:
        payload["skipped_skills"] = list(result.skipped_slugs)
    return payload


@router.get("/{package_id}", summary="Get a global skill package and its skills")
async def get_skill_package(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    locale = resolve_request_locale(request)
    row = _package_visible_or_404(store, package_id, user, server, locale=locale)
    return {
        **_package_payload_with_creator(
            server,
            store,
            row,
            locale=locale,
        ),
        **_package_access(server).visibility(
            RESOURCE_SKILL_PACKAGE, row.id, shared=bool(row.shared)
        ),
        "can_write": store.can_mutate(row, user),
        "can_copy": store.can_copy(row, user),
        "can_download": store.can_download(row, user),
    }


@router.patch("/{package_id}", summary="Update global skill package metadata")
async def update_skill_package(
    package_id: str,
    body: UpdateSkillPackageBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    locale = resolve_request_locale(request)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_mutate(row, user)
    name = _required(body.name, "name") if body.name is not None else None
    description = body.description.strip() if body.description is not None else None
    icon_name = body.icon_name.strip() if body.icon_name is not None else None
    icon_url = (
        _icon_url(body.icon_url, package_id=package_id) if body.icon_url is not None else None
    )
    shared_value = None if body.shared is None else int(body.shared)
    if body.visibility == "owner":
        shared_value = 0
    elif body.visibility in {"all", "groups"}:
        shared_value = 1
    try:
        store.repo.update(
            package_id,
            name=name,
            description=description,
            icon_name=icon_name,
            icon_url=icon_url,
            copy_policy=body.copy_policy,
            allow_download=None if body.allow_download is None else int(body.allow_download),
            shared=shared_value,
        )
    except Exception as exc:
        if name is not None and is_skill_package_name_conflict(exc):
            raise_skill_package_name_taken(name)
        raise
    if icon_url is not None and not _is_package_avatar_url(icon_url, package_id):
        from octop.infra.users.profile_avatar import delete_profile_avatar  # noqa: PLC0415

        delete_profile_avatar(server.paths.skill_package_avatars_dir, package_id)
    if body.visibility is not None:
        _package_access(server).set_visibility(
            RESOURCE_SKILL_PACKAGE,
            package_id,
            body.visibility,
            body.group_ids,
        )
    updated = _package_or_404(store, package_id, locale=locale)
    return {
        **_package_payload_with_creator(
            server,
            store,
            updated,
            locale=locale,
        ),
        **_package_access(server).visibility(
            RESOURCE_SKILL_PACKAGE, package_id, shared=bool(updated.shared)
        ),
    }


@router.delete(
    "/{package_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a global skill package"
)
async def delete_skill_package(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> None:
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    store.delete_package(package_id)
    from octop.infra.users.profile_avatar import delete_profile_avatar  # noqa: PLC0415

    delete_profile_avatar(server.paths.skill_package_avatars_dir, package_id)
    _package_access(server).clear(RESOURCE_SKILL_PACKAGE, package_id)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.strip_skill_package_id(package_id)


@router.post(
    "/{package_id}/avatar",
    status_code=201,
    summary="Upload a skill-package portrait",
)
async def upload_skill_package_avatar(
    package_id: str,
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, str]:
    from octop.infra.users.profile_avatar import (  # noqa: PLC0415
        profile_avatar_url,
        write_profile_avatar,
    )

    store = _store(server)
    locale = resolve_request_locale(request)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_mutate(row, user)
    write_profile_avatar(
        server.paths.skill_package_avatars_dir,
        package_id,
        await file.read(),
    )
    icon_url = _package_avatar_api_path(package_id)
    store.repo.update(package_id, icon_url=icon_url)
    display = (
        profile_avatar_url(server.paths.skill_package_avatars_dir, package_id, icon_url) or icon_url
    )
    return {"icon_url": display}


@router.get("/{package_id}/avatar", summary="Read a skill-package portrait")
async def get_skill_package_avatar(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> Response:
    from octop.infra.users.profile_avatar import avatar_response  # noqa: PLC0415

    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    return avatar_response(server.paths.skill_package_avatars_dir, package_id)


@router.delete(
    "/{package_id}/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a skill-package portrait",
)
async def delete_skill_package_avatar(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> None:
    from octop.infra.users.profile_avatar import delete_profile_avatar  # noqa: PLC0415

    store = _store(server)
    locale = resolve_request_locale(request)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_mutate(row, user)
    delete_profile_avatar(server.paths.skill_package_avatars_dir, package_id)
    store.repo.update(package_id, icon_url="")


@router.get("/{package_id}/skills", summary="List skills in a global skill package")
async def list_package_skills(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    return store.list_skill_summaries(package_id, locale=locale)


@router.get("/{package_id}/skills/{slug}", summary="Get a global package skill")
async def get_package_skill(
    package_id: str,
    slug: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    skill = _package_skill_or_404(store, package_id, slug, locale=locale)
    raw = (store.package_skills_dir(package_id) / slug / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)
    return {**skill, "frontmatter": frontmatter, "body": body, "raw": raw}


@router.get(
    "/{package_id}/skills/{slug}/tree",
    summary="List files under a global package skill path",
)
async def list_package_skill_tree(
    package_id: str,
    slug: str,
    request: Request,
    path: str = Query(default="", description="Path relative to the skill root"),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    _package_skill_or_404(store, package_id, slug, locale=locale)
    return await asyncio.to_thread(store.list_skill_tree, package_id, slug, path)


@router.get(
    "/{package_id}/skills/{slug}/file",
    summary="Read a UTF-8 text file from a global package skill",
)
async def read_package_skill_file(
    package_id: str,
    slug: str,
    path: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    _package_skill_or_404(store, package_id, slug, locale=locale)
    content = await asyncio.to_thread(store.read_skill_file_text, package_id, slug, path)
    return {"path": path, "content": coerce_read_content(content)}


@router.get(
    "/{package_id}/skills/{slug}/download",
    summary="Download a file from a global package skill",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download_package_skill_file(
    package_id: str,
    slug: str,
    path: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> Response:
    store = _store(server)
    locale = resolve_request_locale(request)
    _package_visible_or_404(store, package_id, user, server, locale=locale)
    _package_skill_or_404(store, package_id, slug, locale=locale)
    payload = await asyncio.to_thread(store.read_skill_file_bytes, package_id, slug, path)
    fname = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "download.bin"
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition(fname)},
    )


def _read_package_skill_files(
    store: SkillPackageStore, package_id: str
) -> list[tuple[str, list[tuple[str, bytes]]]]:
    packed: list[tuple[str, list[tuple[str, bytes]]]] = []
    root = store.package_skills_dir(package_id)
    for summary in store.list_skill_summaries(package_id):
        if summary.get("corrupt"):
            continue
        slug = str(summary.get("slug") or "")
        packed.append((slug, read_skill_directory(root / slug)))
    if not packed:
        raise SkillPackageError("skill package has no skills")
    return packed


@router.get(
    "/{package_id}/export",
    summary="Download a skill package as a ZIP",
    description=(
        "Pack every skill in the package into one ZIP. Each skill is a top-level "
        "folder containing SKILL.md, matching the dashboard ZIP importer."
    ),
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_skill_package(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    _user: User = Depends(require_permission("skill_packages")),
) -> Response:
    store = _store(server)
    locale = resolve_request_locale(request)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_download(row, _user)
    _assert_group_visible(server, _user, row, locale=locale)
    try:
        packed = await asyncio.to_thread(_read_package_skill_files, store, package_id)
        payload = await asyncio.to_thread(build_skills_zip, packed)
    except SkillPackageError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
    filename = f"{(row.name or package_id).strip() or package_id}.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/{package_id}/skills", summary="Add a skill to a global skill package")
async def create_package_skill(
    package_id: str,
    body: CreatePackageSkillBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    slug = _required(body.name, "name")
    if _package_skill_exists(store, package_id, slug) and not body.overwrite:
        raise OctopError.localized(
            ErrorCode.SKILL_ALREADY_EXISTS,
            resolve_request_locale(request),
            name=slug,
        )
    store.write_skill(
        package_id,
        slug,
        _files_from_package_skill_body(content=body.content, files=body.files),
    )
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.refresh_agents_for_package(package_id)
    return _package_skill_or_404(store, package_id, slug)


@router.put("/{package_id}/skills/{slug}", summary="Replace a global package skill")
async def update_package_skill(
    package_id: str,
    slug: str,
    body: UpdatePackageSkillBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    """Update a package skill.

    A ``content``-only body (dashboard SKILL.md editor) rewrites just the
    manifest in place so sibling files and directories are preserved. A
    ``files`` payload replaces the whole skill directory.
    """
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    _package_skill_or_404(store, package_id, slug)
    # Truthiness mirrors ``_files_from_package_skill_body`` / workspace skills.
    if body.files:
        store.write_skill(
            package_id,
            slug,
            _files_from_package_skill_body(content=body.content, files=body.files),
        )
    else:
        if not body.content:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "content or files is required")
        store.write_skill_manifest(package_id, slug, body.content)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.refresh_agents_for_package(package_id)
    return _package_skill_or_404(store, package_id, slug)


@router.delete(
    "/{package_id}/skills/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a global package skill",
)
async def delete_package_skill(
    package_id: str,
    slug: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> None:
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    _package_skill_or_404(store, package_id, slug)
    store.delete_skill(package_id, slug)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.refresh_agents_for_package(package_id)


def _package_has_skill(store: SkillPackageStore, package_id: str, slug: str) -> bool:
    return (store.package_skills_dir(package_id) / slug / "SKILL.md").is_file()


async def _refresh_package(server: OctopServer, package_id: str) -> None:
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.refresh_agents_for_package(package_id)


class _PackageInstallTarget:
    """Install skills into a global skill package on disk."""

    def __init__(
        self,
        *,
        store: SkillPackageStore,
        package_id: str,
        server: OctopServer,
    ) -> None:
        self._store = store
        self._package_id = package_id
        self._server = server

    async def skill_exists(self, slug: str) -> bool:
        return _package_has_skill(self._store, self._package_id, slug)

    async def write_files(self, slug: str, files: list[tuple[str, bytes]]) -> None:
        self._store.write_skill(self._package_id, slug, files)

    async def after_install(self, slug: str, *, enable: bool | None = None) -> None:
        del slug, enable
        await _refresh_package(self._server, self._package_id)


@router.post(
    "/{package_id}/skills/import",
    status_code=status.HTTP_201_CREATED,
    summary="Import a skill URL into a global skill package",
)
async def import_package_skill(
    package_id: str,
    body: ImportPackageSkillBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    import asyncio  # noqa: PLC0415
    from urllib.error import HTTPError, URLError  # noqa: PLC0415

    from octop.infra.skills.install import (  # noqa: PLC0415
        SkillAlreadyExistsError,
        commit_skill_install,
        resolve_url_import,
    )
    from octop.infra.skills.skill_packages import SkillPackageError  # noqa: PLC0415
    from octop.infra.skills.skills_hub import is_supported_skill_url  # noqa: PLC0415

    locale = resolve_request_locale(request)
    store = _store(server)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_mutate(row, user)

    bundle_url = body.bundle_url.strip()
    if not bundle_url:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "bundle_url is required")
    if not is_supported_skill_url(bundle_url):
        raise OctopError.localized(ErrorCode.SKILL_IMPORT_UNSUPPORTED_URL, locale)

    target = _PackageInstallTarget(store=store, package_id=package_id, server=server)
    try:
        package = await asyncio.to_thread(
            resolve_url_import,
            bundle_url=bundle_url,
            version=body.version,
        )
        await commit_skill_install(
            target,
            package,
            overwrite=body.overwrite,
        )
    except SkillAlreadyExistsError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_ALREADY_EXISTS,
            locale,
            name=exc.slug,
        ) from exc
    except SkillPackageError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc
    except ValueError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc

    return _package_skill_or_404(store, package_id, package.slug)


@router.post(
    "/{package_id}/skills/hub/install",
    status_code=status.HTTP_201_CREATED,
    summary="Install a SkillHub skill into a global skill package",
)
async def hub_install_package_skill(
    package_id: str,
    body: HubInstallPackageSkillBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    from fastapi import HTTPException  # noqa: PLC0415

    from octop.infra.skills.install import (  # noqa: PLC0415
        SkillAlreadyExistsError,
        install_skill_from_skillhub,
        valid_skillhub_icon_url,
    )
    from octop.infra.skills.skill_packages import (  # noqa: PLC0415
        SkillPackageError,
        SkillPackageTooLarge,
        validate_skill_slug,
    )
    from octop.infra.skills.skillhub_market import (  # noqa: PLC0415
        SkillHubMarketError,
        SkillHubPackageError,
        SkillHubPackageTooLarge,
        download_skillhub_package,
    )

    locale = resolve_request_locale(request)
    store = _store(server)
    row = _package_or_404(store, package_id, locale=locale)
    store.assert_can_mutate(row, user)

    try:
        skill_name = validate_skill_slug(body.skill_name)
    except SkillPackageError:
        raise HTTPException(
            status_code=400,
            detail="skill_name is required and must not contain path separators or start with .",
        ) from None

    display_name = (body.display_name or "").strip()
    icon_url = (body.icon_url or "").strip()
    label = (
        {key: value.strip() for key, value in body.label.model_dump().items() if value}
        if body.label
        else {}
    )
    summary = (
        {key: value.strip() for key, value in body.summary.model_dump().items() if value}
        if body.summary
        else {}
    )
    if len(display_name) > 200:
        raise HTTPException(status_code=400, detail="display_name is too long")
    if any(len(value) > 200 for value in label.values()):
        raise HTTPException(status_code=400, detail="localized skill label is too long")
    if any(len(value) > 1024 for value in summary.values()):
        raise HTTPException(status_code=400, detail="localized skill summary is too long")
    if len(icon_url) > 2048 or (icon_url and not valid_skillhub_icon_url(icon_url)):
        raise HTTPException(status_code=400, detail="icon_url must be an HTTP(S) URL")

    target = _PackageInstallTarget(store=store, package_id=package_id, server=server)
    transport = "http"
    try:
        files = await download_skillhub_package(skill_name)
    except SkillHubPackageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except SkillHubPackageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SkillHubMarketError:
        transport = "cli"
        from octop.api.routers.skills import (  # noqa: PLC0415
            _download_skillhub_package_via_cli,
        )

        try:
            files = await _download_skillhub_package_via_cli(skill_name)
        except (SkillHubPackageTooLarge, SkillPackageTooLarge) as package_exc:
            raise HTTPException(status_code=413, detail=str(package_exc)) from package_exc
        except (SkillHubPackageError, SkillPackageError) as package_exc:
            raise HTTPException(status_code=502, detail=str(package_exc)) from package_exc

    try:
        await install_skill_from_skillhub(
            target,
            skill_name=skill_name,
            files=files,
            display_name=display_name,
            icon_url=icon_url,
            label=label,
            summary=summary,
            overwrite=body.overwrite,
        )
    except SkillAlreadyExistsError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_ALREADY_EXISTS,
            locale,
            name=exc.slug,
        ) from exc
    except SkillPackageTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except SkillPackageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "installed": True,
        "name": skill_name,
        "transport": transport,
        "skill": _package_skill_or_404(store, package_id, skill_name, locale=locale),
    }
