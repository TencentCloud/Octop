from __future__ import annotations

import os
from pathlib import Path

import pytest

from octop.infra.utils.download_links import DownloadLinkStore


def test_download_link_serves_bytes_until_it_expires() -> None:
    store = DownloadLinkStore(ttl_seconds=60)
    link = store.create("report.docx", b"hello", owner_id=7, now=1000.0)
    assert link.path.read_bytes() == b"hello"
    assert link.expires_at == 1060.0

    found = store.get(link.token, now=1059.0)
    assert found is not None
    assert found.filename == "report.docx"
    assert found.owner_id == 7

    assert store.get(link.token, now=1060.0) is None
    assert not link.path.exists()


def test_download_link_tokens_are_unique_and_unguessable() -> None:
    store = DownloadLinkStore()
    first = store.create("a.txt", b"a", owner_id=1)
    second = store.create("a.txt", b"b", owner_id=1)
    assert first.token != second.token
    assert len(first.token) >= 32
    assert store.get("not-a-token") is None


def test_locked_expired_link_does_not_block_other_links_or_cleanup_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = DownloadLinkStore(ttl_seconds=60)
    expired = store.create("old.txt", b"old", owner_id=1, now=1000)
    live = store.create("live.txt", b"live", owner_id=1, now=1020)
    unlink = Path.unlink

    def locked_unlink(path: Path, *, missing_ok: bool = False) -> None:
        if path == expired.path:
            raise PermissionError("file is in use")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", locked_unlink)
        assert store.get(expired.token, now=1060) is None
        assert store.get(live.token, now=1060) == live
        created = store.create("new.txt", b"new", owner_id=1, now=1060)
        assert created.path.read_bytes() == b"new"
        assert expired.path.exists()

    assert store.get(live.token, now=1061) == live
    assert not expired.path.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows denies deletion of an open file")
def test_expired_download_with_open_handle_is_cleaned_after_close() -> None:
    store = DownloadLinkStore(ttl_seconds=60)
    link = store.create("report.txt", b"payload", owner_id=1, now=1000)
    with link.path.open("rb") as handle:
        assert store.get(link.token, now=1060) is None
        assert handle.read() == b"payload"
    assert store.get(link.token, now=1061) is None
    assert not link.path.exists()
