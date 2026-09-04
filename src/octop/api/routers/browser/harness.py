"""Helpers for attaching dashboard / chat UI to harness-browser sessions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from octop.api.deps import current_user
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.browser_media import user_browser_profile

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory control ownership per session (keyed by harness profile / session_id).
# This is a UI/coordination hint: the agent pauses interactive input while the
# user is in control. It is stored separately from the live session so a
# takeover survives dashboard reloads and WS reconnects.
_CONTROL_OWNERS: dict[str, str] = {}


def control_owner_for(session_id: str) -> str:
    """Return the current control owner for a session, defaulting to 'agent'."""
    return _CONTROL_OWNERS.get(session_id, "agent")


class HandoffBody(BaseModel):
    """Control handoff request: switch between agent and user control."""

    target: str  # "agent" | "user"
    reason: str = ""


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
        client = sess._internal.client  # noqa: SLF001
        send = getattr(client, "send_passive", client.send)
        await asyncio.wait_for(
            send("Runtime.evaluate", {"expression": "1", "returnByValue": True}),
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
    create: bool = True,
) -> Any | None:
    """Return a live :class:`harness_browser.BrowserSession` for ``profile_hint``.

    *profile_hint* must be a concrete profile name (``user-<id>``). Empty /
    ``auto`` never falls back to another user's session or to ``default``.

    When ``create=True`` (screencast / interactive clients) a missing live
    session is launched. Listen-only dashboard hooks pass ``create=False``
    so a status WebSocket cannot spawn Chrome just to watch for updates.

    Cached entries are health-checked before reuse — a dead/stale session
    (e.g. browser crashed) is evicted and replaced with a freshly launched
    one rather than being handed back to fail again.

    When ``create=False`` and no live session exists, returns ``None``.
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
    if not hint or hint == "auto":
        if not create:
            return None
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "browser profile is required")

    cached = _registry.get(hint)
    if cached is not None:
        if await _is_session_alive(cached):
            return cached
        logger.warning(
            "harness session %r is dead (stale CDP connection); discarding%s",
            hint,
            " and relaunching" if create else "",
        )
        _registry.pop(hint, None)
        with contextlib.suppress(Exception):
            await cached.close()

    if not create:
        return None

    profile = hint
    harness_settings = None
    if server is not None and agent_id:
        from octop.api.common.agent_workspace import (  # noqa: PLC0415
            resolve_agent_workspace_dir,
        )
        from octop.infra.utils.browser_media import (  # noqa: PLC0415
            agent_outbound_screenshots_dir,
            harness_settings_for_screenshots_dir,
        )

        shots = agent_outbound_screenshots_dir(resolve_agent_workspace_dir(server, agent_id))
        harness_settings = harness_settings_for_screenshots_dir(shots)

    from octop.infra.browser.setup import (  # noqa: PLC0415
        prepare_harness_profile_for_launch,
        resolve_browser_display,
    )

    # Shared ~/.octop/browser-profiles (not per-agent workspace).
    await prepare_harness_profile_for_launch(profile)
    # Virtual desktop (Xvnc :99) → headed Chrome so the window shows on
    # remote desktop; otherwise force headless (do not use mode=auto — a
    # stale $DISPLAY would still resolve to headed and crash Chromium).
    display = resolve_browser_display()
    launch_mode = "headed" if display else "headless"

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
            launch_mode = "headed" if display else "headless"
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
        client = sess._internal.client  # noqa: SLF001
        send = getattr(client, "send_passive", client.send)
        info = await send(
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


async def harness_sessions_payload(profile_name: str) -> dict[str, Any]:
    """Shape expected by the dashboard ``BrowserSessionsResponse`` type."""
    try:
        from harness_browser.tool_interface import _registry
    except ImportError:
        return {"ok": False, "environment": "headless-server", "sessions": []}

    now = int(time.time() * 1000)
    sessions: list[dict[str, Any]] = []
    for profile, sess in list(_registry.items()):
        if profile != profile_name:
            continue
        url = await harness_page_url(sess)
        sessions.append(
            {
                "session_id": profile,
                "profile_name": profile,
                "conversation_id": profile,
                "channel_source": "dashboard",
                "state": "streaming" if url else "idle",
                "control_owner": control_owner_for(profile),
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
async def list_harness_sessions(user: Any = Depends(current_user)) -> dict[str, Any]:
    """List the current user's live harness-browser profile."""
    return await harness_sessions_payload(user_browser_profile(user.id))


@router.post("/browser/sessions/{session_id}/handoff")
async def handoff(
    session_id: str,
    body: HandoffBody,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Switch control of a browser session between the agent and the user.

    The control owner is a coordination hint (the agent yields interactive
    input to the user while they are in control). It is stored in-memory per
    session and reflected in ``harness-sessions`` and the WS screencast so a
    takeover survives dashboard reloads and reconnects.
    """
    profile = user_browser_profile(user.id)
    if session_id not in {"", "auto"} and session_id != profile:
        logger.debug("handoff path %r ignored; using %r", session_id, profile)
    target = body.target
    if target not in ("agent", "user"):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "target must be 'agent' or 'user'")
    _CONTROL_OWNERS[profile] = target

    payload = await harness_sessions_payload(profile)
    session = next(
        (s for s in payload.get("sessions", []) if s["session_id"] == profile),
        None,
    )
    if session is None:
        # Session not currently live — return a minimal payload so the UI can
        # still flip its local control-owner state.
        now = int(time.time() * 1000)
        session = {
            "session_id": profile,
            "profile_name": profile,
            "conversation_id": profile,
            "channel_source": "dashboard",
            "state": "idle",
            "control_owner": target,
            "current_url": "",
            "created_at": now,
            "last_activity_at": now,
        }
    return {"ok": True, "session": session}


@router.post(
    "/browser/shutdown",
    summary="Stop the local Chrome process for a harness-browser profile",
)
async def shutdown_browser(user: Any = Depends(current_user)) -> dict[str, Any]:
    """Terminate the current user's Octop-managed Chrome. Cookies stay on disk."""
    try:
        from harness_browser.tool_interface import browser_tool
    except ImportError as exc:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            "harness-browser not installed",
            status=503,
        ) from exc

    hint = user_browser_profile(user.id)

    result = await browser_tool(action="close_session", profile=hint, kill=True)
    _CONTROL_OWNERS.pop(hint, None)
    if not result.success:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            result.error or f"failed to stop browser profile {hint!r}",
            status=503,
        )
    return {"ok": True, "profile": hint}
