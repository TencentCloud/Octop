"""Remote browser router — Playwright-backed sessions (P1.5).

Surface (intentionally lean — finnie's full router has handoff /
multi-tab control / SSE install progress; we cap to what the dashboard
actually drives in the octop MVP):

  GET    /api/browser/env-status                  → { playwright, browsers_ok, error? }
  POST   /api/browser/install                     → run ``playwright install chromium``
                                                    inline (fire-and-forget; returns 202)
  GET    /api/browser/sessions                    → list active sessions
  POST   /api/browser/sessions                    → create + return id
  DELETE /api/browser/sessions/{id}               → close
  POST   /api/browser/sessions/{id}/goto          → navigate
  GET    /api/browser/sessions/{id}/screenshot    → PNG body

All endpoints require an authenticated user; cross-user isolation is
in-memory (sessions are keyed by ``(user_id, session_id)``). Playwright
is an optional dependency — endpoints return a structured 503 if the
``playwright`` import or ``chromium`` browser binary is missing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)

router = APIRouter()

_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
    "--restore-last-session",
]


# --- module-level state (process-wide) -------------------------------------


class _Session:
    """Browser session: one browser context, one or more pages (tabs)."""

    def __init__(
        self,
        playwright: Any,
        browser: Any,
        context: Any,
        owner_id: int,
    ) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.pages: list[Any] = []  # ordered list of open pages
        self.active_idx: int = 0  # index of currently active page
        self.owner_id = owner_id
        self._lock = asyncio.Lock()

    @property
    def page(self) -> Any:
        """Currently active page."""
        return self.pages[self.active_idx]

    @property
    def url(self) -> str:
        try:
            return str(self.page.url)
        except Exception:
            return "about:blank"

    def _track_page(self, page: Any) -> None:
        """Wire lifecycle hooks for a Playwright page."""

        def _on_close() -> None:
            asyncio.create_task(self._on_page_closed(page))

        with contextlib.suppress(Exception):
            page.on("close", _on_close)

    async def _on_page_closed(self, page: Any) -> None:
        async with self._lock:
            if page not in self.pages:
                return
            idx = self.pages.index(page)
            self.pages.pop(idx)
            if not self.pages:
                return
            if self.active_idx >= len(self.pages):
                self.active_idx = len(self.pages) - 1
            elif idx < self.active_idx:
                self.active_idx = max(0, self.active_idx - 1)

    async def _on_new_page(self, page: Any) -> None:
        """Track a page opened by the browser (popup / new tab)."""
        async with self._lock:
            if page.is_closed() or page in self.pages:
                return
            self._track_page(page)
            self.pages.append(page)

    def _wire_context(self) -> None:
        self.context.on("page", lambda page: asyncio.create_task(self._on_new_page(page)))

    async def sync_pages(self) -> None:
        """Reconcile tracked pages with the live browser context."""
        async with self._lock:
            live = [p for p in self.context.pages if not p.is_closed()]
            if not live:
                raise OctopError(ErrorCode.NOT_FOUND, "browser session ended — all tabs closed")
            seen: set[int] = set()
            merged: list[Any] = []
            for p in self.pages:
                if not p.is_closed() and p in live:
                    merged.append(p)
                    seen.add(id(p))
            for p in live:
                if id(p) not in seen:
                    self._track_page(p)
                    merged.append(p)
            self.pages = merged
            if self.active_idx >= len(self.pages):
                self.active_idx = len(self.pages) - 1
            elif self.pages[self.active_idx].is_closed():
                self.active_idx = 0

    async def tab_list(self) -> list[dict[str, Any]]:
        """Serializable list of tabs for the API response."""
        await self.sync_pages()
        tabs: list[dict[str, Any]] = []
        for i, p in enumerate(self.pages):
            title = ""
            url = "about:blank"
            with contextlib.suppress(Exception):
                url = str(p.url)
                title = await p.title()
            tabs.append(
                {
                    "idx": i,
                    "url": url,
                    "title": title,
                    "active": i == self.active_idx,
                }
            )
        return tabs

    async def ensure_page(self) -> Any:
        await self.sync_pages()
        page = self.page
        if page.is_closed():
            raise OctopError(ErrorCode.NOT_FOUND, "active tab was closed")
        return page

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.context.close()
        with contextlib.suppress(Exception):
            await self.playwright.stop()


_sessions: dict[str, _Session] = {}
_session_lock = asyncio.Lock()


def _user_profile_dir(home: Path, user_id: int) -> Path:
    d = home / "browser-profiles" / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_session(user_id: int, session_id: str) -> _Session:
    s = _sessions.get(session_id)
    if s is None or s.owner_id != user_id:
        raise OctopError(ErrorCode.NOT_FOUND, "session not found")
    return s


async def _session_response(sess: _Session) -> dict[str, Any]:
    tabs = await sess.tab_list()
    return {"id": sess.id, "url": sess.url, "tabs": tabs}


async def _mouse_click(
    sess: _Session,
    page: Any,
    x: float,
    y: float,
    *,
    button: str = "left",
    click_count: int = 1,
) -> None:
    """Click at (x, y); switch to a new tab only when one actually opens."""
    before = len(sess.pages)
    await page.mouse.move(x, y)
    await page.mouse.click(x, y, button=button, click_count=click_count)
    # Popup tabs arrive via context "page" event — brief yield before reconcile.
    await asyncio.sleep(0.05)
    await sess.sync_pages()
    if len(sess.pages) > before:
        sess.active_idx = len(sess.pages) - 1


# --- env probe -------------------------------------------------------------


def _probe_env() -> dict[str, Any]:
    """Cheap synchronous probe of browser environment availability.

    Requirements:
      1. Detect system Chrome/Chromium **or** Playwright-managed Chromium
         via the same ``find_chrome`` path used at launch time.
      2. ``browsers_ok`` means launch can use that binary (screenshot stream).
      3. Install (elsewhere) downloads Playwright Chromium only when missing.
      4. ``playwright_chromium`` flags whether *our* install exists (uninstall
         target); never implies deleting the user's system browser.

    ``verify_chromium`` is install-time only (see ``POST /browser/install``).
    """
    out: dict[str, Any] = {
        "playwright": False,
        "browsers_ok": False,
        "harness_browser": False,
        "playwright_chromium": False,
        "chrome_path": None,
        "chrome_source": None,  # "system" | "playwright" | None
        "error": None,
    }

    from octop.infra.browser.setup import (  # noqa: PLC0415
        chrome_source_for_path,
        playwright_chromium_installed,
    )

    out["playwright_chromium"] = playwright_chromium_installed()

    try:
        from harness_browser import BrowserSession  # noqa: F401, PLC0415
        from harness_browser.cdp.launcher import find_chrome  # noqa: PLC0415

        out["harness_browser"] = True
        chrome = find_chrome()
        if chrome:
            out["browsers_ok"] = True
            out["chrome_path"] = chrome
            out["chrome_source"] = chrome_source_for_path(chrome)
        else:
            out["error"] = (
                "Chrome/Chromium not found. Install Google Chrome, or run "
                "POST /api/browser/install to download Playwright Chromium."
            )
    except ImportError:
        pass

    try:
        import playwright  # noqa: F401, PLC0415

        out["playwright"] = True
    except ImportError as exc:
        if not out["harness_browser"]:
            out["error"] = (
                f"playwright not installed: {exc}. Install octop[browser] extras or harness-browser."
            )
        return out

    if not out["browsers_ok"] and not out.get("error"):
        out["error"] = (
            "Chrome/Chromium not found. Install Google Chrome, or run "
            "POST /api/browser/install to download Playwright Chromium."
        )
    return out


@router.get("/browser/env-status")
async def env_status(_: Any = Depends(current_user)) -> dict[str, Any]:
    return _probe_env()


# --- install ---------------------------------------------------------------


def _verify_browser_binary(exe: str) -> tuple[bool, str]:
    """Install-time check: binary exists and responds to ``--version``."""
    import subprocess  # noqa: PLC0415

    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Browser verification timed out: {exe}"
    except OSError as exc:
        return False, f"Browser verification failed: {exc}"

    if result.returncode == 0:
        version = (result.stdout or result.stderr or "").strip() or exe
        return True, version
    detail = (result.stderr or result.stdout or "").strip()
    return False, f"Browser exited with code {result.returncode}: {detail}"


@router.post("/browser/install")
async def install(_: Any = Depends(current_user)) -> StreamingResponse:
    """Stream Chromium install progress as SSE.

    Each event is a JSON line conforming to ``harness_browser.InstallEvent``:
      ``{"log": "..."}``                              — progress line
      ``{"done": true, "success": true}``             — finished OK
      ``{"done": true, "success": false, "error": "..."}``  — failed

    If a system Chrome/Chromium is already resolvable via ``find_chrome``,
    verify it with ``--version`` and short-circuit (no Playwright download).
    Otherwise delegate to ``install_chromium_stream`` (which runs its own
    ``verify_chromium`` after download).

    Returns ``text/event-stream``; the client reads until ``done`` appears.
    """

    async def _event_stream() -> AsyncGenerator[str, None]:
        try:
            from harness_browser.cdp.launcher import find_chrome  # noqa: PLC0415

            chrome = find_chrome()
            if chrome:
                yield ("data: " + json.dumps({"log": f"Found browser: {chrome}"}) + "\n\n")
                yield ("data: " + json.dumps({"log": "Verifying installation ..."}) + "\n\n")
                ok, msg = _verify_browser_binary(chrome)
                if ok:
                    yield "data: " + json.dumps({"log": msg}) + "\n\n"
                    yield ("data: " + json.dumps({"done": True, "success": True}) + "\n\n")
                    return
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "log": (
                                f"System browser not usable ({msg}); "
                                "falling back to Playwright Chromium download ..."
                            )
                        }
                    )
                    + "\n\n"
                )

            from harness_browser import install_chromium_stream  # noqa: PLC0415

            async for event in install_chromium_stream():
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # pragma: no cover
            yield f"data: {json.dumps({'done': True, 'success': False, 'error': str(exc)})}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- sessions --------------------------------------------------------------


class GotoBody(BaseModel):
    url: str
    wait_until: str = "load"  # load / domcontentloaded / networkidle


class ActionBody(BaseModel):
    """A single user interaction event to execute on the page."""

    type: str
    """Event type: click | dblclick | mousedown | mouseup | type | scroll |
    keydown | keyup | navigate | goback | goforward | reload"""

    x: float | None = None
    y: float | None = None
    button: str = "left"  # for mouse events: left | middle | right
    delta_x: float = 0.0  # for scroll
    delta_y: float = 0.0  # for scroll
    text: str | None = None  # for type / key events
    key: str | None = None  # for keydown / keyup
    url: str | None = None  # for navigate


@router.post("/browser/sessions/{session_id}/action")
async def action(
    session_id: str,
    body: ActionBody,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Execute a single interaction on the session page.

    Supported action types:
      click / dblclick / mousedown / mouseup — mouse at (x, y)
      type               — insert text (body.text)
      scroll             — scroll at (x, y) by (delta_x, delta_y)
      keydown / keyup    — key press (body.key)
      navigate           — navigate to body.url
      goback             — history.back()
      goforward          — history.forward()
      reload             — reload page

    Returns ``{id, url}`` with the updated session URL.
    """
    sess = _get_session(user.id, session_id)
    try:
        page = await sess.ensure_page()
    except OctopError:
        raise
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"session unavailable: {exc}") from exc
    t = body.type
    try:
        if t in ("click", "dblclick", "mousedown", "mouseup"):
            if body.x is None or body.y is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "x and y required for mouse action")
            if t == "click":
                await _mouse_click(sess, page, body.x, body.y, button=body.button)
            elif t == "dblclick":
                await _mouse_click(sess, page, body.x, body.y, button=body.button, click_count=2)
            else:
                await page.mouse.move(body.x, body.y)
                if t == "mousedown":
                    await page.mouse.down(button=body.button)
                else:
                    await page.mouse.up(button=body.button)
        elif t == "type":
            if body.text is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "text required for type")
            await page.keyboard.type(body.text)
        elif t == "scroll":
            if body.x is None or body.y is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "x and y required for scroll")
            await page.mouse.move(body.x, body.y)
            # Drag-scroll sends small per-frame deltas; amplify for visible movement.
            await page.mouse.wheel(body.delta_x * 2.5, body.delta_y * 2.5)
        elif t == "keydown":
            if body.key is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "key required for keydown")
            await page.keyboard.down(body.key)
        elif t == "keyup":
            if body.key is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "key required for keyup")
            await page.keyboard.up(body.key)
        elif t == "navigate":
            if body.url is None:
                raise OctopError(ErrorCode.SLASH_BAD_ARGS, "url required for navigate")
            await page.goto(body.url, wait_until="domcontentloaded", timeout=30_000)
        elif t == "goback":
            await page.go_back(wait_until="domcontentloaded", timeout=15_000)
        elif t == "goforward":
            await page.go_forward(wait_until="domcontentloaded", timeout=15_000)
        elif t == "reload":
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
        else:
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"unknown action type: {t!r}")
        if t in ("navigate", "goback", "goforward", "reload"):
            await sess.sync_pages()
    except OctopError:
        raise
    except Exception as exc:
        msg = str(exc)
        if "has been closed" in msg or "Target page" in msg:
            with contextlib.suppress(Exception):
                await sess.sync_pages()
            raise OctopError(ErrorCode.NOT_FOUND, f"tab closed: {msg}") from exc
        raise OctopError(ErrorCode.INTERNAL_ERROR, f"action failed: {exc}") from exc
    return await _session_response(sess)


