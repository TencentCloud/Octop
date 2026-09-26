"""Tests for optional knowledge-base OCR configuration and routing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from octop.infra.knowledge import ocr
from octop.infra.knowledge.parse import parse_document


def test_ocr_disabled_by_default() -> None:
    capability = ocr.get_ocr_capability(lambda _key: None)

    assert capability["enabled"] is False
    assert capability["backend"] == "onnx"
    assert capability["usable"] is False


def test_set_local_ocr_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    values: dict[str, str] = {}
    monkeypatch.setattr(ocr, "local_ocr_deps_available", lambda: True)

    ocr.set_ocr_settings(
        values.__setitem__,
        enabled=True,
        backend="onnx",
        model=None,
        provider_id=None,
    )

    assert values == {
        "knowledge_ocr_enabled": "true",
        "knowledge_ocr_backend": "onnx",
        "knowledge_ocr_model": "rapidocr",
        "knowledge_ocr_provider_id": "",
    }


def test_remote_ocr_requires_image_capable_model() -> None:
    provider = SimpleNamespace(
        enabled=True,
        api_key="secret",
        base_url="https://example.test/v1",
        name="Remote",
        get_models=lambda: [
            {"id": "text-only", "input": ["text"]},
            {"id": "vision-1", "input": ["text", "image"]},
        ],
    )
    repo = SimpleNamespace(get=lambda provider_id: provider if provider_id == 7 else None)
    values: dict[str, str] = {}

    with pytest.raises(ValueError, match="provider is not ready"):
        ocr.set_ocr_settings(
            values.__setitem__,
            enabled=True,
            backend="remote",
            model="text-only",
            provider_id="7",
            provider_repo=repo,
        )

    ocr.set_ocr_settings(
        values.__setitem__,
        enabled=True,
        backend="remote",
        model="vision-1",
        provider_id="7",
        provider_repo=repo,
    )
    assert ocr.get_ocr_capability(values.get, repo)["usable"] is True


def test_image_and_blank_pdf_use_ocr(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"not-decoded-by-the-fake")
    pdf = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf.open("wb") as output:
        writer.write(output)
    calls: list[Path] = []

    def fake_ocr(path: Path) -> str:
        calls.append(path)
        return "recognized text"

    assert parse_document(image, ocr=fake_ocr) == "recognized text"
    assert parse_document(pdf, ocr=fake_ocr) == "recognized text"
    assert calls == [image, pdf]


def test_text_pdf_does_not_require_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "text.pdf"
    pdf.write_bytes(b"placeholder")

    class Page:
        @staticmethod
        def extract_text() -> str:
            return "embedded text"

    monkeypatch.setattr(
        "pypdf.PdfReader",
        lambda _path: SimpleNamespace(pages=[Page()]),
    )

    def unexpected_ocr(_path: Path) -> str:
        raise AssertionError("OCR must not run for a text PDF")

    assert parse_document(pdf, ocr=unexpected_ocr) == "embedded text"


def test_image_requires_enabled_ocr(tmp_path: Path) -> None:
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"image")

    with pytest.raises(RuntimeError, match="OCR is not enabled"):
        parse_document(image)


def _stub_pdf(monkeypatch: pytest.MonkeyPatch, texts: list[str]) -> Path:
    """Point PdfReader at pages that extract to *texts*, as in the #837 report."""
    pages = [SimpleNamespace(extract_text=lambda text=text: text) for text in texts]
    monkeypatch.setattr("pypdf.PdfReader", lambda _path: SimpleNamespace(pages=pages))
    return Path("/not-read/synthetic.pdf")


def _recording_ocr(calls: list[Path], text: str = "OCR text"):
    def extract(path: Path) -> str:
        calls.append(path)
        return text

    return extract


