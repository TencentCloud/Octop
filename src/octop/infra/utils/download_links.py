"""Short-lived download links for browsers that cannot save a blob.

In-app browsers (WeChat, QQ, DingTalk, …) refuse ``blob:`` downloads, and a
plain API URL needs a JWT that the system browser does not have. The
dashboard hands the bytes it already fetched back to Octop, which keeps them
on disk behind an unguessable token for a few minutes so the link can be
opened anywhere.
"""

from __future__ import annotations

import secrets
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

LINK_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class DownloadLink:
    token: str
    filename: str
    path: Path
    owner_id: int
    expires_at: float


class DownloadLinkStore:
    def __init__(self, *, ttl_seconds: int = LINK_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._links: dict[str, DownloadLink] = {}
        self._lock = threading.Lock()
        self._dir: tempfile.TemporaryDirectory[str] | None = None

    def create(
        self,
        filename: str,
        data: bytes,
        *,
        owner_id: int,
        now: float | None = None,
    ) -> DownloadLink:
        ts = time.time() if now is None else now
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._sweep(ts)
            if self._dir is None:
                self._dir = tempfile.TemporaryDirectory(prefix="octop-download-links-")
            path = Path(self._dir.name) / token
        path.write_bytes(data)
        link = DownloadLink(
            token=token,
            filename=filename,
            path=path,
            owner_id=owner_id,
            expires_at=ts + self.ttl_seconds,
        )
        with self._lock:
            self._links[token] = link
        return link

    def get(self, token: str, *, now: float | None = None) -> DownloadLink | None:
        ts = time.time() if now is None else now
        with self._lock:
            self._sweep(ts)
            return self._links.get(token)

    def _sweep(self, now: float) -> None:
        for token in [t for t, link in self._links.items() if link.expires_at <= now]:
            self._links.pop(token).path.unlink(missing_ok=True)
