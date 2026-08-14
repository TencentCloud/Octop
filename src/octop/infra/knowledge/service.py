"""Knowledge-base ownership checks and document upload orchestration.

Visibility is owner or instance-wide ``shared`` — no per-user ACL members.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from octop.infra.db.repos.knowledge import KnowledgeBaseRow, KnowledgeDocumentRow
from octop.infra.knowledge.files import (
    delete_document_file,
    delete_knowledge_base_files,
    document_path,
    write_document,
)
from octop.infra.knowledge.gate import assert_knowledge_usable
from octop.infra.knowledge.index import KnowledgeIndex
from octop.infra.knowledge.parse import parse_document

MAX_DOCS_PER_KB = 100
MAX_BASES_PER_OWNER = 20
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 20 MiB
_MAX_PREVIEW_CHARS = 200_000
_EXT_TO_CONTENT_TYPE = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_ALLOWED_CONTENT_TYPES = set(_EXT_TO_CONTENT_TYPE.values())


def _resolve_content_type(filename: str, content_type: str) -> str:
    ct = (content_type or "").strip().lower()
    if ct in _ALLOWED_CONTENT_TYPES:
        return ct
    if ct in {"", "application/octet-stream"}:
        return _EXT_TO_CONTENT_TYPE.get(Path(filename).suffix.lower(), ct)
    return ct


class KnowledgeService:
    """Apply ownership while keeping control-plane rows and files synchronized."""

    def __init__(self, services: Any) -> None:
        self._services = services

    @property
    def _repo(self) -> Any:
        return self._services.knowledge_repo

    def create_base(
        self,
        *,
        owner_user_id: int,
        name: str,
        description: str = "",
        default_open: bool = False,
        shared: bool = False,
        icon_name: str = "",
    ) -> KnowledgeBaseRow:
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        owned = self._repo.count_bases_for_owner(owner_user_id)
        if owned >= MAX_BASES_PER_OWNER:
            raise ValueError(f"a user can own at most {MAX_BASES_PER_OWNER} knowledge bases")
        model = (self._services.settings_repo.get("knowledge_embedding_model") or "").strip()
        return cast(
            KnowledgeBaseRow,
            self._repo.create_base(
                owner_user_id=owner_user_id,
                name=name,
                description=description,
                default_open=default_open,
                shared=shared,
                icon_name=icon_name,
                embedding_model=model,
            ),
        )

    def list_visible_bases(
        self, *, actor_user_id: int, is_admin: bool = False
    ) -> list[KnowledgeBaseRow]:
        if is_admin:
            return cast(list[KnowledgeBaseRow], self._repo.list_all())
        return cast(list[KnowledgeBaseRow], self._repo.list_visible(actor_user_id))

    def update_base(
        self,
        kb_id: str,
        *,
        actor_user_id: int,
        name: str | None = None,
        description: str | None = None,
        default_open: bool | None = None,
        shared: bool | None = None,
        icon_name: str | None = None,
        is_admin: bool = False,
    ) -> KnowledgeBaseRow:
        self.require_owner(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        self._repo.update_base(
            kb_id,
            name=name,
            description=description,
            default_open=default_open,
            shared=shared,
            icon_name=icon_name,
        )
        return self._require_base(kb_id)

    def list_documents(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> list[KnowledgeDocumentRow]:
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        return cast(list[KnowledgeDocumentRow], self._repo.list_documents(kb_id))

    def preview_document(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> dict[str, str]:
        """Return extracted plain text for a readable knowledge document."""
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        text = parse_document(document_path(kb_id, doc_id, document.filename))
        if len(text) > _MAX_PREVIEW_CHARS:
            text = text[:_MAX_PREVIEW_CHARS]
        return {
            "id": document.id,
            "filename": document.filename,
            "text": text,
        }

    def get_readable_base(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> KnowledgeBaseRow:
        base = self._require_base(kb_id)
        if is_admin or base.owner_user_id == actor_user_id or base.shared:
            return base
        raise PermissionError("knowledge base read access is required")

    def get_writable_base(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> KnowledgeBaseRow:
        base = self._require_base(kb_id)
        if is_admin or base.owner_user_id == actor_user_id:
            return base
        raise PermissionError("knowledge base write access is required")

    def require_owner(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> KnowledgeBaseRow:
        base = self._require_base(kb_id)
        if is_admin or base.owner_user_id == actor_user_id:
            return base
        raise PermissionError("knowledge base owner access is required")

    def upload_document(
        self,
        kb_id: str,
        *,
        actor_user_id: int,
        filename: str,
        content_type: str,
        content: bytes,
        is_admin: bool = False,
    ) -> KnowledgeDocumentRow:
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"knowledge document size exceeds maximum of {MAX_DOCUMENT_BYTES} bytes"
            )
        resolved_type = _resolve_content_type(filename, content_type)
        if resolved_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"unsupported knowledge document content type: {content_type}")
        if not filename or PathLikeName(filename).is_unsafe:
            raise ValueError("invalid knowledge document filename")
        document = self._repo.create_document(
            kb_id=kb_id,
            filename=filename,
            content_type=resolved_type,
            byte_size=len(content),
            max_documents=MAX_DOCS_PER_KB,
        )
        try:
            write_document(kb_id, document.id, filename, content)
        except Exception:
            self._repo.delete_document(document.id)
            raise
        return cast(KnowledgeDocumentRow, document)

    def delete_document(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> None:
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        KnowledgeIndex(kb_id).delete_doc(doc_id)
        delete_document_file(kb_id, doc_id, document.filename)
        self._repo.delete_document(doc_id)

    def reindex_document(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> KnowledgeDocumentRow:
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        self._repo.update_document(doc_id, status="pending", error_message="", chunk_count=0)
        refreshed = self._repo.get_document(doc_id)
        if refreshed is None:
            raise LookupError("knowledge document not found")
        return cast(KnowledgeDocumentRow, refreshed)

    def delete_base(self, kb_id: str, *, actor_user_id: int, is_admin: bool = False) -> None:
        self.require_owner(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        self._repo.delete_base(kb_id)
        delete_knowledge_base_files(kb_id)

    def _require_base(self, kb_id: str) -> KnowledgeBaseRow:
        base = self._repo.get_base(kb_id)
        if base is None:
            raise LookupError("knowledge base not found")
        return cast(KnowledgeBaseRow, base)


class PathLikeName:
    """Minimal filename safety check; document ids, not names, form the path."""

    def __init__(self, value: str) -> None:
        self.is_unsafe = not value.strip() or "/" in value or "\\" in value
