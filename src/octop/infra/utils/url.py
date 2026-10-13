"""URL helpers shared across infra and API layers."""


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
