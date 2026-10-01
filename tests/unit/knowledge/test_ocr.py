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
