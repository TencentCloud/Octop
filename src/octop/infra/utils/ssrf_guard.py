"""Outbound HTTPS URL validation — mitigates SSRF (CWE-918).

Self-hosted installs can opt specific LAN targets out of the private-address
check with ``OCTOP_SSRF_ALLOWLIST`` (comma-separated hosts, ``.suffix``
domains or CIDRs), and let those targets use plain http with
``OCTOP_SSRF_ALLOW_HTTP``. Allowlisted requests are still resolved and pinned
to the validated IP, so DNS rebinding stays blocked. Unset, nothing changes.
"""

from __future__ import annotations

import asyncio
import functools
import ipaddress
import os
import socket
import typing
from urllib.parse import urlparse, urlunparse

import httpx
from httpcore._backends.auto import AutoBackend
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkStream


class UnsafeOutboundUrl(ValueError):
    """Raised when a URL must not be fetched server-side."""


# Hostnames that never refer to a public Internet endpoint (Docker Desktop, etc.).
_LOCAL_HOSTNAMES = frozenset(
    {
        "localhost",
        "host.docker.internal",
        "gateway.docker.internal",
    }
)
_LOCAL_HOST_SUFFIXES = (".local", ".localhost", ".internal")

ALLOWLIST_ENV = "OCTOP_SSRF_ALLOWLIST"
ALLOW_HTTP_ENV = "OCTOP_SSRF_ALLOW_HTTP"
_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@functools.lru_cache(maxsize=8)
def _parse_allowlist(raw: str) -> tuple[frozenset[str], tuple[str, ...], tuple[_IPNetwork, ...]]:
    hosts: set[str] = set()
    suffixes: list[str] = []
    networks: list[_IPNetwork] = []
    for item in raw.split(","):
        entry = item.strip().lower().rstrip(".")
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            if entry.startswith("."):
                suffixes.append(entry)
            else:
                hosts.add(entry)
    return frozenset(hosts), tuple(suffixes), tuple(networks)


def _allowlist() -> tuple[frozenset[str], tuple[str, ...], tuple[_IPNetwork, ...]]:
    return _parse_allowlist(os.environ.get(ALLOWLIST_ENV, ""))


def _ip_in_allowlist(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in network for network in _allowlist()[2])


def _host_in_allowlist(host: str) -> bool:
    """True when the admin allowlisted ``host`` by name, suffix or (for IPs) CIDR."""
    hosts, suffixes, _ = _allowlist()
    return host in hosts or host.endswith(suffixes) or _ip_in_allowlist(host)


def _allow_http() -> bool:
    return os.environ.get(ALLOW_HTTP_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def is_private_or_local_host(host: str) -> bool:
    """True for loopback / RFC1918 / link-local literals and well-known local names.

    Used by MCP connector URL validation so self-hosted LAN endpoints are allowed
    without weakening the outbound SSRF guard used for OAuth / provider probes.
    """
    normalized = host.lower().rstrip(".")
    if not normalized:
        return False
    if normalized in _LOCAL_HOSTNAMES:
        return True
    if normalized.endswith(_LOCAL_HOST_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private or addr.is_link_local


def _parse_https_host(url: str) -> tuple[str, int | None]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and host and _allow_http() and _host_in_allowlist(host)
    ):
        raise UnsafeOutboundUrl("only https URLs are allowed")
    if not host:
        raise UnsafeOutboundUrl("missing hostname")
    return host, parsed.port


def _check_ip_not_private(ip_str: str, *, host: str = "") -> None:
    if _ip_in_allowlist(ip_str) or (host and _host_in_allowlist(host)):
        return
    addr = ipaddress.ip_address(ip_str)
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    ):
        raise UnsafeOutboundUrl("private or reserved IP addresses are not allowed")


def _check_ip_literal(host: str) -> None:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return
    _check_ip_not_private(host)


def _check_resolved_ip(ip_str: str, *, host: str) -> None:
    _check_ip_not_private(ip_str, host=host)


