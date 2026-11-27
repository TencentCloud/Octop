"""Real upload/preview/index integration, with embedding readiness and vectors stubbed."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.knowledge import jobs
from octop.infra.knowledge.files import document_path
from octop.infra.knowledge.index import KnowledgeIndex
from octop.infra.knowledge.service import KnowledgeService


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    owner = UserRepo(pool).create(username="owner", password_hash="unused", role="user")
    monkeypatch.setattr(jobs, "assert_knowledge_usable", lambda *_args: None)
    monkeypatch.setattr(
        "octop.infra.knowledge.service.assert_knowledge_usable", lambda *_args: None
    )
    monkeypatch.setattr(
        jobs, "embed_knowledge_texts", lambda _services, chunks: [[1.0, 0.0] for _ in chunks]
    )
    try:
        yield SimpleNamespace(
            knowledge_repo=KnowledgeRepo(pool), settings_repo=SettingsRepo(pool), owner_id=owner
        )
    finally:
        pool.close()


def test_spreadsheetml_upload_preview_and_index_preserve_source(services: SimpleNamespace) -> None:
    service = KnowledgeService(services)
    base = service.create_base(owner_user_id=services.owner_id, name="Exports")
    source = (
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
        'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
        '<Worksheet ss:Name="Orders"><Table><Row><Cell><Data ss:Type="String">'
        '订单 0001234567890123456789</Data></Cell><Cell><Data ss:Type="Number">'
        "12.25</Data></Cell></Row></Table></Worksheet></Workbook>"
    ).encode()
    document = service.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="orders.xls",
        content_type="application/vnd.ms-excel",
        content=source,
    )

    jobs.process_document(services, base.id, document.id)

    expected = "# Orders\n订单 0001234567890123456789\t12.25"
    preview = service.preview_document(base.id, document.id, actor_user_id=services.owner_id)
    assert preview["text"] == expected
    updated = services.knowledge_repo.get_document(document.id)
    assert updated.status == "ready"
    assert updated.chunk_count == 1
    hit = KnowledgeIndex(base.id).search([1.0, 0.0], 1)[0]
    assert hit.doc_id == document.id
    assert hit.text == expected
    assert document_path(base.id, document.id, document.filename).read_bytes() == source


def test_invalid_xml_does_not_replace_a_previously_indexed_document(
    services: SimpleNamespace,
) -> None:
    service = KnowledgeService(services)
    base = service.create_base(owner_user_id=services.owner_id, name="Exports")
    document = service.upload_document(
        base.id,
        actor_user_id=services.owner_id,
        filename="orders.xls",
        content_type="application/vnd.ms-excel",
        content=b"<!DOCTYPE Workbook><Workbook/>",
    )
    index = KnowledgeIndex(base.id)
    index.replace_doc_chunks(document.id, ["previously indexed content"], [[1.0, 0.0]])

    with pytest.raises(ValueError, match="DTD"):
        jobs.process_document(services, base.id, document.id)

    assert services.knowledge_repo.get_document(document.id).status == "failed"
    assert index.search([1.0, 0.0], 1)[0].text == "previously indexed content"
