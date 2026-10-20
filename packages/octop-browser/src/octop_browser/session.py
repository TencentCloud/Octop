"""BrowserSession: the primary user-facing API."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from octop_browser.actions import capture, interact, js_eval
from octop_browser.actions import navigate as nav_actions
from octop_browser.cdp.client import CDPClient
from octop_browser.cdp.launcher import get_page_ws_url, launch_or_attach
from octop_browser.dom.builder import DOMBuilder, DOMLevel
from octop_browser.dom.refs import RefCache
from octop_browser.hooks import HooksMixin
from octop_browser.idle import BrowserIdleController, idle_controller_for
from octop_browser.mode import BrowserMode, normalize_mode, resolve_headless
from octop_browser.models import ActionMetrics, TabInfo, ToolResult
from octop_browser.profile import Profile, ProfileManager
from octop_browser.settings import OctopSettings
from octop_browser.settings import settings as _default_settings

logger = logging.getLogger(__name__)

_default_profile_manager = ProfileManager()
_REUSABLE_BLANK_URLS = {"about:blank", "chrome://newtab/", "chrome://newtab"}


class _InternalCDPSession:
    """Low-level CDP session: owns a CDPClient and RefCache for one page."""

    def __init__(self, profile: Profile, cfg: OctopSettings) -> None:
        self._profile = profile
        self._cfg = cfg
        self._idle_controller: BrowserIdleController | None = idle_controller_for(
            profile, cfg
        )
        self._client = CDPClient(
            timeout=cfg.cdp_timeout,
            activity_tracker=self._idle_controller,
        )
        self._ref_cache = RefCache()
        self._connected = False

    async def connect(self, headless: bool = False) -> None:
        """Launch/attach Chrome and connect CDP to the active page.

        If ``BROWSER_USE_CDP_WS_URL`` is set (or ``cfg.cdp_ws_url`` is provided),
        skip the launcher and connect directly to that WebSocket address.
        """
        if self._cfg.cdp_ws_url:
            ws_url = self._cfg.cdp_ws_url
            logger.debug("Direct CDP connect to %s", ws_url)
        else:
            await launch_or_attach(self._profile, headless=headless)
            ws_url = await get_page_ws_url(
                self._profile.cdp_port, profile=self._profile
            )
        await self._client.connect(ws_url)
        await self._client.enable_domain("Page")
        await self._client.enable_domain("DOM")
        await self._client.enable_domain("Runtime")
        # Note: the "Input" domain has no .enable method in CDP — input events
        # are dispatched directly via Input.dispatch* commands without enabling.
        await self._apply_viewport()
        self._connected = True
        if self._idle_controller is not None:
            self._idle_controller.start()

    async def _apply_viewport(self) -> None:
        """Pin the page viewport to the configured CSS-pixel dimensions.

        Without this, a freshly-launched Chromium uses an unpredictable
        default viewport (often ~800×600 in headless mode), so screenshots
        come back tiny. ``Emulation.setDeviceMetricsOverride`` fixes the
        viewport without resizing the window — the same approach finnie's
        screencast uses for its remote-browser stream.
        """
        width = max(int(self._cfg.viewport_width), 1)
        height = max(int(self._cfg.viewport_height), 1)
        try:
            await self._client.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
        except Exception:  # pragma: no cover  # pylint: disable=broad-except
            logger.debug("setDeviceMetricsOverride failed", exc_info=True)

    async def switch_to_target(self, target_id: str, *, activate: bool = True) -> None:
        """Reconnect this session to another page target.

        ``Target.activateTarget`` alone only focuses the Chrome tab; a CDP
        WebSocket remains bound to the old page. CLI calls and replay both
        expect subsequent actions after ``new_tab`` / ``switch_tab`` to address
        the selected tab, so we reconnect the page-level CDP client and persist
        the chosen target id on the profile.
        """
        if self._cfg.cdp_ws_url:
            raise RuntimeError(
                "Cannot switch tabs when connected via BROWSER_USE_CDP_WS_URL"
            )
        if activate:
            try:
                await self._client.send(
                    "Target.activateTarget", {"targetId": target_id}
                )
            except Exception:  # pragma: no cover  # pylint: disable=broad-except
                logger.debug("Target.activateTarget failed", exc_info=True)

        import aiohttp

        url = f"http://{self._cfg.cdp_host}:{self._profile.cdp_port}/json"
        async with aiohttp.ClientSession() as http:
            async with http.get(url) as resp:
                targets = await resp.json(content_type=None)
        match = next(
            (
                t
                for t in targets
                if t.get("type") == "page" and t.get("id") == target_id
            ),
            None,
        )
        if not match or not match.get("webSocketDebuggerUrl"):
            raise RuntimeError(f"No page target found for tab {target_id}")

        await self._client.close()
        self._client = CDPClient(
            timeout=self._cfg.cdp_timeout,
            activity_tracker=self._idle_controller,
        )
        self._ref_cache.invalidate()
        await self._client.connect(str(match["webSocketDebuggerUrl"]))
        await self._client.enable_domain("Page")
        await self._client.enable_domain("DOM")
        await self._client.enable_domain("Runtime")
        await self._apply_viewport()
        self._profile.save_target(target_id)

    async def close(self, *, kill: bool = False) -> None:
        await self._client.close()
        self._connected = False
        if kill:
            if self._idle_controller is not None:
                await self._idle_controller.reap_now()
            elif not self._cfg.cdp_ws_url:
                from octop_browser.cdp.launcher import (  # noqa: PLC0415
                    terminate_browser,
                )

                await terminate_browser(
                    self._profile,
                    cdp_host=self._cfg.cdp_host,
                )

    @property
    def client(self) -> CDPClient:
        return self._client

    @property
    def ref_cache(self) -> RefCache:
        return self._ref_cache


class BrowserSession(HooksMixin):
    """
    Profile-aware browser session with a clean Python API.

    Login state is persisted via Chrome's user-data-dir (per profile).
    All methods return :class:`~octop_browser.models.ToolResult`.

    Usage::

        async with await BrowserSession.create(profile="work") as sess:
            await sess.navigate("https://github.com")
            tree = await sess.dom_tree(level="interactive")
            await sess.click(ref="btn_1")
    """

    def __init__(self, internal: _InternalCDPSession, profile_name: str) -> None:
        super().__init__()
        self._internal = internal
        self._profile_name = profile_name
        self._action_count = 0
        self._total_duration_ms = 0
        self._total_tokens = 0
        self._errors = 0

    @classmethod
    async def create(
        cls,
        profile: str = "default",
        headless: bool | None = None,
        mode: BrowserMode | None = None,
        urls: list[str] | None = None,
        profile_manager: ProfileManager | None = None,
        settings: OctopSettings | None = None,
    ) -> "BrowserSession":
        """Create a new BrowserSession, launching or re-attaching Chrome.

        Args:
            profile: Profile name — maps to a Chrome user-data-dir for login
                persistence.
            headless: Legacy override. ``True``/``False`` forces a specific
                launch mode regardless of ``mode``/settings. Prefer ``mode``.
            mode: ``"auto"`` | ``"headed"`` | ``"headless"``. Overrides
                ``settings.browser_mode``. ``auto`` picks based on
                ``DISPLAY``/``WAYLAND_DISPLAY``.
            urls: Optional list of URLs to open as separate tabs on startup.
                If provided, each URL gets its own browser tab. The first
                URL becomes the active tab.
            profile_manager: Custom :class:`ProfileManager` (for testing or
                non-default base directories).
            settings: :class:`OctopSettings` instance. Defaults to the module-level
                singleton which reads from environment variables.
        """
        cfg = settings or _default_settings
        pm = profile_manager or _default_profile_manager
        p = pm.get_or_create(profile)
        # Resolve launch mode: explicit headless wins, else explicit mode,
        # else cfg.browser_mode.
        if headless is not None:
            is_headless = headless
        else:
            effective_mode = normalize_mode(mode) if mode else cfg.browser_mode
            is_headless = resolve_headless(effective_mode)
        internal = _InternalCDPSession(p, cfg)
        await internal.connect(headless=is_headless)
        session = cls(internal, profile)

        # Open additional tabs if urls were provided
        if urls:
            for i, url in enumerate(urls):
                if i == 0:
                    # Navigate the initial blank tab to the first URL
                    await session.navigate(url)
                else:
                    # Open new tab for subsequent URLs
                    await session.new_tab(url=url, force_new=True)

        return session

    async def __aenter__(self) -> "BrowserSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, url: str) -> ToolResult:
        await self._fire(
            "before_action", {"action": "navigate", "params": {"url": url}}
        )
        result = await nav_actions.navigate(
            self._internal.client, self._internal.ref_cache, url
        )
        await self._record(result)
        return result

    async def go_back(self) -> ToolResult:
        await self._fire("before_action", {"action": "go_back", "params": {}})
        result = await nav_actions.go_back(
            self._internal.client, self._internal.ref_cache
        )
        await self._record(result)
        return result

    async def go_forward(self) -> ToolResult:
        await self._fire("before_action", {"action": "go_forward", "params": {}})
        result = await nav_actions.go_forward(
            self._internal.client, self._internal.ref_cache
        )
        await self._record(result)
        return result

    async def reload(self) -> ToolResult:
        await self._fire("before_action", {"action": "reload", "params": {}})
        result = await nav_actions.reload(
            self._internal.client, self._internal.ref_cache
        )
        await self._record(result)
        return result

    # ------------------------------------------------------------------
    # Page state
    # ------------------------------------------------------------------

    async def dom_tree(self, level: DOMLevel = "interactive") -> ToolResult:
        start = time.monotonic()
        await self._fire(
            "before_action", {"action": "dom_tree", "params": {"level": level}}
        )
        try:
            doc = await self._internal.client.send("DOM.getDocument", {"depth": -1})
            root = doc["root"]
            info = await self._internal.client.send(
                "Runtime.evaluate",
                {
                    "expression": (
                        "JSON.stringify({url: location.href, title: document.title})"
                    ),
                    "returnByValue": True,
                },
            )
            page_info = json.loads(info.get("result", {}).get("value", "{}"))
            url = page_info.get("url", "")
            title = page_info.get("title", "")
            builder = DOMBuilder(
                dom=root,
                url=url,
                title=title,
                ref_cache=self._internal.ref_cache,
            )
            content = builder.build(level=level)
            tokens = len(content) // 4
            metrics = ActionMetrics(
                action="dom_tree",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=tokens,
            )
            result = ToolResult(success=True, content=content, metrics=metrics)
        except Exception as exc:  # pylint: disable=broad-except
            metrics = ActionMetrics(
                action="dom_tree",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=False, content="", error=str(exc), metrics=metrics
            )
        await self._record(result)
        return result

    async def screenshot(
        self,
        crop: bool = False,
        element_ref: str | None = None,
        full_page: bool = False,
        path: str | None = None,
    ) -> ToolResult:
        """Capture a screenshot. Returns a ToolResult whose content is the
        saved PNG file path (not raw base64) and ``metadata`` carries the
        page url/title/dimensions. See ``actions.capture.screenshot`` for
        path resolution and ``BROWSER_USE_SCREENSHOTS_DIR`` env.
        """
        await self._fire("before_action", {"action": "screenshot", "params": {}})
        result = await capture.screenshot(
            self._internal.client,
            self._internal.ref_cache,
            crop=crop,
            element_ref=element_ref,
            full_page=full_page,
            path=path,
            settings=self._internal._cfg,
        )
        await self._record(result)
        return result

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    async def click(
        self,
        ref: str | None = None,
        selector: str | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> ToolResult:
        await self._fire("before_action", {"action": "click", "params": {"ref": ref}})
        result = await interact.click(
            self._internal.client,
            self._internal.ref_cache,
            ref=ref,
            selector=selector,
            x=x,
            y=y,
        )
        await self._record(result)
        return result

    async def type(
        self,
        text: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> ToolResult:
        await self._fire(
            "before_action",
            {"action": "type", "params": {"ref": ref, "selector": selector}},
        )
        result = await interact.type_text(
            self._internal.client,
            self._internal.ref_cache,
            text=text,
            ref=ref,
            selector=selector,
        )
        await self._record(result)
        return result

    async def fill(
        self,
        text: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> ToolResult:
        await self._fire(
            "before_action",
            {"action": "fill", "params": {"ref": ref, "selector": selector}},
        )
        result = await interact.fill_text(
            self._internal.client,
            self._internal.ref_cache,
            text=text,
            ref=ref,
            selector=selector,
        )
        await self._record(result)
        return result

    async def press(self, key: str) -> ToolResult:
        await self._fire("before_action", {"action": "press", "params": {"key": key}})
        result = await interact.press_key(self._internal.client, key=key)
        await self._record(result)
        return result

    async def select(
        self,
        value: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> ToolResult:
        await self._fire(
            "before_action",
            {"action": "select", "params": {"ref": ref, "selector": selector}},
        )
        result = await interact.select_value(
            self._internal.client,
            self._internal.ref_cache,
            value=value,
            ref=ref,
            selector=selector,
        )
        await self._record(result)
        return result

    async def scroll(self, direction: str = "down", amount: int = 300) -> ToolResult:
        await self._fire("before_action", {"action": "scroll", "params": {}})
        result = await interact.scroll(
            self._internal.client,
            self._internal.ref_cache,
            direction=direction,
            amount=amount,
        )
        await self._record(result)
        return result

    async def hover(self, ref: str) -> ToolResult:
        await self._fire("before_action", {"action": "hover", "params": {"ref": ref}})
        result = await interact.hover(
            self._internal.client, self._internal.ref_cache, ref=ref
        )
        await self._record(result)
        return result

    # ------------------------------------------------------------------
    # JavaScript
    # ------------------------------------------------------------------

    async def eval_js(self, expression: str) -> ToolResult:
        await self._fire("before_action", {"action": "eval_js", "params": {}})
        result = await js_eval.eval_js(self._internal.client, expression)
        await self._record(result)
        return result

    async def wait(
        self,
        url_contains: str | None = None,
        text: str | None = None,
        selector: str | None = None,
        timeout_ms: int = 10000,
    ) -> ToolResult:
        start = time.monotonic()
        await self._fire("before_action", {"action": "wait", "params": {}})
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000
        error = "Timeout waiting for condition"
        while time.monotonic() <= deadline:
            try:
                expr = (
                    "JSON.stringify({url: location.href,"
                    " text: document.body ? document.body.innerText : '',"
                    " selector: null})"
                )
                if selector:
                    expr = (
                        "JSON.stringify({url: location.href, text: document.body ? document.body.innerText : '', "
                        + "selector: !!document.querySelector("
                        + json.dumps(selector)
                        + ")})"
                    )
                info = await self._internal.client.send(
                    "Runtime.evaluate", {"expression": expr, "returnByValue": True}
                )
                data = json.loads(info.get("result", {}).get("value", "{}"))
                ok = True
                if url_contains:
                    ok = ok and url_contains in str(data.get("url", ""))
                if text:
                    ok = ok and text in str(data.get("text", ""))
                if selector:
                    ok = ok and bool(data.get("selector"))
                if ok:
                    result = ToolResult(
                        success=True,
                        content="Wait condition satisfied",
                        metrics=ActionMetrics(
                            action="wait",
                            duration_ms=int((time.monotonic() - start) * 1000),
                            dom_nodes_scanned=0,
                            estimated_tokens=0,
                        ),
                    )
                    await self._record(result)
                    return result
            except Exception as exc:  # pylint: disable=broad-except
                error = str(exc)
            import asyncio

            await asyncio.sleep(0.25)
        result = ToolResult(
            success=False,
            content="",
            error=error,
            metrics=ActionMetrics(
                action="wait",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            ),
        )
        await self._record(result)
        return result

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    async def new_tab(
        self, url: str | None = None, force_new: bool = False
    ) -> ToolResult:
        start = time.monotonic()
        await self._fire(
            "before_action",
            {"action": "new_tab", "params": {"url": url, "force_new": force_new}},
        )
        try:
            target_id: str | None = None
            navigation_result: ToolResult | None = None
            current_url = (
                await self._current_page_url() if url and not force_new else None
            )
            blank_target_id: str | None = None
            if not force_new and url and current_url in _REUSABLE_BLANK_URLS:
                target_id = self._current_target_id()
                navigation_result = await self._navigate_existing_tab(url)
                content = target_id or f"Reused current tab for {url}"
            elif (
                not force_new
                and url
                and (blank_target_id := await self._find_blank_target_id())
            ):
                await self._internal.switch_to_target(blank_target_id)
                target_id = blank_target_id
                navigation_result = await self._navigate_existing_tab(url)
                content = blank_target_id
            else:
                previous_target_id = self._current_target_id()
                create_url = url or "about:blank"
                cdp_result = await self._internal.client.send(
                    "Target.createTarget", {"url": create_url}
                )
                target_id = str(cdp_result.get("targetId", ""))
                if target_id:
                    await self._switch_to_target_with_retry(target_id)
                if not url:
                    navigation_result = None
                elif create_url != url:
                    navigation_result = await self._navigate_existing_tab(url)
                content = target_id
            metrics = ActionMetrics(
                action="new_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            metadata: dict[str, object] | None = (
                {"target_id": target_id} if target_id else None
            )
            if navigation_result is not None and not navigation_result.success:
                if (
                    target_id
                    and "previous_target_id" in locals()
                    and target_id != previous_target_id
                ):
                    await self._close_failed_new_target(
                        target_id,
                        previous_target_id,
                    )
                result = ToolResult(
                    success=False,
                    content="",
                    error=navigation_result.error,
                    metrics=metrics,
                    metadata=metadata,
                )
            else:
                result = ToolResult(
                    success=True,
                    content=content,
                    metrics=metrics,
                    metadata=metadata,
                )
        except Exception as exc:  # pylint: disable=broad-except
            metrics = ActionMetrics(
                action="new_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=False, content="", error=str(exc), metrics=metrics
            )
        await self._record(result)
        return result

    async def _navigate_existing_tab(self, url: str) -> ToolResult:
        return await nav_actions.navigate(
            self._internal.client,
            self._internal.ref_cache,
            url,
        )

    async def _close_failed_new_target(
        self, target_id: str, previous_target_id: str | None
    ) -> None:
        """Best-effort cleanup for a just-created tab whose navigation failed."""
        try:
            if previous_target_id:
                await self._internal.switch_to_target(previous_target_id)
            await self._internal.client.send(
                "Target.closeTarget", {"targetId": target_id}
            )
        except Exception:  # pragma: no cover  # pylint: disable=broad-except
            logger.debug(
                "Failed to close target %s after navigation error",
                target_id,
                exc_info=True,
            )

    async def _current_page_url(self) -> str | None:
        try:
            info = await self._internal.client.send(
                "Runtime.evaluate",
                {"expression": "location.href", "returnByValue": True},
            )
        except Exception:  # pragma: no cover  # pylint: disable=broad-except
            return None
        value = info.get("result", {}).get("value")
        return value if isinstance(value, str) else None

    def _current_target_id(self) -> str | None:
        load_target = getattr(self._internal._profile, "load_target", None)
        if load_target is None:
            return None
        target_id = load_target()
        return target_id if isinstance(target_id, str) and target_id else None

    async def _switch_to_target_with_retry(
        self,
        target_id: str,
        *,
        attempts: int = 3,
        delay: float = 0.1,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                await self._internal.switch_to_target(target_id)
                return
            except Exception as exc:  # pylint: disable=broad-except
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(delay)
        if last_exc is not None:
            raise last_exc

    async def _find_blank_target_id(self) -> str | None:
        if self._internal._cfg.cdp_ws_url:
            return None

        host = self._internal._cfg.cdp_host
        port = self._internal._profile.cdp_port
        current_target_id = self._current_target_id()
        async with aiohttp.ClientSession() as http:
            async with http.get(f"http://{host}:{port}/json") as resp:
                targets = await resp.json(content_type=None)
        if not isinstance(targets, list):
            return None
        for target in targets:
            if not isinstance(target, dict) or target.get("type") != "page":
                continue
            target_id = target.get("id")
            if not isinstance(target_id, str) or target_id == current_target_id:
                continue
            if target.get("url") in _REUSABLE_BLANK_URLS:
                return target_id
        return None

    async def switch_tab(self, tab_id: str) -> ToolResult:
        start = time.monotonic()
        await self._fire(
            "before_action", {"action": "switch_tab", "params": {"tab_id": tab_id}}
        )
        try:
            await self._internal.switch_to_target(tab_id)
            metrics = ActionMetrics(
                action="switch_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=True,
                content=f"Activated tab {tab_id}",
                metrics=metrics,
            )
        except Exception as exc:  # pylint: disable=broad-except
            metrics = ActionMetrics(
                action="switch_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=False, content="", error=str(exc), metrics=metrics
            )
        await self._record(result)
        return result

    async def close_tab(self, tab_id: str | None = None) -> ToolResult:
        start = time.monotonic()
        await self._fire(
            "before_action", {"action": "close_tab", "params": {"tab_id": tab_id}}
        )
        try:
            if tab_id:
                await self._internal.client.send(
                    "Target.closeTarget", {"targetId": tab_id}
                )
                msg = f"Closed tab {tab_id}"
            else:
                msg = "No tab_id supplied; nothing to close."
            metrics = ActionMetrics(
                action="close_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(success=True, content=msg, metrics=metrics)
        except Exception as exc:  # pylint: disable=broad-except
            metrics = ActionMetrics(
                action="close_tab",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=False, content="", error=str(exc), metrics=metrics
            )
        await self._record(result)
        return result

    async def list_tabs(self) -> ToolResult:
        import aiohttp

        start = time.monotonic()
        await self._fire("before_action", {"action": "list_tabs", "params": {}})
        try:
            host = self._internal._cfg.cdp_host
            port = self._internal._profile.cdp_port
            async with aiohttp.ClientSession() as http:
                async with http.get(f"http://{host}:{port}/json") as resp:
                    targets = await resp.json(content_type=None)
            current_target_id = self._current_target_id()
            page_targets = [
                t for t in targets if isinstance(t, dict) and t.get("type") == "page"
            ]
            active_id = current_target_id
            if active_id and not any(t.get("id") == active_id for t in page_targets):
                active_id = None
            if active_id is None and page_targets:
                first_id = page_targets[0].get("id")
                active_id = first_id if isinstance(first_id, str) else None
            tabs = [
                TabInfo(
                    tab_id=t["id"],
                    url=t.get("url", ""),
                    title=t.get("title", ""),
                    active=t.get("id") == active_id,
                )
                for t in page_targets
                if isinstance(t.get("id"), str)
            ]
            content = (
                "\n".join(
                    f"[{t.tab_id}] {t.title or '(no title)'} — {t.url}" for t in tabs
                )
                or "(no open tabs)"
            )
            metrics = ActionMetrics(
                action="list_tabs",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=len(content) // 4,
            )
            result = ToolResult(
                success=True,
                content=content,
                metrics=metrics,
                metadata={
                    "tabs": [
                        {
                            "tab_id": tab.tab_id,
                            "url": tab.url,
                            "title": tab.title,
                            "active": tab.active,
                        }
                        for tab in tabs
                    ]
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            metrics = ActionMetrics(
                action="list_tabs",
                duration_ms=int((time.monotonic() - start) * 1000),
                dom_nodes_scanned=0,
                estimated_tokens=0,
            )
            result = ToolResult(
                success=False, content="", error=str(exc), metrics=metrics
            )
        await self._record(result)
        return result

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def metrics_summary(self) -> dict[str, Any]:
        return {
            "total_actions": self._action_count,
            "total_duration_ms": self._total_duration_ms,
            "total_estimated_tokens": self._total_tokens,
            "errors": self._errors,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self, *, kill: bool = False) -> None:
        """Close CDP and optionally terminate the local Chrome profile."""
        await self._internal.close(kill=kill)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _record(self, result: ToolResult) -> None:
        self._action_count += 1
        self._total_duration_ms += result.metrics.duration_ms
        self._total_tokens += result.metrics.estimated_tokens
        if not result.success:
            self._errors += 1
            await self._fire("action_error", result)
        else:
            await self._fire("after_action", result.metrics)
