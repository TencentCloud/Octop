"""Make httpx honor CIDR entries in ``NO_PROXY`` (Windows / macOS / Linux).

httpx 0.28 maps ``NO_PROXY=192.168.0.0/16`` to the mount key
``all://192.168.0.0/16``.  ``httpx.URL`` treats ``/16`` as a path, so
``URLPattern`` exact-matches host ``192.168.0.0`` and LAN hosts such as
``192.168.103.101`` fall through to ``HTTP_PROXY``.

This module patches ``URLPattern.matches`` and ``get_environment_proxies``
once at process start.  Extra compatibility beyond upstream httpx:

- split ``NO_PROXY`` on ``,`` **and** ``;`` (Windows env / ProxyOverride)
- emit parseable IPv6 CIDR mount keys (``all://[addr]/prefix``) so Client
  construction does not raise ``InvalidURL``
- always bypass loopback (``127.0.0.1``, ``::1``, ``localhost``) so macOS
  System Configuration / Windows registry proxies do not capture local servers
"""

from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Any

_PATCHED_ATTR = "_octop_cidr_no_proxy"

# macOS System Configuration / Windows Internet Settings often enable an HTTP
# proxy with no exception list.  httpx then proxies loopback (local mock
# servers, health checks).  curl-style NO_PROXY almost always includes these.
_LOOPBACK_NO_PROXY = ("127.0.0.1", "::1", "localhost")


def split_no_proxy_hosts(raw: str) -> list[str]:
    """Split a ``NO_PROXY`` / ProxyOverride value into host tokens.

    Windows uses ``;`` in the registry and often in the environment; Unix
    and curl use ``,``.  Quotes around a token are stripped.
    """
    if not raw:
        return []
    hosts: list[str] = []
    for part in raw.replace(";", ",").split(","):
        host = part.strip().strip("'\"")
        if host:
            hosts.append(host)
    return hosts


def _unwrap_ip_literal(hostname: str) -> str:
    """Turn ``[2001:db8::]/32`` or ``[::1]`` into a form ``ip_network`` accepts."""
    if not hostname.startswith("["):
        return hostname
    end = hostname.find("]")
    if end == -1:
        return hostname
    return hostname[1:end] + hostname[end + 1 :]


def cidr_network_from_host(hostname: str) -> IPv4Network | IPv6Network | None:
    """Parse a NO_PROXY token as CIDR.  Exact IPs (no ``/``) return None."""
    candidate = _unwrap_ip_literal(hostname.strip())
    if "/" not in candidate:
        return None
    try:
        network = ip_network(candidate, strict=False)
    except ValueError:
        return None
    if not isinstance(network, (IPv4Network, IPv6Network)):
        return None
    return network


def cidr_network_from_mount_pattern(pattern: str) -> IPv4Network | IPv6Network | None:
    """Recover a CIDR from an httpx proxy mount key such as ``all://192.168.0.0/16``."""
    rest = pattern.split("://", 1)[1] if "://" in pattern else pattern
    return cidr_network_from_host(rest)


def no_proxy_mount_key(hostname: str) -> str:
    """Mount key for one ``NO_PROXY`` token, CIDR-safe for IPv4 and IPv6."""
    if "://" in hostname:
        return hostname
    network = cidr_network_from_host(hostname)
    if network is not None:
        if isinstance(network, IPv6Network):
            return f"all://[{network.network_address}]/{network.prefixlen}"
        return f"all://{network.network_address}/{network.prefixlen}"
    from httpx._utils import is_ipv4_hostname, is_ipv6_hostname

    if is_ipv4_hostname(hostname):
        return f"all://{hostname}"
    if is_ipv6_hostname(hostname):
        return f"all://[{hostname}]"
    if hostname.lower() == "localhost":
        return f"all://{hostname}"
    return f"all://*{hostname}"


def get_environment_proxies() -> dict[str, str | None]:
    """httpx ``get_environment_proxies`` with CIDR and ``;``-separated NO_PROXY."""
    import httpx._utils as utils

    proxy_info = utils.getproxies()  # type: ignore[attr-defined]
    mounts: dict[str, str | None] = {}
    for scheme in ("http", "https", "all"):
        value = proxy_info.get(scheme)
        if value:
            mounts[f"{scheme}://"] = value if "://" in value else f"http://{value}"
    hosts = split_no_proxy_hosts(proxy_info.get("no") or "")
    if "*" in hosts:
        return {}
    seen: set[str] = set()
    for hostname in (*hosts, *_LOOPBACK_NO_PROXY):
        if hostname.lower() == "<local>":
            # Windows ProxyOverride token; loopback mounts cover the common case.
            continue
        key = no_proxy_mount_key(hostname)
        if key in seen:
            continue
        seen.add(key)
        mounts[key] = None
    return mounts


def install_httpx_cidr_no_proxy() -> None:
    """Idempotent process-wide patch.  No-op when httpx is not installed."""
    try:
        import httpx._client as client_mod
        import httpx._utils as utils
    except ImportError:
        return
    if getattr(utils.URLPattern.matches, _PATCHED_ATTR, False):
        return

    orig_matches = utils.URLPattern.matches

    def matches(self: Any, other: Any) -> bool:
        network = cidr_network_from_mount_pattern(self.pattern)
        if network is not None:
            if self.scheme and self.scheme != other.scheme:
                return False
            try:
                addr = ip_address(other.host)
            except ValueError:
                return False
            if addr not in network:
                return False
            return self.port is None or self.port == other.port
        return bool(orig_matches(self, other))

    setattr(matches, _PATCHED_ATTR, True)
    utils.URLPattern.matches = matches  # type: ignore[method-assign]
    utils.get_environment_proxies = get_environment_proxies
    client_mod.get_environment_proxies = get_environment_proxies  # type: ignore[attr-defined]
