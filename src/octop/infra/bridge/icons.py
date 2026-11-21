"""Rewrite peer agent icon URLs for local Bridge shadow experts."""

from __future__ import annotations

from urllib.parse import urlsplit

from octop.infra.agents.experts.avatar import agent_avatar_api_path


def bridge_avatar_api_path(bridge_agent_id: str) -> str:
    """Local avatar URL for a Bridge shadow agent.

    Keep the id unencoded here — the dashboard encodes the path segment the
    same way it does for chat WS / threads (``encodeURIComponent``).
    """
    return agent_avatar_api_path(bridge_agent_id)


def rewrite_remote_icon_url(
    raw: str | None,
    *,
    remote_agent_id: str,
    bridge_agent_id: str | None = None,
) -> str | None:
    """Map a peer ``icon_url`` to something the local dashboard can load.

    - Bundled ``/experts/avatars/…`` paths stay as-is (same assets locally).
    - Absolute CDN / SkillHub ``http(s)://…`` URLs stay as-is.
    - Peer ``/api/agents/{id}/avatar`` (and absolute peer equivalents) become
      the local Bridge proxy avatar path when ``bridge_agent_id`` is set.
      Without a connection, those URLs are dropped (browser cannot auth to the peer).
    - Empty → ``None`` so the UI falls back to ``icon_name``.
    """
    text = str(raw or "").strip()
    if not text:
        return None

    path = text
    query = ""
    if text.startswith("http://") or text.startswith("https://"):
        parts = urlsplit(text)
        path = parts.path or "/"
        query = parts.query or ""
        # External portraits (CDN) — browser can fetch directly.
        if not path.startswith("/api/agents/") and not path.startswith("/experts/"):
            return text

    path_only = path.split("?", 1)[0]
    if path_only.startswith("/experts/"):
        return path_only + (f"?{query}" if query else "")

    # Uploaded workspace avatar (or legacy ``/icon``) → tunnel via Bridge proxy.
    if path_only.endswith("/avatar") or path_only.endswith("/icon"):
        if not bridge_agent_id:
            return None
        return bridge_avatar_api_path(bridge_agent_id)

    # Rare relative path — keep so we do not force a Lucide fallback incorrectly.
    if path_only.startswith("/"):
        return path_only
    _ = remote_agent_id  # reserved for future peer-id-specific rewrites
    return None
