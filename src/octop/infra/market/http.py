"""HTTP reads against the Octop portal and the remote market object origin."""

from __future__ import annotations

import errno
import json
import os
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from octop.infra.market.errors import PortalMarketError

DEFAULT_REMOTE_BASE = "https://download.octop.cloud"
DEFAULT_PORTAL_BASE = "https://octop.cloud"
MARKET_ROOT = "octop/market"

FETCH_TIMEOUT_SECONDS = 8.0
MAX_INDEX_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
READ_CHUNK = 64 * 1024
_LOCAL_NETWORK_ERRNOS = frozenset(
    code
    for name in ("ENETUNREACH", "ENETDOWN", "EHOSTUNREACH", "EHOSTDOWN", "ENONET")
    if (code := getattr(errno, name, None)) is not None
)


def portal_base() -> str:
    """Site origin. An empty ``OCTOP_PORTAL_URL`` disables the remote catalog."""
    if "OCTOP_PORTAL_URL" in os.environ:
        return os.environ.get("OCTOP_PORTAL_URL", "").strip().rstrip("/")
    return DEFAULT_PORTAL_BASE


def remote_base() -> str:
    """Object origin for plugin and expert packages.

    ``OCTOP_MARKET_REMOTE_URL`` overrides the public origin. A bare host is
    treated as ``https://``. An empty or unusable value keeps the default.
    Only the origin is kept, so a pasted path does not change object keys.
    """
    raw = os.environ.get("OCTOP_MARKET_REMOTE_URL", "").strip()
    if not raw:
        return DEFAULT_REMOTE_BASE
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return DEFAULT_REMOTE_BASE
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        origin = f"{origin}:{parsed.port}"
    return origin


def is_market_archive_url(url: str) -> bool:
    """Archives are only downloaded from the configured remote origin."""
    parsed = urlparse(url.strip())
    allowed = urlparse(remote_base())
    if (
        parsed.scheme != allowed.scheme
        or parsed.hostname != allowed.hostname
        or not parsed.path.startswith(f"/{MARKET_ROOT}/")
    ):
        return False
    return allowed.port is None or parsed.port == allowed.port


def is_local_network_failure(exc: BaseException) -> bool:
    """True only for DNS, no-route, and connect timeouts on this host.

    HTTP responses, TLS failures, and other ``URLError`` reasons stay false.
    Those are catalog failures, not a local network outage.
    """
    reason = exc
    if isinstance(exc, URLError) and isinstance(exc.reason, BaseException):
        reason = exc.reason
    if isinstance(reason, socket.gaierror | TimeoutError):
        return True
    return isinstance(reason, OSError) and reason.errno in _LOCAL_NETWORK_ERRNOS


def fetch_json(url: str, *, limit: int) -> Any:
    body = fetch_bytes(url, limit=limit)
    try:
        return json.loads(body.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PortalMarketError("invalid json") from exc


def fetch_bytes(url: str, *, limit: int) -> bytes:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Octop"},
    )
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
            status = int(getattr(response, "status", 200))
            if status == 404:
                raise PortalMarketError("not found", status=404)
            if status >= 400:
                raise PortalMarketError(f"http {status}", status=status)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise PortalMarketError("response too large")
                chunks.append(chunk)
            return b"".join(chunks)
    except PortalMarketError:
        raise
    except HTTPError as exc:
        raise PortalMarketError(f"http {exc.code}", status=exc.code) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None) or exc
        raise PortalMarketError(
            f"unreachable: {reason}",
            network=is_local_network_failure(exc),
        ) from exc
    except TimeoutError as exc:
        raise PortalMarketError("timeout", network=True) from exc
