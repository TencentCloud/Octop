from __future__ import annotations

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
