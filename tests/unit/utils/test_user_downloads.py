from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from itertools import count
from pathlib import Path
from threading import Barrier

import pytest

from octop.infra.utils import user_downloads
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


def test_concurrent_downloads_do_not_overwrite_each_other(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "Downloads").mkdir()
    choose_path = user_downloads.unique_download_path
    ready = Barrier(2)
    calls = count()

    def choose_before_either_write(filename: str, *, home: Path | None = None) -> Path:
        path = choose_path(filename, home=home)
        if next(calls) < 2:
            ready.wait(timeout=5)
        return path

    monkeypatch.setattr(user_downloads, "unique_download_path", choose_before_either_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(save_user_download, "report.txt", data, home=tmp_path)
            for data in (b"first", b"second")
        ]
        first, second = [future.result(timeout=10) for future in futures]

    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_download_write_errors_are_propagated(tmp_path: Path, monkeypatch) -> None:
    def deny_write(*args, **kwargs):
        raise PermissionError("download directory is read-only")

    monkeypatch.setattr(Path, "open", deny_write)
    with pytest.raises(PermissionError, match="read-only"):
        save_user_download("report.txt", b"contents", home=tmp_path)


def test_local_dashboard_request_requires_loopback_host_and_peer() -> None:
    assert is_local_dashboard_request(_Req("127.0.0.1:8088", "127.0.0.1"))
    assert is_local_dashboard_request(_Req("localhost:8088", "127.0.0.1"))
    assert not is_local_dashboard_request(_Req("octop.example", "127.0.0.1"))
    assert not is_local_dashboard_request(_Req("127.0.0.1:8088", "8.8.8.8"))


def test_request_hostname_parses_ipv6() -> None:
    assert request_hostname("[::1]:8088") == "::1"
