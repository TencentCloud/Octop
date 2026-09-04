"""Browser environment probe and Chromium install (SSE).

Live sessions are harness-browser (see ``harness.py`` / ``stream.py``), not
in-process Playwright.

  GET    /api/browser/env-status  → { playwright, browsers_ok, harness_browser, … }
  POST   /api/browser/install     → SSE Playwright Chromium install (or reuse system Chrome)
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from octop.api.deps import current_user, require_permission

router = APIRouter()


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
async def install(_: Any = Depends(require_permission("browser"))) -> StreamingResponse:
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
