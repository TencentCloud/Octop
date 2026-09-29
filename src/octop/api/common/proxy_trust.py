"""Decide which reverse proxies may set ``X-Forwarded-*``.

Octop's shipped artifacts all bind ``0.0.0.0`` with no proxy in front
(``docker/docker-compose.yml``, ``fnos/docker/app/docker/docker-compose.yaml``,
and both Dockerfiles set ``OCTOP_BIND_HOST=0.0.0.0``), and the built-in
Let's Encrypt flow *requires* that bind — ``tls_issue_mode`` returns
``TlsIssueMode.NONE`` unless ``bind_host == "0.0.0.0"``. Direct exposure is
therefore the supported topology, not an edge case.

That matters because the login captcha limiter and the invite rate limiter key
on the client address. If ``X-Forwarded-For`` is honoured from any peer, an
attacker on a directly-exposed install *is* the header source and both limiters
are bypassable in a few bytes. So the default is **trust nothing** and proxy
trust is opt-in, via ``trusted_proxies`` / ``OCTOP_TRUSTED_PROXIES``.

The one exception is a non-wildcard bind. ``octop run`` defaults to
``127.0.0.1``, where the service is unreachable from the network and a local
reverse proxy is the overwhelmingly likely topology; breaking those installs on
upgrade would buy nothing, since a local process can already do far worse than
spoof a header. So a loopback/private bind trusts loopback, and says so at
startup.

The returned list is handed to uvicorn as ``forwarded_allow_ips`` (see
``launch.py``). uvicorn's default is ``None``, i.e. *no* proxy-header handling
at all, so before this change nothing in the server honoured
``X-Forwarded-*`` — the API layer reading those headers by hand was the only
path, and it honoured them from any peer. There is deliberately no second
implementation of the trust decision: the API layer reads ``request.client``,
which only the server rewrites.
"""

from __future__ import annotations

from typing import Any

TRUSTED_PROXIES_ENV = "OCTOP_TRUSTED_PROXIES"

#: Loopback peers trusted automatically when the bind is not wildcard.
LOOPBACK_PROXIES: tuple[str, ...] = ("127.0.0.1", "::1")

#: Binds on which the service is reachable off-host, so nothing is trusted.
_WILDCARD_BINDS: frozenset[str] = frozenset({"0.0.0.0", "::", ""})


def trusted_proxy_hosts(config: Any | None) -> list[str]:
    """Return the ``trusted_hosts`` value for ``ProxyHeadersMiddleware``.

    ``config`` is an :class:`~octop.config.OctopConfig` or anything exposing
    ``trusted_proxies`` / ``bind_host``; ``None`` is treated as "no config",
    which means trust nothing.
    """
    if config is None:
        return []

    explicit = [str(h).strip() for h in (getattr(config, "trusted_proxies", None) or [])]
    explicit = [h for h in explicit if h]
    if explicit:
        return explicit

    bind_host = str(getattr(config, "bind_host", "") or "").strip()
    if bind_host in _WILDCARD_BINDS:
        return []
    return list(LOOPBACK_PROXIES)


def is_wildcard_bind(config: Any | None) -> bool:
    """True when the service is reachable from off-host with no proxy in front."""
    if config is None:
        return True
    bind_host = str(getattr(config, "bind_host", "") or "").strip()
    return bind_host in _WILDCARD_BINDS
