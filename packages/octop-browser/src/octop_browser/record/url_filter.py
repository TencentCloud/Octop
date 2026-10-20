"""URL filtering helpers for browser record/replay artifacts."""

from __future__ import annotations

from urllib.parse import urlsplit

_BROWSER_INTERNAL_PREFIXES = ("chrome://", "devtools://")
_BROWSER_SCAFFOLD_URLS = {"about:blank", "chrome://newtab/", "chrome://newtab"}


def is_transient_auth_or_risk_url(url: str | None) -> bool:
    """Return true for known automatic auth/risk-control redirects.

    Keep this intentionally narrow. These URLs are emitted by sites while
    blocking anonymous/headless traffic and should not become durable replay
    intent for a generic "open these sites" recording. We do *not* filter all
    login pages because recording an explicit login flow must remain possible.
    """
    if not url:
        return False
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()

    if host == "passport.weibo.com" and path.startswith("/visitor/"):
        return True
    if (
        host.endswith("weibo.com")
        and path.startswith("/newlogin")
        and ("url=" in query or "tabtype=" in query or "openloginlayer=" in query)
    ):
        return True
    if host == "wappass.baidu.com" and "/captcha/" in path:
        return True
    if host.endswith("xiaohongshu.com") and path.startswith("/website-login/error"):
        return True
    return False


def is_replayable_page_url(url: str | None) -> bool:
    """Return whether a page URL should be preserved as replay intent."""
    if not url:
        return False
    normalized = url.strip().lower()
    if normalized in _BROWSER_SCAFFOLD_URLS:
        return False
    if normalized.startswith(_BROWSER_INTERNAL_PREFIXES):
        return False
    return not is_transient_auth_or_risk_url(url)