@router.get("/browser/sessions/{session_id}")
async def get_session(
    session_id: str,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    sess = _get_session(user.id, session_id)
    try:
        return await _session_response(sess)
    except OctopError:
        raise
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"session unavailable: {exc}") from exc


@router.get("/browser/sessions")
async def list_sessions(user: Any = Depends(current_user)) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in _sessions.values():
        if s.owner_id != user.id:
            continue
        with contextlib.suppress(Exception):
            out.append(await _session_response(s))
    return out


class CreateSessionBody(BaseModel):
    width: int = 0
    height: int = 0


@router.post("/browser/sessions", status_code=201)
async def create_session(
    body: CreateSessionBody = CreateSessionBody(),
    user: Any = Depends(current_user),
    server: OctopServer = Depends(get_server),
) -> dict[str, Any]:
    env = _probe_env()
    if not env["playwright"] or not env["browsers_ok"]:
        # 503: the *dependency* is missing, not the request itself.
        reason = env["error"] or "browser environment not ready"
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            reason,
            status=503,
            details={"error": reason},
        )

    from playwright.async_api import async_playwright  # noqa: PLC0415

    async with _session_lock:
        # Reuse an existing live session for this user instead of spawning another.
        for sid, existing in list(_sessions.items()):
            if existing.owner_id != user.id:
                continue
            try:
                return await _session_response(existing)
            except OctopError:
                _sessions.pop(sid, None)
                with contextlib.suppress(Exception):
                    await existing.close()

        profile_dir = _user_profile_dir(server.paths.root, user.id)
        pw = await async_playwright().start()
        try:
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": list(_CHROMIUM_ARGS),
            }
            if body.width > 0 and body.height > 0:
                launch_kwargs["viewport"] = {"width": body.width, "height": body.height}
            context = await pw.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_kwargs,
            )
        except Exception as exc:
            await pw.stop()
            raise OctopError(
                ErrorCode.INTERNAL_ERROR,
                f"browser launch failed: {exc}",
                status=500,
            ) from exc
        sess = _Session(pw, context.browser, context, owner_id=user.id)
        sess._wire_context()
        await sess.sync_pages()
        if not sess.pages:
            page = await context.new_page()
            sess._track_page(page)
            sess.pages.append(page)
        _sessions[sess.id] = sess
    return await _session_response(sess)


