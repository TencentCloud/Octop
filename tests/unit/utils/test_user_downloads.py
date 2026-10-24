from __future__ import annotations

from pathlib import Path

from octop.infra.utils.user_downloads import (
    is_local_dashboard_request,
    request_hostname,
    sanitize_download_filename,
    save_user_download,
    unique_download_path,
)


class _Client:
    def __init__(self, host: str) -> None:
        self.host = host


class _Req:
    def __init__(self, host: str, peer: str) -> None:
        self.headers = {"host": host}
        self.client = _Client(peer)


def test_sanitize_download_filename_strips_paths() -> None:
    assert sanitize_download_filename("../etc/passwd") == "_etc_passwd"
    assert sanitize_download_filename("") == "download"
    assert sanitize_download_filename("report.pdf") == "report.pdf"


def test_sanitize_download_filename_preserves_short_ascii() -> None:
    # ASCII names within the byte budget are unchanged (backward compatible).
    assert sanitize_download_filename("report.pdf") == "report.pdf"
    assert sanitize_download_filename("a" * 200) == "a" * 200


def test_sanitize_download_filename_bounds_long_ascii_stem() -> None:
    # A 300-char name with a short extension must keep its extension and stay
    # within the byte budget.
    safe = sanitize_download_filename("a" * 300 + ".txt")
    assert safe.endswith(".txt")
    assert len(safe.encode("utf-8")) <= 200
    assert safe[:-4] == "a" * (200 - 4)


def test_sanitize_download_filename_bounds_utf8_bytes() -> None:
    # A 130-emoji name (520 UTF-8 bytes, 260 UTF-16 units) with a short
    # extension must be capped by encoded bytes, not by character count, and
    # the extension must be preserved (#2255).
    long_emoji = "\U0001f600" * 130 + ".txt"
    safe = sanitize_download_filename(long_emoji)
    assert len(safe.encode("utf-8")) <= 200
    assert safe.endswith(".txt")
    assert "\U0001f600" in safe


def test_save_user_download_long_unicode_name(tmp_path: Path) -> None:
    # Reproduces #2255: the long emoji name previously raised OSError when the
    # encoded filename exceeded the filesystem per-component limit.
    path = save_user_download("\U0001f600" * 130 + ".txt", b"hello", home=tmp_path)
    assert path.read_bytes() == b"hello"
    assert path.name.endswith(".txt")
    assert len(path.name.encode("utf-8")) <= 200


def test_unique_download_path_avoids_collision(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    first = unique_download_path("note.txt", home=tmp_path)
    first.write_text("a", encoding="utf-8")
    second = unique_download_path("note.txt", home=tmp_path)
    assert second.name == "note (1).txt"


def test_save_user_download_writes_bytes(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    path = save_user_download("hello.txt", b"hi", home=tmp_path)
    assert path.read_bytes() == b"hi"
    assert path.parent == downloads


def test_local_dashboard_request_requires_loopback_host_and_peer() -> None:
    assert is_local_dashboard_request(_Req("127.0.0.1:8088", "127.0.0.1"))
    assert is_local_dashboard_request(_Req("localhost:8088", "127.0.0.1"))
    assert not is_local_dashboard_request(_Req("octop.example", "127.0.0.1"))
    assert not is_local_dashboard_request(_Req("127.0.0.1:8088", "8.8.8.8"))


def test_request_hostname_parses_ipv6() -> None:
    assert request_hostname("[::1]:8088") == "::1"
