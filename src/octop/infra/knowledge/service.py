"""Knowledge-base ownership checks and document upload orchestration.

Visibility is owner or instance-wide ``shared``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from octop.config import DEFAULT_MAX_UPLOAD_MB, upload_mb_to_bytes
from octop.infra.db.repos.knowledge import KnowledgeBaseRow, KnowledgeDocumentRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge.blobs import KnowledgeBlobs
from octop.infra.knowledge.gate import assert_knowledge_usable
from octop.infra.knowledge.ocr import (
    OCR_IMAGE_SUFFIXES,
    load_ocr_config,
    optional_ocr_extractor,
)
from octop.infra.knowledge.parse import parse_document
from octop.infra.knowledge.plane import open_knowledge_index, postgres_database
from octop.infra.knowledge.relpath import normalize_kb_path, path_basename, path_parent

logger = logging.getLogger(__name__)

MAX_DOCS_PER_KB = 100
MAX_BASES_PER_OWNER = 20
MAX_DOCUMENT_BYTES = upload_mb_to_bytes(DEFAULT_MAX_UPLOAD_MB)
# Upper bound for the per-base max_documents field. Mirrors Field(le=10000).
MAX_KB_MAX_DOCUMENTS = 10_000
_MAX_PREVIEW_CHARS = 200_000
_EXT_TO_CONTENT_TYPE = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".rst": "text/x-rst",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".jsonl": "application/jsonl",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".wps": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_ALLOWED_CONTENT_TYPES = set(_EXT_TO_CONTENT_TYPE.values())
_TEXT_CONTENT_TYPES = {"text/plain", "text/markdown"}
_TEXT_FORMAT_TO_EXT = {"md": ".md", "txt": ".txt"}
_TEXT_FORMAT_TO_CONTENT_TYPE = {"md": "text/markdown", "txt": "text/plain"}


def _resolve_content_type(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    mapped = _EXT_TO_CONTENT_TYPE.get(suffix)
    if mapped is not None:
        return mapped
    ct = (content_type or "").strip().lower()
    if ct in _ALLOWED_CONTENT_TYPES:
        return ct
    if ct in {"", "application/octet-stream"}:
        return ct
    return ct


class KnowledgeService:
    """Apply ownership while keeping control-plane rows and files synchronized."""

    def __init__(self, services: Any) -> None:
        self._services = services

    def _max_document_bytes(self) -> int:
        config = getattr(self._services, "config", None)
        limit = getattr(config, "max_upload_bytes", None)
        if isinstance(limit, int) and limit > 0:
            return limit
        return MAX_DOCUMENT_BYTES

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
        icon_url: str = "",
        max_documents: int = MAX_DOCS_PER_KB,
    ) -> KnowledgeBaseRow:
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        if max_documents < 0 or max_documents > MAX_KB_MAX_DOCUMENTS:
            raise ValueError(f"max_documents must be between 0 and {MAX_KB_MAX_DOCUMENTS}")
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
                icon_url=icon_url,
                embedding_model=model,
                max_documents=max_documents,
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
        icon_url: str | None = None,
        max_documents: int | None = None,
        is_admin: bool = False,
    ) -> KnowledgeBaseRow:
        self.require_owner(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        if max_documents is not None and (
            max_documents < 0 or max_documents > MAX_KB_MAX_DOCUMENTS
        ):
            raise ValueError(f"max_documents must be between 0 and {MAX_KB_MAX_DOCUMENTS}")
        self._repo.update_base(
            kb_id,
            name=name,
            description=description,
            default_open=default_open,
            shared=shared,
            icon_name=icon_name,
            icon_url=icon_url,
            max_documents=max_documents,
        )
        return self._require_base(kb_id)

    def list_documents(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False, prefix: str | None = None
    ) -> list[KnowledgeDocumentRow]:
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        if prefix is None:
            return cast(list[KnowledgeDocumentRow], self._repo.list_documents(kb_id))
        return cast(list[KnowledgeDocumentRow], self._repo.list_children(kb_id, prefix))

    def create_folder(
        self, kb_id: str, *, actor_user_id: int, path: str, is_admin: bool = False
    ) -> KnowledgeDocumentRow:
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        return cast(KnowledgeDocumentRow, self._repo.ensure_folder(kb_id, path))

    def preview_document(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> dict[str, str]:
        """Return extracted plain text for a readable knowledge document."""
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        if document.is_dir:
            raise LookupError("knowledge document not found")
        path = self._blobs().ensure_local(kb_id, doc_id, document.filename)
        text = parse_document(path, ocr=optional_ocr_extractor(self._services))
        if len(text) > _MAX_PREVIEW_CHARS:
            text = text[:_MAX_PREVIEW_CHARS]
        return {
            "id": document.id,
            "filename": document.filename,
            "text": text,
        }

    def list_document_chunks(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> dict[str, object]:
        """Return the indexed slices actually stored for one document."""
        from octop.infra.knowledge.plane import open_knowledge_index

        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id or document.is_dir:
            raise LookupError("knowledge document not found")
        rows = open_knowledge_index(self._services, kb_id).list_doc_chunks(document.id)
        return {
            "id": document.id,
            "filename": document.filename,
            "chunks": [{"ordinal": ordinal, "text": text} for ordinal, text in rows],
        }

    def resolve_document_file(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> tuple[Path, str, str]:
        """Return ``(path, filename, content_type)`` for the on-disk original.

        Raises ``LookupError`` when the document row is missing and
        ``FileNotFoundError`` when the original bytes are gone from disk.
        """
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        if document.is_dir:
            raise LookupError("knowledge document not found")
        path = self._blobs().ensure_local(kb_id, doc_id, document.filename)
        if not path.is_file():
            raise FileNotFoundError("knowledge document original file not found")
        return path, document.filename, document.content_type

    def document_has_original(self, document: KnowledgeDocumentRow) -> bool:
        """True when the uploaded original still exists."""
        if document.is_dir:
            return False
        return self._blobs().exists(document.kb_id, document.id, document.filename)

    def read_text_document(
        self, kb_id: str, doc_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> dict[str, str]:
        """Return raw UTF-8 text for an editable md/txt knowledge document."""
        self.get_readable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        if document.is_dir:
            raise LookupError("knowledge document not found")
        if document.content_type not in _TEXT_CONTENT_TYPES:
            raise ValueError("unsupported knowledge document content type: not editable text")
        raw = self._blobs().read_bytes(kb_id, doc_id, document.filename)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("knowledge document is not valid UTF-8 text") from exc
        return {
            "id": document.id,
            "filename": document.filename,
            "content_type": document.content_type,
            "text": text,
        }

    def create_text_document(
        self,
        kb_id: str,
        *,
        actor_user_id: int,
        name: str,
        format: str,
        content: str = "",
        is_admin: bool = False,
        path: str | None = None,
    ) -> KnowledgeDocumentRow:
        """Create a markdown or plain-text document with optional draft content."""
        fmt = (format or "").strip().lower().lstrip(".")
        if fmt not in _TEXT_FORMAT_TO_EXT:
            raise ValueError(f"unsupported knowledge document content type: {format}")
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise ValueError("invalid knowledge document filename")
        ext = _TEXT_FORMAT_TO_EXT[fmt]
        stem = Path(cleaned_name).name
        if Path(stem).suffix.lower() not in {".md", ".txt"}:
            stem = f"{stem}{ext}"
        elif Path(stem).suffix.lower() != ext:
            stem = f"{Path(stem).stem}{ext}"
        relative = f"{normalize_kb_path(path)}/{stem}" if path else stem
        relative = normalize_kb_path(relative)
        encoded = content.encode("utf-8")
        return self.upload_document(
            kb_id,
            actor_user_id=actor_user_id,
            filename=stem,
            content_type=_TEXT_FORMAT_TO_CONTENT_TYPE[fmt],
            content=encoded,
            is_admin=is_admin,
            path=relative,
        )

    def update_text_document(
        self,
        kb_id: str,
        doc_id: str,
        *,
        actor_user_id: int,
        content: str,
        is_admin: bool = False,
    ) -> KnowledgeDocumentRow:
        """Overwrite md/txt content and mark the document pending for reindex."""
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        if document.is_dir:
            raise LookupError("knowledge document not found")
        if document.content_type not in _TEXT_CONTENT_TYPES:
            raise ValueError("unsupported knowledge document content type: not editable text")
        encoded = content.encode("utf-8")
        limit = self._max_document_bytes()
        if len(encoded) > limit:
            raise ValueError(f"knowledge document size exceeds maximum of {limit} bytes")
        self._blobs().write(kb_id, document.id, document.filename, encoded)
        self._repo.update_document(
            doc_id,
            byte_size=len(encoded),
            status="pending",
            error_message="",
            chunk_count=0,
        )
        refreshed = self._repo.get_document(doc_id)
        if refreshed is None:
            raise LookupError("knowledge document not found")
        return cast(KnowledgeDocumentRow, refreshed)

    def get_readable_base(
        self, kb_id: str, *, actor_user_id: int, is_admin: bool = False
    ) -> KnowledgeBaseRow:
        base = self._require_base(kb_id)
        if is_admin or base.owner_user_id == actor_user_id:
            return base
        if base.shared:
            from octop.infra.users.groups import RESOURCE_KNOWLEDGE_BASE, GroupAccess

            repos = getattr(self._services, "repos", None)
            if repos is None or GroupAccess(repos).allows(
                user_id=actor_user_id,
                is_admin=False,
                resource_type=RESOURCE_KNOWLEDGE_BASE,
                resource_key=base.id,
                is_owner=False,
            ):
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
        path: str | None = None,
    ) -> KnowledgeDocumentRow:
        assert_knowledge_usable(
            self._services.settings_repo.get, getattr(self._services, "provider_repo", None)
        )
        base = self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        limit = self._max_document_bytes()
        if len(content) > limit:
            raise ValueError(f"knowledge document size exceeds maximum of {limit} bytes")
        rel = normalize_kb_path(path or filename)
        name = path_basename(rel)
        if not name:
            raise ValueError("invalid knowledge document filename")
        if (
            Path(name).suffix.lower() in OCR_IMAGE_SUFFIXES
            and not load_ocr_config(self._services.settings_repo.get).enabled
        ):
            raise ValueError("knowledge OCR must be enabled for image documents")
        resolved_type = _resolve_content_type(name, content_type)
        if resolved_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"unsupported knowledge document content type: {content_type}")
        # The per-base limit lives on the KB row (schema v10). 0 = unlimited.
        document = self._repo.create_document(
            kb_id=kb_id,
            filename=name,
            path=rel,
            content_type=resolved_type,
            byte_size=len(content),
            max_documents=base.max_documents,
        )
        try:
            self._blobs().write(kb_id, document.id, name, content)
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
        removed = self._repo.delete_document(doc_id)
        for row in removed:
            if row.is_dir:
                continue
            open_knowledge_index(self._services, kb_id).delete_doc(row.id)
            self._blobs().delete(kb_id, row.id, row.filename)

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
        if document.is_dir:
            raise ValueError("folders cannot be reindexed")
        self._repo.update_document(doc_id, status="pending", error_message="", chunk_count=0)
        refreshed = self._repo.get_document(doc_id)
        if refreshed is None:
            raise LookupError("knowledge document not found")
        return cast(KnowledgeDocumentRow, refreshed)

    def rename_document(
        self,
        kb_id: str,
        doc_id: str,
        *,
        new_name: str,
        actor_user_id: int,
        is_admin: bool = False,
    ) -> KnowledgeDocumentRow:
        """Rename a document (file or folder), rewriting descendant paths for folders."""
        self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        cleaned = (new_name or "").strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("invalid knowledge document name")
        new_path = normalize_kb_path(f"{path_parent(document.path)}/{cleaned}")
        if new_path == document.path:
            return cast(KnowledgeDocumentRow, document)
        if self._repo.get_document_by_path(kb_id, new_path) is not None:
            raise ValueError("a knowledge document with this name already exists")
        result = self._repo.rename_document(kb_id, doc_id, cleaned)
        if result is None:
            raise LookupError("knowledge document not found")
        return cast(KnowledgeDocumentRow, result)

    def _move_across_bases(
        self,
        document: KnowledgeDocumentRow,
        *,
        source: KnowledgeBaseRow,
        dest: KnowledgeBaseRow,
        target: str,
    ) -> KnowledgeDocumentRow:
        """Move a file or folder into ``target`` of another base.

        Originals and chunks are copied to the target before the rows switch
        base, and removed from the source after, so a failure leaves the source
        intact. Chunks are reused when both bases embed with the same model;
        otherwise (or when a file has none yet) the file goes back to pending
        and the caller schedules indexing in the target.
        """
        new_path = normalize_kb_path(f"{target}/{path_basename(document.path)}")
        if self._repo.get_document_by_path(dest.id, new_path) is not None:
            raise OctopError(
                ErrorCode.KNOWLEDGE_MOVE_NAME_TAKEN,
                "the target folder already has an item with this name",
            )
        files = [row for row in self._repo.list_subtree(document) if not row.is_dir]
        if any(row.status == "processing" for row in files):
            raise OctopError(
                ErrorCode.KNOWLEDGE_MOVE_BUSY,
                "documents still being indexed cannot move to another knowledge base",
            )
        if dest.max_documents > 0 and dest.doc_count + len(files) > dest.max_documents:
            raise OctopError(
                ErrorCode.KNOWLEDGE_DOC_LIMIT,
                f"knowledge bases support at most {dest.max_documents} documents",
            )
        blobs = self._blobs()
        source_index = open_knowledge_index(self._services, source.id)
        dest_index = open_knowledge_index(self._services, dest.id)
        same_model = source.embedding_model == dest.embedding_model
        reindex: list[str] = []
        copied: list[KnowledgeDocumentRow] = []
        try:
            for row in files:
                copied.append(row)
                if blobs.exists(source.id, row.id, row.filename):
                    content = blobs.read_bytes(source.id, row.id, row.filename)
                    blobs.write(dest.id, row.id, row.filename, content)
                chunks = (
                    source_index.read_doc_chunks(row.id)
                    if same_model and row.status == "ready"
                    else []
                )
                if chunks:
                    dest_index.replace_doc_chunks(
                        row.id,
                        [text for text, _, _ in chunks],
                        [embedding for _, embedding, _ in chunks],
                        metadata=[meta for _, _, meta in chunks],
                    )
                elif row.status != "failed":
                    reindex.append(row.id)
            result = self._repo.move_to_base(
                document,
                target_kb_id=dest.id,
                target_folder=target,
                max_documents=dest.max_documents,
                reindex_ids=reindex,
            )
        except ValueError as exc:
            self._discard_copies(dest.id, copied)
            if "at most" in str(exc):
                raise OctopError(ErrorCode.KNOWLEDGE_DOC_LIMIT, str(exc)) from exc
            raise
        except Exception:
            self._discard_copies(dest.id, copied)
            raise
        if result is None:
            raise LookupError("knowledge document not found")
        self._discard_copies(source.id, files)
        dimension = source.embedding_dim if same_model else 0
        if dimension and not dest.embedding_dim:
            self._repo.update_base(dest.id, embedding_dim=dimension)
        return cast(KnowledgeDocumentRow, result)

    def _discard_copies(self, kb_id: str, rows: list[KnowledgeDocumentRow]) -> None:
        """Best-effort removal of originals and chunks a base no longer owns."""
        index = open_knowledge_index(self._services, kb_id)
        blobs = self._blobs()
        for row in rows:
            try:
                index.delete_doc(row.id)
                blobs.delete(kb_id, row.id, row.filename)
            except Exception:
                logger.warning(
                    "could not clean up knowledge document %s in %s", row.id, kb_id, exc_info=True
                )

    def pending_file_ids(self, document: KnowledgeDocumentRow) -> list[str]:
        """Files of a document or folder still waiting to be indexed."""
        return [
            row.id
            for row in self._repo.list_subtree(document)
            if not row.is_dir and row.status == "pending"
        ]

    def move_document(
        self,
        kb_id: str,
        doc_id: str,
        *,
        target_folder: str,
        actor_user_id: int,
        is_admin: bool = False,
        target_kb_id: str | None = None,
    ) -> KnowledgeDocumentRow:
        """Move a document (file or folder) into a folder of this or another base.

        ``target_folder`` is a folder path; ``""`` is the root. Moving a folder
        takes its whole subtree. Within one base the index is untouched: chunks
        belong to the document id, not to its path. ``target_kb_id`` names
        another base the actor can write to; see ``_move_across_bases``.
        """
        source = self.get_writable_base(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        document = self._repo.get_document(doc_id)
        if document is None or document.kb_id != kb_id:
            raise LookupError("knowledge document not found")
        dest_kb_id = (target_kb_id or "").strip() or kb_id
        dest = (
            source
            if dest_kb_id == kb_id
            else self.get_writable_base(dest_kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        )
        try:
            target = normalize_kb_path(target_folder)
        except ValueError as exc:
            raise LookupError("knowledge folder not found") from exc
        if target:
            folder = self._repo.get_document_by_path(dest.id, target)
            if folder is None or not folder.is_dir:
                raise LookupError("knowledge folder not found")
        if dest.id != kb_id:
            return self._move_across_bases(document, source=source, dest=dest, target=target)
        if document.is_dir and (target == document.path or target.startswith(f"{document.path}/")):
            raise OctopError(
                ErrorCode.KNOWLEDGE_MOVE_INVALID,
                "a folder cannot be moved into itself or one of its subfolders",
            )
        if target == path_parent(document.path):
            return cast(KnowledgeDocumentRow, document)
        new_path = normalize_kb_path(f"{target}/{path_basename(document.path)}")
        if self._repo.get_document_by_path(kb_id, new_path) is not None:
            raise OctopError(
                ErrorCode.KNOWLEDGE_MOVE_NAME_TAKEN,
                "the target folder already has an item with this name",
            )
        result = self._repo.move_document(kb_id, doc_id, target)
        if result is None:
            raise LookupError("knowledge document not found")
        return cast(KnowledgeDocumentRow, result)

    def delete_base(self, kb_id: str, *, actor_user_id: int, is_admin: bool = False) -> None:
        self.require_owner(kb_id, actor_user_id=actor_user_id, is_admin=is_admin)
        database = postgres_database(self._services)
        if database is not None:
            from octop.infra.knowledge.pg_index import PgVectorKnowledgeIndex

            PgVectorKnowledgeIndex(kb_id, database).delete_kb()
        self._repo.delete_base(kb_id)
        from octop.infra.users.groups import RESOURCE_KNOWLEDGE_BASE, GroupAccess

        repos = getattr(self._services, "repos", None)
        if repos is not None:
            GroupAccess(repos).clear(RESOURCE_KNOWLEDGE_BASE, kb_id)
        self._blobs().delete_base(kb_id)

    def _blobs(self) -> KnowledgeBlobs:
        return KnowledgeBlobs.from_services(self._services)

    def _require_base(self, kb_id: str) -> KnowledgeBaseRow:
        base = self._repo.get_base(kb_id)
        if base is None:
            raise LookupError("knowledge base not found")
        return cast(KnowledgeBaseRow, base)