def test_pdf_glyph_garbage_text_layer_uses_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-empty but glyph-encoded text layer must not pass as parsed (#837).

    Pre-fix the whole-file "is there any text?" test saw ``/G21/G22/G23/G24`` as
    content, skipped OCR, and indexed the garbage.
    """
    pdf = _stub_pdf(monkeypatch, ["/G21/G22/G23/G24", ""])
    calls: list[Path] = []

    assert parse_document(pdf, ocr=_recording_ocr(calls)) == "OCR text"
    assert calls == [pdf]


def test_pdf_cid_text_layer_uses_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _stub_pdf(monkeypatch, ["(cid:12)(cid:13)(cid:14)"])
    calls: list[Path] = []

    assert parse_document(pdf, ocr=_recording_ocr(calls)) == "OCR text"
    assert calls == [pdf]


def test_pdf_mixed_text_and_scan_pages_use_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """One readable page must not make the whole file skip OCR for its scans."""
    pdf = _stub_pdf(monkeypatch, ["real page text", "", "another page"])
    calls: list[Path] = []

    assert parse_document(pdf, ocr=_recording_ocr(calls)) == "OCR text"
    assert calls == [pdf]


def test_pdf_keeps_embedded_text_when_ocr_returns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When OCR yields nothing we keep what did extract rather than blank it out."""
    pdf = _stub_pdf(monkeypatch, ["real page text", ""])

    assert parse_document(pdf, ocr=lambda _path: "") == "real page text\n"


def test_pdf_prose_containing_paths_does_not_use_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Path-like tokens in ordinary prose must not be mistaken for glyph garbage."""
    text = "see /usr/local/bin and /etc/hosts for the config"
    pdf = _stub_pdf(monkeypatch, [text])

    def unexpected_ocr(_path: Path) -> str:
        raise AssertionError("OCR must not run for a text PDF")

    assert parse_document(pdf, ocr=unexpected_ocr) == text


def test_pdf_glyph_run_inside_prose_is_not_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    """A glyph run that does not dominate the page is left alone."""
    text = "prefix /G21/G22/G23/G24 and a long tail of normal words here"
    pdf = _stub_pdf(monkeypatch, [text])

    def unexpected_ocr(_path: Path) -> str:
        raise AssertionError("OCR must not run for a text PDF")

    assert parse_document(pdf, ocr=unexpected_ocr) == text


@pytest.mark.parametrize(
    ("text", "usable"),
    [
        ("", False),
        ("   \n\t ", False),
        ("/G21/G22/G23/G24", False),
        ("(cid:12)(cid:13)(cid:14)", False),
        ("plain prose", True),
        ("12345", True),
        ("/usr/local/bin", True),
        ("prefix /G21/G22/G23/G24 and a long tail of normal words here", True),
    ],
)
def test_pdf_page_text_usability(text: str, usable: bool) -> None:
    from octop.infra.knowledge.parse import _pdf_page_text_is_usable  # noqa: PLC0415

    assert _pdf_page_text_is_usable(text) is usable


def test_local_ocr_joins_rapidocr_text_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"image")

    def engine(_data: bytes) -> SimpleNamespace:
        return SimpleNamespace(txts=("第一行", "Second line"))

    monkeypatch.setattr(ocr, "_rapidocr_engine", lambda: engine)

    assert ocr._extract_local(image) == "第一行\nSecond line"


def test_remote_ocr_sends_image_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"image")
    messages: list[object] = []

    class Model:
        @staticmethod
        def invoke(value: list[object]) -> SimpleNamespace:
            messages.extend(value)
            return SimpleNamespace(content="remote text")

    monkeypatch.setattr(ocr, "build_probe_chat_model", lambda *_a, **_k: Model())
    extractor = ocr._RemoteOcr(SimpleNamespace(), "vision")

    assert extractor(image) == "remote text"
    content = messages[0].content
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def _remote_extractor(monkeypatch: pytest.MonkeyPatch, reply: object) -> ocr._RemoteOcr:
    """Build a ``_RemoteOcr`` whose model returns *reply* (str or a per-call sequence)."""

    class Model:
        @staticmethod
        def invoke(_value: list[object]) -> SimpleNamespace:
            if isinstance(reply, list):
                return SimpleNamespace(content=reply.pop(0))
            return SimpleNamespace(content=reply)

    monkeypatch.setattr(ocr, "build_probe_chat_model", lambda *_a, **_k: Model())
    return ocr._RemoteOcr(SimpleNamespace(), "vision")


@pytest.mark.parametrize(
    "refusal",
    [
        "No image was attached. Please upload an image.",
        "I don't see an image attached to your message. Please upload the image you'd "
        "like me to transcribe, and I'll provide the exact transcription.",
        "未收到图片，请上传图片后重试。",
    ],
)
def test_remote_ocr_ignores_no_image_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    """A refusal is not source text: indexing it would mark the document ready with junk."""
    image = tmp_path / "scan.png"
    image.write_bytes(b"image")

    assert _remote_extractor(monkeypatch, refusal)(image) == ""


def test_remote_ocr_keeps_long_page_that_mentions_uploading_an_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal filter must not drop real transcriptions that happen to mention an image."""
    image = tmp_path / "scan.png"
    image.write_bytes(b"image")
    page = (
        "No image was attached. Please upload an image. "
        + "发票明细：办公用品 128.00 元，差旅费 340.00 元。" * 12
    )

    assert _remote_extractor(monkeypatch, page)(image) == page


def test_remote_ocr_skips_refusal_page_but_keeps_transcribed_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refusals are dropped per page, so a partly readable document keeps its good pages."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        ocr,
        "_image_inputs",
        lambda _path: iter([(b"page-1", "image/png"), (b"page-2", "image/png")]),
    )

    extractor = _remote_extractor(
        monkeypatch,
        ["No image was attached. Please upload an image.", "第二页正文"],
    )

    assert extractor(pdf) == "第二页正文"
