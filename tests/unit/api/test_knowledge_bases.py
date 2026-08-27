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
    pk: int = 1
    owner_user_id: int = 1
    name: str = "Docs"
    description: str = ""
    default_open: bool = False
    shared: bool = False
    icon_name: str = ""
    embedding_model: str = "model"
    embedding_dim: int = 0
    doc_count: int = 0
    max_documents: int = 100
    created_at: int = 1
    updated_at: int = 1


@dataclass
class _Document:
    id: str = "doc-1"
    pk: int = 1
    kb_id: str = "kb-1"
    path: str = "readme.md"
    filename: str = "readme.md"
    is_dir: bool = False
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
        "max_documents": 100,
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
    from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS

    onnx_ids = [row["id"] for row in options["onnx"]]
    assert onnx_ids == list(ONNX_PRESET_MODEL_IDS)
    assert all(row.get("recommended") for row in options["onnx"])
    assert all("downloaded" in row for row in options["onnx"])
    assert any(row.get("size_gb") for row in options["onnx"])


@pytest.mark.asyncio
async def test_embedding_options_omits_non_recommended_onnx() -> None:
    from octop.api.routers import knowledge_bases
    from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS

    extra = "BAAI/bge-small-en-v1.5"
    server = SimpleNamespace(
        services=SimpleNamespace(
            provider_repo=SimpleNamespace(list_all=lambda: []),
            settings_repo=SimpleNamespace(
                get=lambda key: extra if key == "knowledge_embedding_model" else None
            ),
        )
    )

    options = await knowledge_bases.embedding_options(server=server, _admin=object())

    assert extra not in [row["id"] for row in options["onnx"]]
    assert [row["id"] for row in options["onnx"]] == list(ONNX_PRESET_MODEL_IDS)


@pytest.mark.asyncio
async def test_embedding_options_all_onnx_includes_extras() -> None:
    from octop.api.routers import knowledge_bases
    from octop.infra.agents.providers.onnx_catalog import ONNX_PRESET_MODEL_IDS

    server = SimpleNamespace(
        services=SimpleNamespace(provider_repo=SimpleNamespace(list_all=lambda: []))
    )

    options = await knowledge_bases.embedding_options(all_onnx=True, server=server, _admin=object())

    ids = [row["id"] for row in options["onnx"]]
    assert ids[: len(ONNX_PRESET_MODEL_IDS)] == list(ONNX_PRESET_MODEL_IDS)
    assert len(ids) > len(ONNX_PRESET_MODEL_IDS)
    assert any(not row.get("recommended") for row in options["onnx"])
    assert all("downloaded" in row for row in options["onnx"])


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


@pytest.mark.asyncio
async def test_onnx_download_starts_catalog_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import knowledge_bases

    class _State:
        def to_dict(self) -> dict[str, object]:
            return {
                "status": "downloading",
                "progress": 0.1,
                "model_name": "BAAI/bge-small-zh-v1.5",
                "error": None,
            }

    async def start(model: str) -> _State:
        assert model == "BAAI/bge-small-zh-v1.5"
        return _State()

    monkeypatch.setattr(knowledge_bases.DOWNLOAD_MANAGER, "start_download", start)

    response = await knowledge_bases.start_onnx_download(
        knowledge_bases.OnnxDownloadBody(model="BAAI/bge-small-zh-v1.5"),
        request=_request(),
        _=object(),
    )

    assert response["status"] == "downloading"
    assert response["model_name"] == "BAAI/bge-small-zh-v1.5"


@pytest.mark.asyncio
async def test_onnx_activate_enables_downloaded_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    saved: dict[str, object] = {}

    async def ready(**_kwargs: object) -> str:
        return "ready"

    monkeypatch.setattr(knowledge_bases, "ensure_local_embedding_deps_async", ready)
    monkeypatch.setattr(knowledge_bases, "assert_catalog_model", lambda model: model)
    monkeypatch.setattr(knowledge_bases, "is_model_downloaded", lambda _model: True)
    monkeypatch.setattr(
        knowledge_bases,
        "save_config",
        lambda _setter, config: saved.update(config.to_dict()) or config,
    )
    monkeypatch.setattr(
        knowledge_bases,
        "status_payload",
        lambda *_args, **_kwargs: {"enabled": True, "model": "BAAI/bge-small-zh-v1.5"},
    )
    server = SimpleNamespace(services=_services())

    response = await knowledge_bases.activate_onnx_service(
        knowledge_bases.OnnxDownloadBody(model="BAAI/bge-small-zh-v1.5"),
        request=_request(),
        server=server,
        _=object(),
    )

    assert saved == {"enabled": True, "model": "BAAI/bge-small-zh-v1.5"}
    assert response["enabled"] is True


