"""Unit tests for the knowledge-base HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from octop.infra.errors import ErrorCode, OctopError


def _request() -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/api/knowledge-bases", "headers": []}
    )


def _services(**extra: object) -> SimpleNamespace:
    return SimpleNamespace(
        settings_repo=SimpleNamespace(get=lambda _key: None, set=lambda *_: None),
        provider_repo=SimpleNamespace(list_all=lambda: []),
        **extra,
    )


@dataclass
class _Base:
    id: str = "kb-1"
    owner_user_id: int = 1
    name: str = "Docs"
    description: str = ""
    default_open: bool = False
    shared: bool = False
    icon_name: str = ""
    embedding_model: str = "model"
    embedding_dim: int = 0
    doc_count: int = 0
    created_at: int = 1
    updated_at: int = 1


@dataclass
class _Document:
    id: str = "doc-1"
    kb_id: str = "kb-1"
    filename: str = "readme.md"
    content_type: str = "text/markdown"
    byte_size: int = 2
    content_hash: str = ""
    status: str = "pending"
    error_message: str = ""
    chunk_count: int = 0
    created_at: int = 1
    updated_at: int = 1


@pytest.mark.asyncio
async def test_enabling_without_model_maps_prerequisite_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    server = SimpleNamespace(services=_services())

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("enabling knowledge bases requires an embedding model")

    monkeypatch.setattr(knowledge_bases, "set_feature_enabled", fail)

    with pytest.raises(OctopError) as raised:
        await knowledge_bases.put_feature(
            knowledge_bases.FeatureBody(enabled=True),
            request=_request(),
            server=server,
            _admin=object(),
        )

    assert raised.value.code == ErrorCode.KNOWLEDGE_PREREQUISITES_FAILED


@pytest.mark.asyncio
async def test_enabling_reindexes_documents_when_model_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    settings = {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_model": "old-model",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_provider_id": "",
    }
    calls: list[tuple[object, str]] = []
    server = SimpleNamespace(
        services=SimpleNamespace(
            settings_repo=SimpleNamespace(get=settings.get, set=settings.__setitem__),
            provider_repo=SimpleNamespace(list_all=lambda: []),
        )
    )

    def set_feature(
        _get: object,
        settings_set: object,
        *,
        enabled: bool,
        model: str | None,
        backend: str | None = None,
        provider_id: str | None = None,
        provider_repo: object = None,
    ) -> None:
        assert enabled is True
        assert model == "new-model"
        settings_set("knowledge_embedding_model", model)

    monkeypatch.setattr(knowledge_bases, "set_feature_enabled", set_feature)
    monkeypatch.setattr(
        knowledge_bases,
        "reindex_all_documents",
        lambda services, model: calls.append((services, model)),
    )
    monkeypatch.setattr(
        knowledge_bases,
        "get_capability",
        lambda get, _provider_repo=None: {
            "feature_enabled": get("knowledge_bases_enabled") == "true",
            "selected_model": get("knowledge_embedding_model"),
            "backend": get("knowledge_embedding_backend") or "onnx",
            "provider_id": get("knowledge_embedding_provider_id") or "",
        },
    )

    await knowledge_bases.put_feature(
        knowledge_bases.FeatureBody(enabled=True, model="new-model"),
        request=_request(),
        server=server,
        _admin=object(),
    )

    assert calls == [(server.services, "new-model")]


@pytest.mark.asyncio
async def test_create_base_maps_disabled_feature_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import knowledge_bases

    server = SimpleNamespace(services=_services())
    user = SimpleNamespace(id=1, is_admin=False)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("knowledge feature is disabled")

    monkeypatch.setattr(knowledge_bases, "assert_knowledge_usable", fail)

    with pytest.raises(OctopError) as raised:
        await knowledge_bases.create_base(
            knowledge_bases.CreateBaseBody(name="Docs"),
            request=_request(),
            server=server,
            user=user,
        )

    assert raised.value.code == ErrorCode.KNOWLEDGE_FEATURE_DISABLED


@pytest.mark.asyncio
async def test_create_base_uses_selected_model_when_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    created: dict[str, object] = {}
    service = SimpleNamespace(
        create_base=lambda **kwargs: created.update(kwargs) or _Base(),
    )
    server = SimpleNamespace(services=_services())
    user = SimpleNamespace(id=1, is_admin=False)
    monkeypatch.setattr(knowledge_bases, "assert_knowledge_usable", lambda *_a, **_k: None)
    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _server: service)

    response = await knowledge_bases.create_base(
        knowledge_bases.CreateBaseBody(name="Docs"),
        request=_request(),
        server=server,
        user=user,
    )

    assert response["id"] == "kb-1"
    assert created == {
        "owner_user_id": 1,
        "name": "Docs",
        "description": "",
        "default_open": False,
        "shared": False,
        "icon_name": "",
    }


@pytest.mark.asyncio
async def test_upload_enqueues_document_indexing(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import knowledge_bases

    calls: list[tuple[object, str, str]] = []
    service = SimpleNamespace(
        upload_document=lambda *_args, **_kwargs: _Document(),
    )
    server = SimpleNamespace(services=_services())
    user = SimpleNamespace(id=1, is_admin=False)
    upload = UploadFile(
        file=__import__("io").BytesIO(b"# hi"),
        filename="readme.md",
        headers=Headers({"content-type": "text/markdown"}),
    )
    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _server: service)
    monkeypatch.setattr(knowledge_bases, "assert_knowledge_usable", lambda *_a, **_k: None)
    monkeypatch.setattr(
        knowledge_bases,
        "enqueue_index_document",
        lambda services, kb_id, doc_id: calls.append((services, kb_id, doc_id)),
    )

    response = await knowledge_bases.upload_document(
        "kb-1", request=_request(), upload=upload, server=server, user=user
    )

    assert response["id"] == "doc-1"
    assert calls == [(server.services, "kb-1", "doc-1")]


def test_base_payload_includes_owner_display_fields() -> None:
    from octop.api.routers import knowledge_bases

    owner = SimpleNamespace(username="Test", display_name=None)
    server = SimpleNamespace(
        services=SimpleNamespace(user_repo=SimpleNamespace(get=lambda _id: owner))
    )
    base = _Base(owner_user_id=7)

    payload = knowledge_bases._base_payload(server, base)

    assert payload["owner_user_id"] == 7
    assert payload["owner_username"] == "Test"
    assert payload["owner_display_name"] == "Test"


@pytest.mark.asyncio
async def test_preview_document_returns_extracted_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    service = SimpleNamespace(
        preview_document=lambda *_args, **_kwargs: {
            "id": "doc-1",
            "filename": "notes.md",
            "text": "# Hello",
        }
    )
    server = SimpleNamespace(services=_services())
    user = SimpleNamespace(id=1, is_admin=False)
    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _server: service)

    response = await knowledge_bases.preview_document(
        "kb-1", "doc-1", request=_request(), server=server, user=user
    )

    assert response == {"id": "doc-1", "filename": "notes.md", "text": "# Hello"}


@pytest.mark.asyncio
async def test_embedding_options_excludes_onnx_local_provider() -> None:
    from octop.api.routers import knowledge_bases

    providers = [
        SimpleNamespace(
            id=1,
            name="ONNX (Local)",
            api_key="onnx",
            get_models=lambda: [
                {
                    "id": "BAAI/bge-small-zh-v1.5",
                    "name": "bge",
                    "embedding": True,
                }
            ],
        ),
        SimpleNamespace(
            id=2,
            name="OpenAI",
            api_key="sk-test",
            get_models=lambda: [
                {"id": "text-embedding-3-small", "name": "embed", "embedding": True},
                {"id": "gpt-4o", "name": "GPT-4o"},
            ],
        ),
    ]
    server = SimpleNamespace(
        services=SimpleNamespace(provider_repo=SimpleNamespace(list_all=lambda: providers))
    )

    options = await knowledge_bases.embedding_options(server=server, _admin=object())

    assert [row["provider_name"] for row in options["remote"]] == ["OpenAI"]
    assert options["remote"][0]["models"] == [{"id": "text-embedding-3-small", "name": "embed"}]
    assert isinstance(options["onnx"], list)


@pytest.mark.asyncio
async def test_reindex_document_enqueues_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    calls: list[tuple[object, str, str]] = []
    service = SimpleNamespace(
        reindex_document=lambda *_args, **_kwargs: _Document(status="pending"),
    )
    server = SimpleNamespace(services=_services())
    user = SimpleNamespace(id=1, is_admin=False)
    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _server: service)
    monkeypatch.setattr(knowledge_bases, "_require_usable", lambda *_a, **_k: None)
    monkeypatch.setattr(
        knowledge_bases,
        "enqueue_index_document",
        lambda services, kb_id, doc_id: calls.append((services, kb_id, doc_id)),
    )

    response = await knowledge_bases.reindex_document(
        "kb-1", "doc-1", request=_request(), server=server, user=user
    )

    assert response["status"] == "pending"
    assert calls == [(server.services, "kb-1", "doc-1")]
