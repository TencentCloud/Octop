"""HTTP API for instance-global skill packages."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel

from octop.api.deps import get_server, require_permission
from octop.infra.agents.experts.skillhub_market import (
    SkillHubMarketError,
    SkillHubMarketErrorKind,
)
from octop.infra.db.repos.skill_packages import SkillPackageRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.skills.install import valid_skillhub_icon_url
from octop.infra.skills.skill_package_from_skillhub import create_package_from_skillhub
from octop.infra.skills.skill_package_store import (
    SkillPackageStore,
    is_skill_package_name_conflict,
    raise_skill_package_name_taken,
)
from octop.infra.skills.skillhub_market import SkillHubMarketError as SkillHubDownloadError
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


class UpdateSkillPackageBody(BaseModel):
    name: str | None = None
    description: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None


class FromSkillHubBody(BaseModel):
    slug: str
    name: str | None = None
    description: str | None = None
    icon_name: str | None = None
    icon_url: str | None = None


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


def _row_public_dict(row: SkillPackageRow) -> dict[str, Any]:
    payload = asdict(row)
    payload.pop("pk", None)
    return payload


def _package_payload(
    store: SkillPackageStore,
    row: SkillPackageRow,
    *,
    locale: Locale | None = None,
) -> dict[str, Any]:
    return {
        **_row_public_dict(row),
        "skills": store.list_skill_summaries(row.id, locale=locale),
    }


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
        **_package_payload(store, row, locale=locale),
        **_creator_fields(server, row.created_by),
    }


def _required(value: str, field: str) -> str:
    value = value.strip()
    if not value:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"{field} is required")
    return value


def _icon_url(value: str) -> str:
    value = value.strip()
    if value and not valid_skillhub_icon_url(value):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid SkillHub icon URL")
    return value


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
    server: OctopServer = Depends(get_server),
    _user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    store = _store(server)
    return [
        {**_row_public_dict(row), **_creator_fields(server, row.created_by)}
        for row in store.repo.list_all()
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
        row = store.create(
            name=name,
            description=body.description.strip(),
            created_by=str(user.id),
            icon_name=body.icon_name.strip(),
            icon_url=_icon_url(body.icon_url),
        )
    except Exception as exc:
        if is_skill_package_name_conflict(exc):
            raise_skill_package_name_taken(name)
        raise
    return _package_payload_with_creator(server, store, row)


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
        )
    except (SkillHubMarketError, SkillHubDownloadError) as exc:
        raise _map_skillhub_error(exc) from exc
    return _package_payload_with_creator(server, store, result.row)


@router.get("/{package_id}", summary="Get a global skill package and its skills")
async def get_skill_package(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    _user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    return _package_payload_with_creator(
        server,
        store,
        row,
        locale=resolve_request_locale(request),
    )


@router.patch("/{package_id}", summary="Update global skill package metadata")
async def update_skill_package(
    package_id: str,
    body: UpdateSkillPackageBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    name = _required(body.name, "name") if body.name is not None else None
    description = body.description.strip() if body.description is not None else None
    icon_name = body.icon_name.strip() if body.icon_name is not None else None
    icon_url = _icon_url(body.icon_url) if body.icon_url is not None else None
    try:
        store.repo.update(
            package_id,
            name=name,
            description=description,
            icon_name=icon_name,
            icon_url=icon_url,
        )
    except Exception as exc:
        if name is not None and is_skill_package_name_conflict(exc):
            raise_skill_package_name_taken(name)
        raise
    updated = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    return _package_payload_with_creator(
        server,
        store,
        updated,
        locale=resolve_request_locale(request),
    )


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
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.strip_skill_package_id(package_id)


@router.get("/{package_id}/skills", summary="List skills in a global skill package")
async def list_package_skills(
    package_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    _user: User = Depends(require_permission("skill_packages")),
) -> list[dict[str, Any]]:
    store = _store(server)
    _package_or_404(store, package_id, locale=resolve_request_locale(request))
    return store.list_skill_summaries(
        package_id,
        locale=resolve_request_locale(request),
    )


@router.get("/{package_id}/skills/{slug}", summary="Get a global package skill")
async def get_package_skill(
    package_id: str,
    slug: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    _user: User = Depends(require_permission("skill_packages")),
) -> dict[str, Any]:
    store = _store(server)
    _package_or_404(store, package_id, locale=resolve_request_locale(request))
    skill = _package_skill_or_404(
        store,
        package_id,
        slug,
        locale=resolve_request_locale(request),
    )
    raw = (store.package_skills_dir(package_id) / slug / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)
    return {**skill, "frontmatter": frontmatter, "body": body, "raw": raw}


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
    store = _store(server)
    row = _package_or_404(store, package_id, locale=resolve_request_locale(request))
    store.assert_can_mutate(row, user)
    _package_skill_or_404(store, package_id, slug)
    store.write_skill(
        package_id,
        slug,
        _files_from_package_skill_body(content=body.content, files=body.files),
    )
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
