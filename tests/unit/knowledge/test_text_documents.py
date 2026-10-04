"""KnowledgeService text create / update helpers."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge.files import document_path, write_document
from octop.infra.knowledge.service import KnowledgeService
from octop.infra.utils.paths import PathLayout


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / ".octop"))
    paths = PathLayout.from_env()
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    owner_id = UserRepo(db).create(username="owner", password_hash="h", role="user")
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: {
        "knowledge_feature_enabled": "1",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": "tiny",
    }.get(key, default)
    return SimpleNamespace(
        knowledge_repo=KnowledgeRepo(db),
        settings_repo=settings,
        provider_repo=None,
        owner_id=owner_id,
    )


def test_create_and_update_text_document(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    created = svc.create_text_document(
        base.id,
        actor_user_id=services.owner_id,
        name="notes",
        format="md",
        content="# Hello\n",
    )
    assert created.filename == "notes.md"
    assert created.content_type == "text/markdown"
    assert created.status == "pending"
    path = document_path(base.id, created.id, created.filename)
    assert path.read_text(encoding="utf-8") == "# Hello\n"

    updated = svc.update_text_document(
        base.id,
        created.id,
        actor_user_id=services.owner_id,
        content="# Updated\n",
    )
    assert updated.status == "pending"
    assert path.read_text(encoding="utf-8") == "# Updated\n"
    raw = svc.read_text_document(base.id, created.id, actor_user_id=services.owner_id)
    assert raw["text"] == "# Updated\n"


def test_upload_spreadsheet_documents(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Sheets")
    xlsx = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="sales.xlsx",
        content_type="application/octet-stream",
        content=b"fake-xlsx",
    )
    csv_doc = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="sales.csv",
        content_type="application/vnd.ms-excel",
        content=b"a,b\n1,2\n",
    )
    xls = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="legacy.xls",
        content_type="application/vnd.ms-excel",
        content=b"fake-xls",
    )
    html = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="page.html",
        content_type="text/html",
        content=b"<p>hi</p>",
    )
    json_doc = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="data.json",
        content_type="application/json",
        content=b"{}",
    )
    xlsm = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="macro.xlsm",
        content_type="application/octet-stream",
        content=b"fake-xlsm",
    )
    assert xlsx.content_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert csv_doc.content_type == "text/csv"
    assert xls.content_type == "application/vnd.ms-excel"
    assert html.content_type == "text/html"
    assert json_doc.content_type == "application/json"
    assert xlsm.content_type == "application/vnd.ms-excel.sheet.macroEnabled.12"


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("failure", ["write", "sync", "replace"])
def test_failed_document_save_preserves_disk_and_database(
    services: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure: str,
) -> None:
    monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a: None)
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    original = "# 原文\n保留完整的知识库内容。\n"
    document = None
    if operation == "update":
        document = svc.create_text_document(
            base.id, actor_user_id=services.owner_id, name="notes", format="md", content=original
        )
        services.knowledge_repo.update_document(document.id, status="ready", chunk_count=7)
    folder = document_path(base.id, "unused", "notes.md").parent
    real_open = Path.open

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("simulated disk failure")

    @contextmanager
    def failing_open(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Iterator[Any]:
        with real_open(path, mode, *args, **kwargs) as stream:
            if failure == "write" and mode in ("wb", "xb") and path.parent == folder:

                def partial_write(data: bytes) -> int:
                    stream.write(data[:3])
                    stream.flush()
                    return fail()

                yield SimpleNamespace(write=partial_write)
            else:
                yield stream

    monkeypatch.setattr(Path, "open", failing_open)
    if failure != "write":
        monkeypatch.setattr(os, "fsync" if failure == "sync" else "replace", fail)
    with pytest.raises(OSError, match="simulated disk failure"):
        if document is None:
            svc.create_text_document(
                base.id, actor_user_id=services.owner_id, name="notes", format="md", content="new"
            )
        else:
            svc.update_text_document(
                base.id, document.id, actor_user_id=services.owner_id, content="new content"
            )
    if document is None:
        assert services.knowledge_repo.list_documents(base.id) == []
        assert list(folder.iterdir()) == []
    else:
        path = document_path(base.id, document.id, document.filename)
        assert path.read_bytes() == original.encode("utf-8")
        stored = services.knowledge_repo.get_document(document.id)
        assert stored.status == "ready"
        assert stored.chunk_count == 7
        assert stored.byte_size == len(original.encode("utf-8"))
        assert set(folder.iterdir()) == {path}


def test_document_readers_see_complete_content_during_update(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("octop.infra.knowledge.service.assert_knowledge_usable", lambda *_a: None)
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Docs")
    document = svc.create_text_document(
        base.id, actor_user_id=services.owner_id, name="notes", format="md", content="original"
    )
    target = document_path(base.id, document.id, document.filename)
    real_open = Path.open
    observed: list[bytes] = []

    @contextmanager
    def observe_write(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Iterator[Any]:
        with real_open(path, mode, *args, **kwargs) as stream:
            if mode in ("wb", "xb") and path.parent == target.parent:

                def write(data: bytes) -> int:
                    first = stream.write(data[:3])
                    stream.flush()
                    observed.append(target.read_bytes())
                    return first + stream.write(data[3:])

                yield SimpleNamespace(write=write, flush=stream.flush, fileno=stream.fileno)
            else:
                yield stream

    monkeypatch.setattr(Path, "open", observe_write)
    svc.update_text_document(
        base.id, document.id, actor_user_id=services.owner_id, content="complete new content"
    )
    assert observed == [b"original"]
    assert target.read_bytes() == b"complete new content"
    assert set(target.parent.iterdir()) == {target}


@pytest.mark.skipif(os.name != "posix", reason="POSIX file mode semantics")
def test_document_save_preserves_file_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    reference = tmp_path / "reference.txt"
    reference.write_bytes(b"reference")
    target = write_document("kb", "doc", "notes.md", b"new")
    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(reference.stat().st_mode)
    target.chmod(0o640)
    write_document("kb", "doc", "notes.md", b"updated")
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_image_upload_requires_ocr(
    services: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable",
        lambda *_a, **_k: None,
    )
    svc = KnowledgeService(services)
    base = svc.create_base(owner_user_id=services.owner_id, name="Images")

    with pytest.raises(ValueError, match="OCR must be enabled"):
        svc.upload_document(
            base.id,
            actor_user_id=services.owner_id,
            filename="scan.png",
            content_type="image/png",
            content=b"image",
        )

    services.settings_repo.get.side_effect = lambda key, default=None: {
        "knowledge_feature_enabled": "1",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": "tiny",
        "knowledge_ocr_enabled": "true",
    }.get(key, default)
    created = svc.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="scan.png",
        content_type="application/octet-stream",
        content=b"image",
    )
    assert created.content_type == "image/png"
