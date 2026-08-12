"""Text extraction for the document types accepted by knowledge bases."""

from __future__ import annotations

from pathlib import Path


def parse_document(path: Path) -> str:
    """Extract searchable text from a supported local document."""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        from docx import Document

        return "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    if suffix == ".pptx":
        from pptx import Presentation

        return "\n".join(
            shape.text
            for slide in Presentation(str(path)).slides
            for shape in slide.shapes
            if hasattr(shape, "text") and shape.text
        )
    raise ValueError(f"unsupported knowledge document extension: {suffix or '(none)'}")
