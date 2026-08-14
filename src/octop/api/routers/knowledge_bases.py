"""HTTP API for private, shareable knowledge bases."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server, require_permission
from octop.infra.agents.providers.model_flags import is_embedding_model, is_onnx_local_provider
from octop.infra.agents.providers.onnx_catalog import list_onnx_catalog_models
from octop.infra.agents.providers.onnx_service import (
    ensure_local_embedding_deps_async,
    is_model_downloaded,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge.gate import (
    assert_knowledge_usable,
    get_capability,
    set_feature_enabled,
)
from octop.infra.knowledge.jobs import enqueue_index_document, reindex_all_documents
from octop.infra.knowledge.service import (
    MAX_BASES_PER_OWNER,
    MAX_DOCS_PER_KB,
    MAX_DOCUMENT_BYTES,
    KnowledgeService,
)
from octop.infra.server import OctopServer
from octop.infra.users.identity import User
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter(prefix="/knowledge-bases")


class FeatureBody(BaseModel):
    enabled: bool = Field(description="Whether to enable the instance-wide knowledge-base feature.")
    model: str | None = Field(
        default=None,
        description="Downloaded ONNX embedding model ID; required when enabling.",
    )
    backend: str | None = Field(default=None, pattern="^(onnx|remote)$")
    provider_id: str | None = None


class CreateBaseBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    default_open: bool = False
    shared: bool = False
    icon_name: str = Field(default="", max_length=64)


class UpdateBaseBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    default_open: bool | None = None
    shared: bool | None = None
    icon_name: str | None = Field(default=None, max_length=64)


def _knowledge_service(server: OctopServer) -> KnowledgeService:
    if server.services is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "knowledge services are not initialized")
    return KnowledgeService(server.services)


def _row_payload(row: Any) -> dict[str, Any]:
    return asdict(row)


def _owner_fields(server: OctopServer, owner_user_id: int) -> dict[str, str | None]:
    if server.services is None:
        return {"owner_username": None, "owner_display_name": None}
    user_repo = getattr(server.services, "user_repo", None)
    if user_repo is None:
        return {"owner_username": None, "owner_display_name": None}
    owner = user_repo.get(int(owner_user_id))
    if owner is None:
        return {"owner_username": None, "owner_display_name": None}
    return {
        "owner_username": owner.username,
        "owner_display_name": owner.display_name or owner.username,
    }


def _base_payload(server: OctopServer, row: Any) -> dict[str, Any]:
    return {**asdict(row), **_owner_fields(server, row.owner_user_id)}


def _is_admin(user: User) -> bool:
    return bool(user.is_admin)


def _map_knowledge_error(exc: Exception, *, locale: str) -> OctopError:
    if isinstance(exc, OctopError):
        return exc
    if isinstance(exc, LookupError):
        return OctopError.localized(ErrorCode.KNOWLEDGE_NOT_FOUND, locale)
    if isinstance(exc, PermissionError):
        return OctopError.localized(ErrorCode.KNOWLEDGE_FORBIDDEN, locale)
    text = str(exc).lower()
    if isinstance(exc, RuntimeError):
        code = (
            ErrorCode.KNOWLEDGE_FEATURE_DISABLED
            if "disabled" in text
            else ErrorCode.KNOWLEDGE_PREREQUISITES_FAILED
        )
        return OctopError.localized(code, locale)
    if "at most 100" in text:
        return OctopError.localized(ErrorCode.KNOWLEDGE_DOC_LIMIT, locale)
    if "document size exceeds" in text:
        return OctopError.localized(ErrorCode.KNOWLEDGE_DOC_TOO_LARGE, locale)
    if "at most" in text and "knowledge bases" in text:
        return OctopError.localized(ErrorCode.KNOWLEDGE_BASE_LIMIT, locale)
    if "unsupported knowledge document content type" in text:
        return OctopError.localized(ErrorCode.KNOWLEDGE_UNSUPPORTED_TYPE, locale)
    if "unique constraint" in text or "duplicate key" in text:
        return OctopError.localized(ErrorCode.KNOWLEDGE_NAME_TAKEN, locale)
    return OctopError.localized(ErrorCode.KNOWLEDGE_PREREQUISITES_FAILED, locale)


def _require_usable(server: OctopServer, request: Request) -> None:
    assert server.services is not None
    try:
        assert_knowledge_usable(server.services.settings_repo.get, server.services.provider_repo)
    except (RuntimeError, ValueError) as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


def _capability_payload(server: OctopServer) -> dict[str, Any]:
    assert server.services is not None
    payload = get_capability(server.services.settings_repo.get, server.services.provider_repo)
    payload["limits"] = {
        "max_bases_per_owner": MAX_BASES_PER_OWNER,
        "max_docs_per_kb": MAX_DOCS_PER_KB,
        "max_document_bytes": MAX_DOCUMENT_BYTES,
    }
    return payload


@router.get("/capability", summary="Get knowledge-base feature capability")
async def capability(
    server: OctopServer = Depends(get_server),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    return _capability_payload(server)


@router.get("/embedding-options", summary="List knowledge embedding backend options")
async def embedding_options(
    server: OctopServer = Depends(get_server),
    _admin: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    assert server.services is not None
    remote = []
    for provider in server.services.provider_repo.list_all():
        if is_onnx_local_provider(
            provider.name, provider_api_key=getattr(provider, "api_key", None)
        ):
            continue
        models = [
            {"id": str(model["id"]), "name": str(model.get("name") or model["id"])}
            for model in provider.get_models()
            if str(model.get("id") or "").strip()
            and is_embedding_model(
                model,
                provider_name=provider.name,
                provider_api_key=getattr(provider, "api_key", None),
            )
        ]
        if models:
            remote.append(
                {"provider_id": str(provider.id), "provider_name": provider.name, "models": models}
            )
    return {
        "onnx": [
            {**model, "downloaded": is_model_downloaded(str(model["id"]))}
            for model in list_onnx_catalog_models()
        ],
        "remote": remote,
    }


@router.put("/feature", summary="Enable or disable knowledge bases (admin)")
async def put_feature(
    body: FeatureBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    _admin: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    assert server.services is not None
    previous = get_capability(server.services.settings_repo.get, server.services.provider_repo)
    selected_backend = (body.backend or "onnx").strip().lower()
    if body.enabled and selected_backend == "onnx":
        try:
            await ensure_local_embedding_deps_async(allow_install=True)
        except RuntimeError as exc:
            raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc
    try:
        set_feature_enabled(
            server.services.settings_repo.get,
            server.services.settings_repo.set,
            enabled=body.enabled,
            backend=body.backend,
            model=body.model,
            provider_id=body.provider_id,
            provider_repo=server.services.provider_repo,
        )
    except (RuntimeError, ValueError) as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc
    capability = _capability_payload(server)
    if body.enabled and (
        not previous["feature_enabled"]
        or previous["selected_model"] != capability["selected_model"]
        or previous["backend"] != capability["backend"]
        or previous["provider_id"] != capability["provider_id"]
    ):
        reindex_all_documents(server.services, capability["selected_model"])
    return capability


@router.get("", summary="List visible knowledge bases")
async def list_bases(
    server: OctopServer = Depends(get_server),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    return [
        _base_payload(server, base)
        for base in _knowledge_service(server).list_visible_bases(
            actor_user_id=user.id, is_admin=_is_admin(user)
        )
    ]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a knowledge base")
async def create_base(
    body: CreateBaseBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    locale = resolve_request_locale(request)
    try:
        _require_usable(server, request)
        base = _knowledge_service(server).create_base(
            owner_user_id=user.id,
            name=body.name.strip(),
            description=body.description.strip(),
            default_open=body.default_open,
            shared=body.shared,
            icon_name=body.icon_name.strip(),
        )
        return _base_payload(server, base)
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=locale) from exc


@router.get("/default-open", summary="List current user's default-open knowledge-base IDs")
async def default_open_bases(
    server: OctopServer = Depends(get_server),
    user: User = Depends(current_user),
) -> dict[str, list[str]]:
    bases = _knowledge_service(server).list_visible_bases(
        actor_user_id=user.id, is_admin=_is_admin(user)
    )
    return {
        "knowledge_base_ids": [
            base.id
            for base in bases
            if base.default_open and int(base.owner_user_id) == int(user.id)
        ]
    }


@router.get("/{kb_id}", summary="Get a visible knowledge base")
async def get_base(
    kb_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        return _base_payload(
            server,
            _knowledge_service(server).get_readable_base(
                kb_id, actor_user_id=user.id, is_admin=_is_admin(user)
            ),
        )
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.patch("/{kb_id}", summary="Update knowledge-base settings")
async def update_base(
    kb_id: str,
    body: UpdateBaseBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    try:
        return _base_payload(
            server,
            _knowledge_service(server).update_base(
                kb_id,
                actor_user_id=user.id,
                name=body.name.strip() if body.name is not None else None,
                description=body.description.strip() if body.description is not None else None,
                default_open=body.default_open,
                shared=body.shared,
                icon_name=body.icon_name.strip() if body.icon_name is not None else None,
                is_admin=_is_admin(user),
            ),
        )
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.delete(
    "/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a knowledge base"
)
async def delete_base(
    kb_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> None:
    try:
        _knowledge_service(server).delete_base(
            kb_id, actor_user_id=user.id, is_admin=_is_admin(user)
        )
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.get("/{kb_id}/documents", summary="List knowledge-base documents")
async def list_documents(
    kb_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(current_user),
) -> list[dict[str, Any]]:
    try:
        return [
            _row_payload(document)
            for document in _knowledge_service(server).list_documents(
                kb_id, actor_user_id=user.id, is_admin=_is_admin(user)
            )
        ]
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.post(
    "/{kb_id}/documents", status_code=status.HTTP_201_CREATED, summary="Upload a knowledge document"
)
async def upload_document(
    kb_id: str,
    request: Request,
    upload: UploadFile = File(..., description="A supported text, PDF, DOCX, or PPTX document."),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    locale = resolve_request_locale(request)
    try:
        _require_usable(server, request)
        content = await upload.read()
        document = _knowledge_service(server).upload_document(
            kb_id,
            actor_user_id=user.id,
            filename=upload.filename or "",
            content_type=upload.content_type or "",
            content=content,
            is_admin=_is_admin(user),
        )
        assert server.services is not None
        enqueue_index_document(server.services, kb_id, document.id)
        return _row_payload(document)
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=locale) from exc


@router.get(
    "/{kb_id}/documents/{doc_id}/preview",
    summary="Preview extracted document text",
)
async def preview_document(
    kb_id: str,
    doc_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    try:
        return _knowledge_service(server).preview_document(
            kb_id, doc_id, actor_user_id=user.id, is_admin=_is_admin(user)
        )
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.delete(
    "/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    kb_id: str,
    doc_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> None:
    try:
        _knowledge_service(server).delete_document(
            kb_id, doc_id, actor_user_id=user.id, is_admin=_is_admin(user)
        )
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.post(
    "/{kb_id}/documents/{doc_id}/reindex",
    summary="Rebuild the index for one knowledge document",
)
async def reindex_document(
    kb_id: str,
    doc_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, Any]:
    try:
        _require_usable(server, request)
        document = _knowledge_service(server).reindex_document(
            kb_id, doc_id, actor_user_id=user.id, is_admin=_is_admin(user)
        )
        assert server.services is not None
        enqueue_index_document(server.services, kb_id, doc_id)
        return _row_payload(document)
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc


@router.post("/{kb_id}/reindex", summary="Reindex all documents in a knowledge base")
async def reindex_base(
    kb_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("knowledge_bases")),
) -> dict[str, int]:
    try:
        _require_usable(server, request)
        service = _knowledge_service(server)
        service.get_writable_base(kb_id, actor_user_id=user.id, is_admin=_is_admin(user))
        documents = service.list_documents(kb_id, actor_user_id=user.id, is_admin=_is_admin(user))
        assert server.services is not None
        for document in documents:
            service.reindex_document(
                kb_id, document.id, actor_user_id=user.id, is_admin=_is_admin(user)
            )
            enqueue_index_document(server.services, kb_id, document.id)
        return {"enqueued": len(documents)}
    except Exception as exc:
        raise _map_knowledge_error(exc, locale=resolve_request_locale(request)) from exc
