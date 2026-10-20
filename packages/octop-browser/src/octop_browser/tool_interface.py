"""Stateless browser_tool() entry point for AI frameworks."""

from __future__ import annotations

import logging
from typing import Any

from octop_browser.cdp.client import CDPSessionError
from octop_browser.mode import BrowserMode
from octop_browser.models import ActionMetrics, ToolResult
from octop_browser.profile import ProfileManager
from octop_browser.session import BrowserSession
from octop_browser.settings import settings

logger = logging.getLogger(__name__)

_registry: dict[str, BrowserSession] = {}
_global_hooks: dict[str, list[Any]] = {}

_KNOWN_ACTIONS = frozenset(
    [
        "navigate",
        "dom_tree",
        "screenshot",
        "click",
        "type",
        "fill",
        "press",
        "wait",
        "select",
        "scroll",
        "hover",
        "eval_js",
        "go_back",
        "go_forward",
        "reload",
        "new_tab",
        "switch_tab",
        "close_tab",
        "list_tabs",
        "close_session",
    ]
)


def _error_result(action: str, message: str) -> ToolResult:
    return ToolResult(
        success=False,
        content="",
        error=message,
        metrics=ActionMetrics(
            action=action, duration_ms=0, dom_nodes_scanned=0, estimated_tokens=0
        ),
    )


async def _get_or_create_session(
    profile: str,
    headless: bool | None = None,
    mode: BrowserMode | None = None,
    urls: list[str] | None = None,
) -> BrowserSession:
    if profile not in _registry:
        sess = await BrowserSession.create(
            profile=profile, headless=headless, mode=mode, urls=urls
        )
        _registry[profile] = sess
    return _registry[profile]


async def _drop_session(profile: str) -> None:
    sess = _registry.pop(profile, None)
    if sess is None:
        return
    try:
        await sess.close()
    except Exception:  # pylint: disable=broad-except
        logger.debug(
            "Failed to close stale browser session for %s", profile, exc_info=True
        )


def _is_disconnected_error(exc: Exception) -> bool:
    if isinstance(exc, CDPSessionError):
        return (
            "not connected" in str(exc).lower() or "connection lost" in str(exc).lower()
        )
    return False


async def browser_tool(
    action: str,
    profile: str = "default",
    headless: bool | None = None,
    mode: BrowserMode | None = None,
    urls: list[str] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """
    Stateless entry point for AI frameworks.

    Routes to the correct :class:`BrowserSession` by ``profile`` name.
    Creates a new session lazily if none exists for the profile.

    Args:
        action: One of the supported action strings.
        profile: Profile name (maps to a Chrome user-data-dir).
        headless: Legacy boolean override (only honored on first call per
            profile). Prefer ``mode``.
        mode: ``"auto"`` | ``"headed"`` | ``"headless"``. Defaults to the
            ``BROWSER_USE_MODE`` environment variable, then ``"auto"``.
            Only honored on first call per profile.
        urls: Optional list of URLs to open as separate tabs on first call
            per profile. Each URL gets its own browser tab.
        **kwargs: Action-specific parameters.

    Returns:
        A :class:`ToolResult`.
    """
    if action not in _KNOWN_ACTIONS:
        return _error_result(
            action, f"Unknown action '{action}'. Valid: {sorted(_KNOWN_ACTIONS)}"
        )

    if action == "close_session":
        kill = bool(kwargs.pop("kill", False))
        if kwargs:
            return _error_result(
                action,
                f"Invalid parameters for 'close_session': {sorted(kwargs)}",
            )
        sess = _registry.pop(profile, None)
        if sess is not None:
            try:
                await sess.close(kill=kill)
            except Exception:  # pylint: disable=broad-except
                logger.debug(
                    "Failed to close browser session for %s", profile, exc_info=True
                )
        elif kill and not settings.cdp_ws_url:
            from octop_browser.cdp.launcher import (  # noqa: PLC0415
                terminate_browser,
            )

            managed_profile = ProfileManager(
                base_dir=settings.profiles_dir
            ).get_or_create(profile)
            await terminate_browser(
                managed_profile,
                cdp_host=settings.cdp_host,
            )
        return ToolResult(
            success=True,
            content=f"Session '{profile}' closed.",
            metrics=ActionMetrics(
                action="close_session",
                duration_ms=0,
                dom_nodes_scanned=0,
                estimated_tokens=0,
            ),
        )

    try:
        sess = await _get_or_create_session(
            profile, headless=headless, mode=mode, urls=urls
        )
    except Exception as exc:  # pylint: disable=broad-except
        return _error_result(action, f"Failed to create session: {exc}")

    # If urls were provided but the session already existed (so urls were
    # not applied during creation), open each URL as a new tab now.
    if urls and profile in _registry:
        for i, url in enumerate(urls):
            if i == 0:
                await sess.navigate(url)
            else:
                await sess.new_tab(url=url, force_new=True)

    try:
        method = getattr(sess, action)
        result: ToolResult = await method(**kwargs)
        return result
    except TypeError as exc:
        return _error_result(action, f"Invalid parameters for '{action}': {exc}")
    except Exception as exc:  # pylint: disable=broad-except
        if _is_disconnected_error(exc):
            logger.info(
                "browser_tool reconnecting stale session for action=%s profile=%s",
                action,
                profile,
            )
            await _drop_session(profile)
            try:
                fresh = await _get_or_create_session(
                    profile, headless=headless, mode=mode, urls=urls
                )
                method = getattr(fresh, action)
                retry_result: ToolResult = await method(**kwargs)
                return retry_result
            except TypeError as retry_exc:
                return _error_result(
                    action, f"Invalid parameters for '{action}': {retry_exc}"
                )
            except Exception as retry_exc:  # pylint: disable=broad-except
                logger.exception(
                    "browser_tool retry failed for action=%s profile=%s",
                    action,
                    profile,
                )
                return _error_result(action, str(retry_exc))
        logger.exception("browser_tool error for action=%s profile=%s", action, profile)
        return _error_result(action, str(exc))