@pytest.mark.asyncio
async def test_rename_document_returns_row_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    server = SimpleNamespace(services=_services())
    renamed = _Document(id="doc-1", is_dir=True, path="docs/new", filename="new")

    class _FakeService:
        def rename_document(self, *_args: object, **_kwargs: object) -> _Document:
            return renamed

    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _server: _FakeService())

    result = await knowledge_bases.rename_document(
        kb_id="kb-1",
        doc_id="doc-1",
        body=knowledge_bases.RenameDocumentBody(new_name="new"),
        request=_request(),
        server=server,
        user=SimpleNamespace(id=1, is_admin=False),
    )

    assert result["document_id"] == "doc-1"
    assert result["path"] == "docs/new"
    assert result["filename"] == "new"


@pytest.mark.asyncio
async def test_rename_document_maps_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    def fail(*_args: object, **_kwargs: object) -> None:
        raise LookupError("knowledge document not found")

    monkeypatch.setattr(knowledge_bases, "_knowledge_service", fail)

    with pytest.raises(OctopError) as raised:
        await knowledge_bases.rename_document(
            kb_id="kb-1",
            doc_id="doc-1",
            body=knowledge_bases.RenameDocumentBody(new_name="new"),
            request=_request(),
            server=SimpleNamespace(services=_services()),
            user=object(),
        )

    assert raised.value.code == ErrorCode.KNOWLEDGE_NOT_FOUND


@pytest.mark.asyncio
async def test_rename_document_maps_name_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("a knowledge document with this name already exists")

    monkeypatch.setattr(knowledge_bases, "_knowledge_service", fail)

    with pytest.raises(OctopError) as raised:
        await knowledge_bases.rename_document(
            kb_id="kb-1",
            doc_id="doc-1",
            body=knowledge_bases.RenameDocumentBody(new_name="dup"),
            request=_request(),
            server=SimpleNamespace(services=_services()),
            user=object(),
        )

    assert raised.value.code == ErrorCode.KNOWLEDGE_NAME_TAKEN


@pytest.mark.asyncio
async def test_rename_document_maps_invalid_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.api.routers import knowledge_bases

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("invalid knowledge document name")

    monkeypatch.setattr(knowledge_bases, "_knowledge_service", fail)

    with pytest.raises(OctopError) as raised:
        await knowledge_bases.rename_document(
            kb_id="kb-1",
            doc_id="doc-1",
            body=knowledge_bases.RenameDocumentBody(new_name="a/b"),
            request=_request(),
            server=SimpleNamespace(services=_services()),
            user=object(),
        )

    assert raised.value.code == ErrorCode.KNOWLEDGE_NAME_INVALID


@pytest.mark.asyncio
async def test_update_base_accepts_max_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import knowledge_bases

    received: dict[str, object] = {}

    class _StubSvc:
        def update_base(self, *_: object, **kw: object) -> object:
            received.update(kw)
            return _Base(max_documents=42)

    monkeypatch.setattr(knowledge_bases, "_knowledge_service", lambda _s: _StubSvc())

    response = await knowledge_bases.update_base(
        kb_id="kb-1",
        body=knowledge_bases.UpdateBaseBody(max_documents=42),
        request=_request(),
        server=SimpleNamespace(services=_services()),
        user=SimpleNamespace(id=1, is_admin=False),
    )
    assert received["max_documents"] == 42
    assert response["max_documents"] == 42


@pytest.mark.asyncio
async def test_update_base_rejects_max_documents_out_of_range() -> None:
    from pydantic import ValidationError

    from octop.api.routers import knowledge_bases

    with pytest.raises(ValidationError):
        knowledge_bases.UpdateBaseBody(max_documents=-1)
    with pytest.raises(ValidationError):
        knowledge_bases.UpdateBaseBody(max_documents=10_001)
    assert knowledge_bases.UpdateBaseBody(max_documents=0).max_documents == 0
    assert knowledge_bases.UpdateBaseBody(max_documents=10_000).max_documents == 10_000
    assert knowledge_bases.UpdateBaseBody().max_documents is None
