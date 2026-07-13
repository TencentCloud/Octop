"""Helpers for attaching dashboard / chat UI to harness-browser sessions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from octop.api.deps import current_user
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _is_session_alive(sess: Any, *, timeout: float = 2.0) -> bool:
    """Probe a cached session with a cheap CDP round-trip.

    A previously-registered session's underlying CDP WebSocket can die out
    from under us (browser crash, OOM kill, network blip) while the Python
    object stays in ``_registry`` forever. Reusing a dead session makes every
    subsequent action fail with confusing low-level errors like
    ``no close frame received or sent``. This does a fast, side-effect-free
    ``Runtime.evaluate`` to confirm the CDP connection is still usable.
    """
    try:
        await asyncio.wait_for(
            sess._internal.client.send(  # noqa: SLF001
                "Runtime.evaluate", {"expression": "1", "returnByValue": True}
            ),
            timeout=timeout,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("cached harness session failed health check: %s", exc)
        return False


async def resolve_harness_session(
    profile_hint: str | None,
    *,
    server: Any | None = None,
    agent_id: str | None = None,
) -> Any:
    """Return a live :class:`harness_browser.BrowserSession` for ``profile_hint``.

    Resolution order:
      1. Exact profile name when present in the in-process registry
      2. ``default`` when the hint is ``auto`` / empty / unknown
      3. Any profile already registered (agent may have started Chrome)
      4. Create (launch-or-attach) for the resolved profile name

    Cached entries are health-checked before reuse — a dead/stale session
    (e.g. browser crashed) is evicted and replaced with a freshly launched
    one rather than being handed back to fail again.
    """
    try:
        from harness_browser import BrowserSession
        from harness_browser.tool_interface import _registry
    except ImportError as exc:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            "harness-browser not installed",
            status=503,
        ) from exc

    hint = (profile_hint or "").strip()
    candidates: list[str] = []
    if hint and hint not in {"auto"}:
        candidates.append(hint)
    if "default" not in candidates:
        candidates.append("default")
    candidates.extend(k for k in _registry if k not in candidates)

    for name in candidates:
        cached = _registry.get(name)
        if cached is None:
            continue
        if await _is_session_alive(cached):
            return cached
        logger.warning(
            "harness session %r is dead (stale CDP connection); discarding and relaunching",
            name,
        )
        _registry.pop(name, None)
        with contextlib.suppress(Exception):
            await cached.close()

    profile = candidates[0] if candidates else "default"
    harness_settings = None
    if server is not None and agent_id:
        from octop.infra.utils.browser_media import (  # noqa: PLC0415
            agent_outbound_screenshots_dir,
            harness_settings_for_screenshots_dir,
        )

        shots = agent_outbound_screenshots_dir(server.paths, agent_id)
        harness_settings = harness_settings_for_screenshots_dir(shots)

    from octop.infra.browser.setup import (  # noqa: PLC0415
        prepare_harness_profile_for_launch,
        resolve_browser_display,
    )

    await prepare_harness_profile_for_launch(profile)
    # Virtual desktop (Xvnc :99) → headed Chrome so the window shows on
    # remote desktop; otherwise keep auto (headless on servers without X).
    display = resolve_browser_display()
    launch_mode = "headed" if display else "auto"

    # Fresh ProfileManager picks up any BROWSER_USE_PROFILES_DIR relocation
    # done by prepare (default singleton is bound at import time).
    from harness_browser.profile import ProfileManager  # noqa: PLC0415
    from harness_browser.settings import settings as hb_settings  # noqa: PLC0415

    profile_manager = ProfileManager(base_dir=Path(hb_settings.profiles_dir))

    try:
        sess = await BrowserSession.create(
            profile=profile,
            mode=launch_mode,  # type: ignore[arg-type]
            settings=harness_settings,
            profile_manager=profile_manager,
        )
    except Exception as exc:
        # Chrome exit 21 / ProcessSingleton usually means a stale lock or a
        # non-writable profile left by a previous root/non-root mismatch.
        msg = str(exc)
        if (
            "returncode=21" in msg
            or "ProcessSingleton" in msg
            or "SingletonLock" in msg
            or "profile directory" in msg.lower()
            or "/run/user/" in msg
        ):
            logger.warning(
                "Browser launch failed for %r (%s); recovering profile and retrying",
                profile,
                exc,
            )
            await prepare_harness_profile_for_launch(profile, force_recover=True)
            display = resolve_browser_display()
            launch_mode = "headed" if display else "auto"
            profile_manager = ProfileManager(base_dir=Path(hb_settings.profiles_dir))
            try:
                sess = await BrowserSession.create(
                    profile=profile,
                    mode=launch_mode,  # type: ignore[arg-type]
                    settings=harness_settings,
                    profile_manager=profile_manager,
                )
            except Exception as retry_exc:
                raise OctopError(
                    ErrorCode.INTERNAL_ERROR,
                    f"failed to attach browser profile {profile!r}: {retry_exc}",
                    status=503,
                ) from retry_exc
        else:
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"failed to attach browser profile {profile!r}: {exc}",
                status=503,
            ) from exc
    _registry[profile] = sess
    return sess


async def harness_page_url(sess: Any) -> str:
    try:
        info = await sess._internal.client.send(  # noqa: SLF001
            "Runtime.evaluate",
            {
                "expression": "location.href",
                "returnByValue": True,
            },
        )
        return str(info.get("result", {}).get("value", "") or "")
    except Exception:
        return ""


async def harness_list_tabs(sess: Any) -> list[dict[str, Any]]:
    """List open page targets in a harness session (CDP /json)."""
    import aiohttp

    host = sess._internal._cfg.cdp_host  # noqa: SLF001
    port = sess._internal._profile.cdp_port  # noqa: SLF001
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with (
            aiohttp.ClientSession() as http,
            http.get(f"http://{host}:{port}/json", timeout=timeout) as resp,
        ):
            targets = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("harness_list_tabs failed: %s", exc)
        return []

    pages = [t for t in targets if t.get("type") == "page"]
    current_target_id = None
    try:
        current_target_id = sess._internal._profile.load_target()  # noqa: SLF001
    except Exception:
        current_target_id = None
    tabs: list[dict[str, Any]] = []
    for i, t in enumerate(pages):
        url = str(t.get("url", "") or "")
        tabs.append(
            {
                "id": t.get("id", i),
                "idx": i,
                "url": url,
                "title": str(t.get("title", "") or ""),
                "active": bool(current_target_id and t.get("id") == current_target_id),
            }
        )
    if tabs and not any(t["active"] for t in tabs):
        tabs[0]["active"] = True
    return tabs


async def harness_sessions_payload(conversation_id: str | None = None) -> dict[str, Any]:
    """Shape expected by the dashboard ``BrowserSessionsResponse`` type."""
    try:
        from harness_browser.tool_interface import _registry
    except ImportError:
        return {"ok": False, "environment": "headless-server", "sessions": []}

    now = int(time.time() * 1000)
    sessions: list[dict[str, Any]] = []
    for profile, sess in list(_registry.items()):
        if conversation_id and profile not in {conversation_id, "default"}:
            continue
        url = await harness_page_url(sess)
        sessions.append(
            {
                "session_id": profile,
                "profile_name": profile,
                "conversation_id": profile,
                "channel_source": "dashboard",
                "state": "streaming" if url else "idle",
                "control_owner": "agent",
                "current_url": url,
                "created_at": now,
                "last_activity_at": now,
            }
        )
    return {
        "ok": True,
        "environment": "headless-server",
        "sessions": sessions,
    }


@router.get("/browser/harness-sessions")
async def list_harness_sessions(
    conversation_id: str | None = Query(default=None),
    _: Any = Depends(current_user),
) -> dict[str, Any]:
    """List live harness-browser profiles (agent ``browser_use`` sessions)."""
    return await harness_sessions_payload(conversation_id)
