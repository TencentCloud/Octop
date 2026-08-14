"""Unit tests for supported knowledge-document parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.knowledge.parse import parse_document


def test_parse_plain_text_and_markdown(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    markdown = tmp_path / "readme.md"
    text.write_text("plain notes", encoding="utf-8")
    markdown.write_text("# Heading\n\nbody", encoding="utf-8")

    assert parse_document(text) == "plain notes"
    assert parse_document(markdown) == "# Heading\n\nbody"


def test_parse_pdf_docx_and_pptx(tmp_path: Path) -> None:
    from docx import Document
    from pptx import Presentation
    from pypdf import PdfWriter

    pdf = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf.open("wb") as output:
        writer.write(output)

    docx = tmp_path / "notes.docx"
    document = Document()
    document.add_paragraph("Word notes")
    document.save(docx)

    pptx = tmp_path / "slides.pptx"
    presentation = Presentation()
    presentation.slides.add_slide(presentation.slide_layouts[0]).shapes.title.text = "Slide title"
    presentation.save(pptx)

    assert parse_document(pdf) == ""
    assert parse_document(docx) == "Word notes"
    assert parse_document(pptx) == "Slide title"


def test_parse_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.xlsx"
    path.write_bytes(b"not a spreadsheet")

    with pytest.raises(ValueError, match="unsupported"):
        parse_document(path)
