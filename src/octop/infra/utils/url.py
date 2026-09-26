"""URL helpers shared across infra and API layers."""

from __future__ import annotations


def format_host_for_url(host: str) -> str:
    """Bracket an IPv6 literal so it survives as a URL authority component.

    uvicorn binds any address containing ``:`` as ``AF_INET6``, so a configured
    ``bind_host`` of ``::1`` is legitimate; ``http://::1:8088`` is not a URL,
    though — the port never splits cleanly from the last address group.
    """
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def normalize_nav_url(raw: str) -> str:
    """``baidu.com`` → ``https://baidu.com``; empty input → ``\"\"``."""
    t = raw.strip()
    if not t:
        return ""
    lower = t.lower()
    if "://" in lower:
        if lower.startswith(("http://", "https://")):
            return t
        return ""
    if t.startswith("//"):
        # Protocol-relative URL (e.g. pasted from a page source): keep the host
        # and force https, instead of producing "https:////host" with an empty
        # host name.
        return f"https://{t[2:]}"
    return f"https://{t}"
