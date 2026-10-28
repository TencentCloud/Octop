"""Regression tests for non-UTF-8-safe values in DB repos.

Two separate failure modes are covered here.

``secrets.v`` is declared ``BLOB NOT NULL``, but SQLite is dynamically typed:
a row written by an external tool comes back as ``str`` and ``bytes(str)``
raises ``TypeError``. ``SecretRepo.get()`` runs on the ``server.start()`` path
(``_ensure_jwt_secret``), so one such row stopped the whole service from
booting.

``thread_messages.message_json`` is a TEXT column. SQLite stores lone
surrogates and truncated multibyte sequences without complaint, but the next
``SELECT`` raises ``OperationalError: Could not decode to UTF-8 column``.
Because the history endpoint re-reads the row on every poll, the thread stayed
broken forever.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator


from octop.infra.db.repos.secrets import SecretRepo, _as_bytes
from octop.infra.db.repos.thread_messages import (
    ThreadMessageRepo,
    _as_text,
    _scrub_text,
)

# Invalid UTF-8: an encoded surrogate (ED A0 BD), as produced by a cut-off
# emoji in model output.
BAD_BYTES = b'{"type":"ai","data":{"content":"\xed\xa0\xbd broken"}}'


class _MiniPool:
    """Minimal stand-in exposing only ``connect()`` so the real repo runs."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            "CREATE TABLE thread_messages("
            "thread_id TEXT, seq INTEGER, message_id TEXT, role TEXT, "
            "message_json TEXT, created_at INTEGER)"
        )

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        yield self._conn


def _insert_bad_row(pool: _MiniPool, thread_id: str = "t1") -> None:
    pool._conn.execute(
        "INSERT INTO thread_messages VALUES (?, 1, 'm1', 'ai', CAST(? AS TEXT), 0)",
        (thread_id, BAD_BYTES),
    )
    pool._conn.commit()


# ---------------------------------------------------------------- secrets


def test_as_bytes_accepts_str() -> None:
    assert _as_bytes("abc") == b"abc"


def test_as_bytes_accepts_blob() -> None:
    assert _as_bytes(b"abc") == b"abc"


def test_secret_repo_reads_text_typed_row() -> None:
    """A TEXT-typed secret must be returned as bytes, not crash boot."""

    class _Row:
        def __init__(self) -> None:
            self._rows = [{"v": "plain-text-secret"}]

        def fetchone(self) -> dict[str, str]:
            return self._rows[0]

    class _Conn:
        def __enter__(self) -> _Conn:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def execute(self, *args: object, **kwargs: object) -> _Row:
            return _Row()

    class _Pool:
        def connect(self) -> _Conn:
            return _Conn()

    assert SecretRepo(_Pool()).get("jwt") == b"plain-text-secret"  # type: ignore[arg-type]


# ------------------------------------------------------- scrub / decode


def test_scrub_text_removes_lone_surrogate() -> None:
    scrubbed = _scrub_text('{"a":"\ud83d"}')
    assert "\ufffd" in scrubbed
    assert scrubbed.encode("utf-8")  # must not raise


def test_scrub_text_is_noop_for_valid_input() -> None:
    text = '{"a":"正常的 emoji 😀"}'
    assert _scrub_text(text) == text


def test_scrub_text_accepts_bytes() -> None:
    assert "\ufffd" in _scrub_text(BAD_BYTES)


def test_as_text_decodes_invalid_bytes() -> None:
    decoded = _as_text(BAD_BYTES)
    assert "broken" in decoded
    assert decoded.encode("utf-8")


# --------------------------------------------------- repo read tolerance


def test_page_survives_non_utf8_row() -> None:
    """The exact production failure: history must not 500 on a bad row."""
    pool = _MiniPool()
    _insert_bad_row(pool)

    rows, has_more = ThreadMessageRepo(pool).page("t1", limit=10)  # type: ignore[arg-type]

    assert len(rows) == 1
    assert has_more is False
    assert "\ufffd" in rows[0].message_json


def test_page_returns_clean_text_for_scrubbed_row() -> None:
    pool = _MiniPool()
    payload = _scrub_text('{"type":"ai","data":{"content":"\ud83d tail"}}')
    pool._conn.execute(
        "INSERT INTO thread_messages VALUES ('t2', 1, 'm2', 'ai', ?, 0)",
        (payload,),
    )
    pool._conn.commit()

    rows, _ = ThreadMessageRepo(pool).page("t2", limit=10)  # type: ignore[arg-type]

    assert len(rows) == 1
    assert rows[0].message_json == payload