@router.delete("/browser/sessions/{session_id}", status_code=204)
async def close_session(
    session_id: str,
    user: Any = Depends(current_user),
) -> None:
    sess = _get_session(user.id, session_id)
    async with _session_lock:
        _sessions.pop(sess.id, None)
    await sess.close()


class NewTabBody(BaseModel):
    url: str | None = None


@router.post("/browser/sessions/{session_id}/tabs", status_code=201)
async def new_tab(
    session_id: str,
    body: NewTabBody = NewTabBody(),
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Open a new tab and optionally navigate to ``body.url``."""
    sess = _get_session(user.id, session_id)
    page = await sess.context.new_page()
    warning: str | None = None
    if body.url:
        try:
            await page.goto(body.url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            # Tab restoration is best-effort. A stale local file URL or a page
            # that can no longer be reached should not make "Start session"
            # fail with a 500; keep the browser session alive and report the
            # failed tab as a warning to the caller.
            warning = f"failed to open tab {body.url!r}: {exc}"
            logger.warning("remote browser tab open failed: %s", warning)
            with contextlib.suppress(Exception):
                await page.close()
    # Page is tracked by context.on("page") — only reconcile and switch.
    await sess.sync_pages()
    if not page.is_closed():
        with contextlib.suppress(ValueError):
            sess.active_idx = sess.pages.index(page)
    resp = await _session_response(sess)
    if warning:
        resp["warning"] = warning
    return resp


@router.delete("/browser/sessions/{session_id}/tabs/{tab_idx}", status_code=200)
async def close_tab(
    session_id: str,
    tab_idx: int,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Close a tab by index. Cannot close the last tab."""
    sess = _get_session(user.id, session_id)
    await sess.sync_pages()
    if len(sess.pages) <= 1:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "cannot close the last tab")
    if tab_idx < 0 or tab_idx >= len(sess.pages):
        raise OctopError(ErrorCode.NOT_FOUND, "tab index out of range")
    page = sess.pages.pop(tab_idx)
    with contextlib.suppress(Exception):
        await page.close()
    # Adjust active_idx if needed
    if sess.active_idx >= len(sess.pages):
        sess.active_idx = len(sess.pages) - 1
    return await _session_response(sess)