def issuer_base_domain(issuer: str) -> str:
    host = (urlparse(issuer).hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def host_allowed_for_issuer(host: str, issuer: str) -> bool:
    normalized = host.lower().rstrip(".")
    issuer_host = (urlparse(issuer).hostname or "").lower()
    base = issuer_base_domain(issuer)
    if normalized in {issuer_host, base}:
        return True
    return normalized.endswith(f".{base}")


def validate_https_url(url: str, *, field: str = "url") -> str:
    """Reject non-https URLs and literal private/reserved IPs."""
    host, _ = _parse_https_host(url)
    if host == "localhost" and not _host_in_allowlist(host):
        raise UnsafeOutboundUrl(f"{field}: localhost is not allowed")
    _check_ip_literal(host)
    return url


async def validate_https_url_resolved(url: str, *, field: str = "url") -> str:
    """Also resolve DNS and reject private/reserved addresses."""
    validate_https_url(url, field=field)
    await _resolve_validated_ip(url)
    return url


async def _resolve_validated_ip(url: str) -> str:
    """Resolve ``url`` and return one validated (public) IP.

    Raises :class:`UnsafeOutboundUrl` if the host cannot be resolved or any
    resolved address is private/reserved.  The caller should pin the returned
    IP for the actual connection to defeat DNS-rebinding (TOCTOU).
    """
    host, port = _parse_https_host(url)
    default_port = 80 if urlparse(url).scheme == "http" else 443
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            host,
            port or default_port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise UnsafeOutboundUrl(f"cannot resolve hostname {host!r}") from exc
    if not infos:
        raise UnsafeOutboundUrl(f"cannot resolve hostname {host!r}")
    for info in infos:
        _check_resolved_ip(info[4][0], host=host)
    return infos[0][4][0]


class _PinnedNetworkBackend(AutoBackend):
    """Resolve the validated host to a fixed IP, while preserving SNI.

    Only requests whose host matches ``_target_host`` are pinned to
    ``_pin_ip``; everything else (e.g. redirects) resolves normally so the
    helper never breaks legitimate cross-host redirects.  The original
    hostname is passed to TLS via httpcore's SNI logic, so certificate
    validation is unaffected by the IP pinning.
    """

    def __init__(self, target_host: str, pin_ip: str) -> None:
        super().__init__()
        self._target_host = target_host
        self._pin_ip = pin_ip

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        if host == self._target_host:
            return await super().connect_tcp(
                self._pin_ip,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )
        return await super().connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class PinnedIPTransport(httpx.AsyncHTTPTransport):
    """httpx transport that pins the validated IP for ``target_host``.

    Swaps the underlying httpcore network backend so the validated host always
    connects to the validated IP — closing the DNS-rebinding window between
    validation and the actual TCP connection (CWE-918).
    """

    def __init__(self, target_host: str, pin_ip: str) -> None:
        super().__init__()
        self._pool._network_backend = _PinnedNetworkBackend(target_host, pin_ip)


async def safe_request(
    method: str,
    url: str,
    *,
    json: typing.Any | None = None,
    data: typing.Any | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> httpx.Response:
    """Validate, resolve, pin the IP, and perform an outbound HTTPS request.

    URL scheme/host must be https and resolve to a public IP (see
    :func:`validate_https_url_resolved`).  The connection is then pinned to the
    validated IP so a malicious DNS change between validation and connection
    cannot redirect the request to an internal address.
    """
    parsed = urlparse(url)
    host, port = _parse_https_host(url)
    pin_ip = await _resolve_validated_ip(url)
    # Rebuild the request URL from validated components so the outbound call
    # does not reuse the original user-controlled string (CWE-918 / CodeQL).
    netloc = f"{host}:{port}" if port is not None else host
    scheme = "http" if parsed.scheme == "http" else "https"
    request_url = urlunparse((scheme, netloc, parsed.path or "/", "", parsed.query, ""))
    transport = PinnedIPTransport(host, pin_ip)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        return await client.request(method, request_url, json=json, data=data, headers=headers)
