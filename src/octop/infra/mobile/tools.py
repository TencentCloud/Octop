"""Built-in LangChain tools for Remote Android (adb automation)."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.config import get_config
from pydantic import Field

from octop.config import OctopConfig
from octop.i18n import tr
from octop.infra.mobile.adb import find_adb, list_devices, screencap_png, shell, swipe, tap
from octop.infra.mobile.setup import mobile_status
from octop.infra.users.permissions import user_has_permission
from octop.infra.utils.paths import PathLayout

MOBILE_SCREENSHOT = "mobile_screenshot"
MOBILE_TAP = "mobile_tap"
MOBILE_SWIPE = "mobile_swipe"
MOBILE_LAUNCH_APP = "mobile_launch_app"
MOBILE_UI_DUMP = "mobile_ui_dump"
MOBILE_HANDOFF = "mobile_handoff_to_user"

_UI_DUMP_PATH = "/sdcard/octop_ui_dump.xml"
_MAX_UI_DUMP_CHARS = 48_000


def _tool_ctx() -> dict[str, Any]:
    return get_config().get("configurable") or {}


def _require_mobile_access(config: OctopConfig, ctx: dict[str, Any], user_repo: Any) -> None:
    if not config.capabilities.mobile.enabled:
        raise ValueError("Remote Phone is not enabled on this host")
    user_raw = ctx.get("user")
    if user_raw is None:
        raise ValueError("missing configurable.user")
    if ctx.get("user_is_admin"):
        return
    row = user_repo.get(int(user_raw))
    if row is None or not user_has_permission(row, "mobile"):
        raise ValueError("mobile permission required")


def _require_ready(config: OctopConfig, *, locale: str) -> None:
    status = mobile_status(config, locale=locale)
    if status.setup_state != "ready" or not status.ok:
        reason = status.reason or status.setup_state
        raise ValueError(f"mobile not ready: {reason}")


async def _resolve_device(device: str | None) -> str:
    from octop.infra.mobile.agent_control import get_mobile_agent_control

    control = get_mobile_agent_control()
    if not control.enabled or not control.device:
        raise ValueError(
            "No Remote Phone session is active — open Remote Phone and Connect a device first."
        )
    picked = (device or "").strip()
    devices = await asyncio.to_thread(list_devices)
    if control.device not in devices:
        raise ValueError(f"bound adb device is no longer connected: {control.device}")
    if picked and picked != control.device:
        raise ValueError(f"agent is bound to {control.device}; cannot use {picked} until rebound")
    if picked and picked not in devices:
        raise ValueError(f"adb device not found: {picked}")
    return control.device


def build_mobile_tools(
    config: OctopConfig, *, user_repo: Any, paths: PathLayout | None = None
) -> list[StructuredTool]:
    """Return adb mobile tools when ``capabilities.mobile.enabled``."""
    if not config.capabilities.mobile.enabled:
        return []
    layout = paths or PathLayout.from_env()

    async def mobile_screenshot(
        device: Annotated[
            str | None,
            Field(description="adb device serial (defaults to the first connected device)."),
        ] = None,
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            _require_ready(config, locale=locale)
            serial = await _resolve_device(device)
            png = await asyncio.to_thread(screencap_png, serial)
            if not png:
                return json.dumps({"error": "screenshot failed"}, ensure_ascii=False)
            agent_id = str(ctx.get("agent_id") or "").strip()
            if not agent_id:
                b64 = base64.b64encode(png).decode("ascii")
                return json.dumps(
                    {"device": serial, "image_base64": b64, "format": "png"},
                    ensure_ascii=False,
                )
            out_dir = layout.agent_workspace(agent_id) / "mobile-screenshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            rel = f"mobile-screenshots/mobile_{stamp}.png"
            path = layout.agent_workspace(agent_id) / rel
            path.write_bytes(png)
            return json.dumps({"device": serial, "path": rel, "format": "png"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def mobile_tap(
        x: Annotated[int, Field(description="Horizontal tap coordinate in device pixels.")],
        y: Annotated[int, Field(description="Vertical tap coordinate in device pixels.")],
        device: Annotated[str | None, Field(description="adb device serial (optional).")] = None,
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            _require_ready(config, locale=locale)
            serial = await _resolve_device(device)
            ok = await asyncio.to_thread(tap, serial, x, y)
            return json.dumps({"device": serial, "ok": ok}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def mobile_swipe(
        x1: Annotated[int, Field(description="Swipe start X.")],
        y1: Annotated[int, Field(description="Swipe start Y.")],
        x2: Annotated[int, Field(description="Swipe end X.")],
        y2: Annotated[int, Field(description="Swipe end Y.")],
        duration_ms: Annotated[
            int, Field(description="Swipe duration in ms.", ge=50, le=5000)
        ] = 300,
        device: Annotated[str | None, Field(description="adb device serial (optional).")] = None,
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            _require_ready(config, locale=locale)
            serial = await _resolve_device(device)
            ok = await asyncio.to_thread(swipe, serial, x1, y1, x2, y2, duration_ms)
            return json.dumps({"device": serial, "ok": ok}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def mobile_launch_app(
        package: Annotated[
            str, Field(description="Android app package name, e.g. com.android.settings.")
        ],
        device: Annotated[str | None, Field(description="adb device serial (optional).")] = None,
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            _require_ready(config, locale=locale)
            serial = await _resolve_device(device)
            pkg = package.strip()
            if not pkg or "/" in pkg or " " in pkg:
                raise ValueError("invalid package name")
            code, out = await asyncio.to_thread(
                shell,
                serial,
                f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1",
            )
            return json.dumps(
                {"device": serial, "exit_code": code, "output": out}, ensure_ascii=False
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def mobile_ui_dump(
        device: Annotated[str | None, Field(description="adb device serial (optional).")] = None,
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            _require_ready(config, locale=locale)
            serial = await _resolve_device(device)
            dump_cmd = f"sh -c 'uiautomator dump {_UI_DUMP_PATH} && cat {_UI_DUMP_PATH}'"
            code, out = await asyncio.to_thread(shell, serial, dump_cmd)
            if code != 0 or not out:
                return json.dumps(
                    {"error": "ui dump failed", "exit_code": code}, ensure_ascii=False
                )
            if len(out) > _MAX_UI_DUMP_CHARS:
                out = out[:_MAX_UI_DUMP_CHARS] + "\n<!-- truncated -->"
            return json.dumps({"device": serial, "xml": out}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def mobile_handoff_to_user(
        reason: Annotated[
            str,
            Field(description="Why the user must take over (login, captcha, payment, etc.)."),
        ],
    ) -> str:
        try:
            ctx = _tool_ctx()
            locale = str(ctx.get("locale") or "en")
            _require_mobile_access(config, ctx, user_repo)
            msg = tr(
                "mobile.handoff_message",
                locale,
                reason=reason.strip() or tr("mobile.handoff_default", locale),
            )
            return json.dumps({"handoff": True, "message": msg}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    if not find_adb():
        return []

    return [
        StructuredTool.from_function(
            coroutine=mobile_screenshot,
            name=MOBILE_SCREENSHOT,
            description="Capture the connected Android device screen (PNG saved under the agent workspace when possible).",
        ),
        StructuredTool.from_function(
            coroutine=mobile_tap,
            name=MOBILE_TAP,
            description="Tap a coordinate on the connected Android device screen.",
        ),
        StructuredTool.from_function(
            coroutine=mobile_swipe,
            name=MOBILE_SWIPE,
            description="Swipe on the connected Android device screen.",
        ),
        StructuredTool.from_function(
            coroutine=mobile_launch_app,
            name=MOBILE_LAUNCH_APP,
            description="Launch an Android app by package name via adb.",
        ),
        StructuredTool.from_function(
            coroutine=mobile_ui_dump,
            name=MOBILE_UI_DUMP,
            description="Dump the Android UI hierarchy (uiautomator XML) for element discovery.",
        ),
        StructuredTool.from_function(
            coroutine=mobile_handoff_to_user,
            name=MOBILE_HANDOFF,
            description="Ask the human user to complete login, captcha, or other manual steps on the device.",
        ),
    ]