@router.post("/browser/sessions/{session_id}/tabs/{tab_idx}/switch")
async def switch_tab(
    session_id: str,
    tab_idx: int,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Switch active tab by index."""
    sess = _get_session(user.id, session_id)
    await sess.sync_pages()
    if tab_idx < 0 or tab_idx >= len(sess.pages):
        raise OctopError(ErrorCode.NOT_FOUND, "tab index out of range")
    sess.active_idx = tab_idx
    return await _session_response(sess)


@router.post("/browser/sessions/{session_id}/goto")
async def goto(
    session_id: str,
    body: GotoBody,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    sess = _get_session(user.id, session_id)
    try:
        page = await sess.ensure_page()
        await page.goto(body.url, wait_until=body.wait_until, timeout=30_000)
    except OctopError:
        raise
    except Exception as exc:
        raise OctopError(ErrorCode.NOT_FOUND, f"navigation failed: {exc}") from exc
    resp = await _session_response(sess)
    with contextlib.suppress(Exception):
        resp["title"] = await sess.page.title()
    return resp


@router.get("/browser/sessions/{session_id}/screenshot")
async def screenshot(
    session_id: str,
    user: Any = Depends(current_user),
) -> Response:
    sess = _get_session(user.id, session_id)
    try:
        page = await sess.ensure_page()
        png = await page.screenshot(type="png", full_page=False)
    except OctopError:
        raise
    except Exception as exc:
        msg = str(exc)
        if "has been closed" in msg or "Target page" in msg:
            raise OctopError(ErrorCode.NOT_FOUND, f"tab closed: {msg}") from exc
        raise OctopError(ErrorCode.NOT_FOUND, f"screenshot failed: {exc}") from exc
    return Response(content=png, media_type="image/png")
