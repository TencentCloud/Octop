"""Unit tests for SSL error detection helpers."""

from __future__ import annotations

from octop.infra.utils.ssl_errors import looks_like_ssl_error


def test_looks_like_ssl_error_record_layer() -> None:
    assert looks_like_ssl_error(
        "Failed to fetch hot rankings: [SSL: RECORD_LAYER_FAILURE] "
        "record layer failure (_ssl.c:1081)"
    )


def test_looks_like_ssl_error_certificate_verify() -> None:
    assert looks_like_ssl_error(
        "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>"
    )


def test_looks_like_ssl_error_handshake() -> None:
    assert looks_like_ssl_error("ssl handshake failure")


def test_looks_like_ssl_error_rejects_unrelated() -> None:
    assert not looks_like_ssl_error("Download failed: HTTP 404")
    assert not looks_like_ssl_error("connection timed out")
    assert not looks_like_ssl_error("")
