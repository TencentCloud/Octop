"""Pre-flight checks before Let's Encrypt issuance."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from typing import Any

import httpx

from octop.config import OctopConfig
from octop.i18n.domains.tls import preflight_message
from octop.infra.setup.tls.listeners import TLS_HTTP_PORT, TLS_HTTPS_PORT
from octop.infra.setup.tls.modes import is_renewal_mode, normalize_domain
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)

# Cloud metadata first (no public Internet). Then CN-reachable and global HTTPS
# echo services — api.ipify.org alone is often unreachable from mainland China.
_METADATA_PUBLIC_IP_URLS: tuple[str, ...] = (
    "http://metadata.tencentyun.com/latest/meta-data/public-ipv4",
    "http://100.100.100.200/latest/meta-data/eipv4",  # Aliyun
)
_PUBLIC_IP_HTTPS_URLS: tuple[str, ...] = (
    "https://4.ipw.cn/",
    "https://api.ip.sb/ip",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://api.ipify.org?format=text",
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)


@dataclass(frozen=True)
class PreflightCheck:
    id: str
    ok: bool
    message: str


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    checks: list[PreflightCheck]
    renewal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [{"id": c.id, "ok": c.ok, "message": c.message} for c in self.checks],
            "renewal": self.renewal,
        }


def _port_available(port: int, host: str = "0.0.0.0") -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _resolve_domain_ips(domain: str) -> set[str]:
    ips: set[str] = set()
    for family, _, _, _, sockaddr in socket.getaddrinfo(
        domain, 80, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    ):
        if family in (socket.AF_INET, socket.AF_INET6):
            ips.add(str(sockaddr[0]))
    return ips


def _parse_public_ipv4(text: str) -> str | None:
    """Extract a non-private IPv4 from a plain or noisy echo response."""
    raw = (text or "").strip()
    if not raw:
        return None
    candidates: list[str] = []
    first = raw.splitlines()[0].strip().split()[0] if raw.split() else ""
    if first:
        candidates.append(first)
    candidates.extend(_IPV4_RE.findall(raw))
    for candidate in candidates:
        try:
            addr = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not isinstance(addr, ipaddress.IPv4Address) or not addr.is_global:
            continue
        return str(addr)
    return None


def _fetch_public_ip_from_urls(urls: tuple[str, ...], *, timeout: float) -> str | None:
    for url in urls:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                ip = _parse_public_ipv4(response.text)
                if ip:
                    return ip
        except httpx.HTTPError as exc:
            logger.debug("public IP probe failed for %s: %s", url, exc)
    return None


def _fetch_public_ip(timeout: float = 4.0) -> str | None:
    """Best-effort public IPv4 via cloud metadata, then HTTPS echo services."""
    ip = _fetch_public_ip_from_urls(_METADATA_PUBLIC_IP_URLS, timeout=min(timeout, 1.5))
    if ip:
        return ip
    return _fetch_public_ip_from_urls(_PUBLIC_IP_HTTPS_URLS, timeout=timeout)


def run_preflight(domain: str, config: OctopConfig, *, locale: str = "en") -> PreflightResult:
    """Verify bind host, ports, and DNS before ACME issuance or renewal."""
    loc = normalize_locale(locale)
    domain = normalize_domain(domain)
    renewal = is_renewal_mode(config)
    checks: list[PreflightCheck] = []

    if not domain:
        checks.append(
            PreflightCheck(
                "domain",
                False,
                preflight_message("domain", variant="fail", locale=loc),
            )
        )
        return PreflightResult(ok=False, checks=checks, renewal=renewal)

    bind_ok = config.bind_host == "0.0.0.0"
    checks.append(
        PreflightCheck(
            "bind_host",
            bind_ok,
            preflight_message(
                "bind_host",
                variant="ok" if bind_ok else "fail",
                locale=loc,
                bind_host=config.bind_host,
            ),
        )
    )

    if renewal:
        checks.append(
            PreflightCheck(
                "dual_port",
                True,
                preflight_message(
                    "dual_port",
                    variant="ok",
                    locale=loc,
                    http_port=config.tls.http_port,
                    https_port=config.port,
                ),
            )
        )
    else:
        if config.tls.enabled:
            checks.append(
                PreflightCheck(
                    "tls_enabled",
                    False,
                    preflight_message("tls_enabled", variant="fail", locale=loc),
                )
            )

        port_ok = config.port == TLS_HTTP_PORT
        checks.append(
            PreflightCheck(
                "port",
                port_ok,
                preflight_message(
                    "port",
                    variant="ok" if port_ok else "fail",
                    locale=loc,
                    port=config.port,
                    http_port=TLS_HTTP_PORT,
                ),
            )
        )

        port_443_ok = _port_available(TLS_HTTPS_PORT)
        checks.append(
            PreflightCheck(
                "port_443",
                port_443_ok,
                preflight_message(
                    "port_443",
                    variant="ok" if port_443_ok else "fail",
                    locale=loc,
                    https_port=TLS_HTTPS_PORT,
                ),
            )
        )

    try:
        domain_ips = _resolve_domain_ips(domain)
    except socket.gaierror as exc:
        checks.append(
            PreflightCheck(
                "dns",
                False,
                preflight_message(
                    "dns",
                    variant="fail",
                    locale=loc,
                    domain=domain,
                    error=str(exc),
                ),
            )
        )
        domain_ips = set()

    public_ip = _fetch_public_ip()
    if public_ip is None:
        checks.append(
            PreflightCheck(
                "public_ip",
                False,
                preflight_message("public_ip", variant="fail", locale=loc),
            )
        )
    elif not domain_ips:
        if not any(c.id == "dns" for c in checks):
            checks.append(
                PreflightCheck(
                    "dns",
                    False,
                    preflight_message(
                        "dns",
                        variant="fail_empty",
                        locale=loc,
                        domain=domain,
                    ),
                )
            )
    else:
        dns_ok = public_ip in domain_ips
        checks.append(
            PreflightCheck(
                "dns",
                dns_ok,
                preflight_message(
                    "dns",
                    variant="ok" if dns_ok else "fail_mismatch",
                    locale=loc,
                    domain=domain,
                    public_ip=public_ip,
                    resolved_ips=sorted(domain_ips),
                ),
            )
        )

    ok = all(c.ok for c in checks)
    return PreflightResult(ok=ok, checks=checks, renewal=renewal)
