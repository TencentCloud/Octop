"""Secrets table access."""

from __future__ import annotations

from collections.abc import Callable

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts


def _as_bytes(value: object) -> bytes:
    """Decode a ``secrets.v`` value that SQLite may hand back as TEXT.

    ``secrets.v`` is declared ``BLOB NOT NULL``, but SQLite is dynamically
    typed: a row written by an external repair script (``INSERT ... VALUES
    ('abc')``) comes back as ``str``. ``bytes(str)`` raises ``TypeError``,
    and this repo's ``get()`` sits on the ``server.start()`` path via
    ``_ensure_jwt_secret`` -- so that one row made the whole service fail to
    boot. Accept both shapes instead of trusting the declared column type.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    return bytes(value)


class SecretRepo:
    def __init__(self, db: DatabasePool):
        self._db = db

    def get(self, k: str) -> bytes | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT v FROM secrets WHERE k = ?", (k,)).fetchone()
        return _as_bytes(r["v"]) if r else None

    def get_or_create(self, k: str, factory: Callable[[], bytes]) -> bytes:
        existing = self.get(k)
        if existing is not None:
            return existing
        value = factory()
        with self._db.transaction() as conn:
            # Check again inside transaction to avoid race
            r = conn.execute("SELECT v FROM secrets WHERE k = ?", (k,)).fetchone()
            if r is not None:
                return _as_bytes(r["v"])
            conn.execute(
                "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                (k, value, now_ts()),
            )
        return value

    def rotate(self, k: str, new_value: bytes) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE secrets SET v = ?, rotated_at = ? WHERE k = ?",
                (new_value, now_ts(), k),
            )
