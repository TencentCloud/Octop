"""tests/unit/api/test_content_disposition.py"""

from __future__ import annotations

import unicodedata

from starlette.responses import Response

from octop.api.common.content_disposition import content_disposition


def test_ascii_filename() -> None:
    assert content_disposition("logo.png") == 'attachment; filename="logo.png"'


def test_inline_disposition() -> None:
    assert content_disposition("doc.pdf", disposition="inline") == 'inline; filename="doc.pdf"'


def test_quotes_escaped() -> None:
    assert content_disposition('say "hi".txt') == 'attachment; filename="say \\"hi\\".txt"'


def test_non_ascii_uses_rfc5987_with_download_ext_fallback() -> None:
    value = content_disposition("1783510288_地球介绍.pptx")
    assert 'filename="download.pptx"' in value
    assert "filename*=UTF-8''" in value
    assert "%E5%9C%B0%E7%90%83%E4%BB%8B%E7%BB%8D" in value
    # Starlette/ASGI requires latin-1-encodable header values
    Response(content=b"x", headers={"Content-Disposition": value})


def test_non_ascii_extension_only_keeps_suffix() -> None:
    value = content_disposition("日本語.pdf")
    assert 'filename="download.pdf"' in value
    assert "%E6%97%A5%E6%9C%AC%E8%AA%9E" in value


def test_non_ascii_without_extension() -> None:
    value = content_disposition("报告")
    assert 'filename="download"' in value
    assert "filename*=UTF-8''" in value


def test_strips_directory_components() -> None:
    assert content_disposition("/outbound/report.pdf") == 'attachment; filename="report.pdf"'
    assert content_disposition(r"C:\Users\me\report.pdf") == 'attachment; filename="report.pdf"'


def test_control_characters_never_reach_the_ascii_form() -> None:
    """A CR/LF/NUL in a stored name makes the transport reject the whole response."""
    assert content_disposition("evil\nname.txt") == 'attachment; filename="evil_name.txt"'
    assert content_disposition("evil\rname.txt") == 'attachment; filename="evil_name.txt"'
    assert content_disposition("evil\r\nname.txt") == 'attachment; filename="evil__name.txt"'
    assert content_disposition("evil\x00name.txt") == 'attachment; filename="evil_name.txt"'
    assert content_disposition("evil\x1fname.txt") == 'attachment; filename="evil_name.txt"'
    assert content_disposition("evil\x7fname.txt") == 'attachment; filename="evil_name.txt"'
    assert content_disposition("evil\tname.txt") == 'attachment; filename="evil_name.txt"'


def test_quoted_form_and_rfc5987_fallback_keep_no_control_characters() -> None:
    for filename in ("\x01\x02", "a\x1fb", "evil\nname.txt", "ré\x01sumé.pdf", "报告\n2.pdf"):
        value = content_disposition(filename)
        assert not [c for c in value if unicodedata.category(c) == "Cc"], value
        Response(content=b"x", headers={"Content-Disposition": value})
