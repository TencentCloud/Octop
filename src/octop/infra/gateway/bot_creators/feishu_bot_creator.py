#!/usr/bin/env python3
# Copyright (C) 2025 Tencent. All rights reserved.
#
# This software is independently developed by Tencent Lighthouse Team.
# Unauthorized copying, modification, distribution, or commercial use
# of this software, in whole or in part, is strictly prohibited.
# Violators will be held liable under applicable laws.
#
# Author: Tencent Lighthouse Team
"""Feishu / Lark Open Platform — scan-to-create app via lark-oapi.

Uses ``lark_oapi.register_app`` (OAuth 2.0 Device Authorization Grant,
RFC 8628). Requires ``lark-oapi>=1.5.5``.

Usage:
    python -m octop.infra.gateway.bot_creators.feishu_bot_creator init
    python -m octop.infra.gateway.bot_creators.feishu_bot_creator create [--platform feishu|lark]
    python -m octop.infra.gateway.bot_creators.feishu_bot_creator cleanup
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
import ssl
import sys
import time
import urllib.request
import uuid
from typing import Any

import lark_oapi as lark
from lark_oapi.scene.registration.errors import (
    AppAccessDeniedError,
    AppExpiredError,
    RegisterAppError,
)

_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(_reconfigure):
    _reconfigure(write_through=True)

PLATFORM = "feishu"

_PLATFORM_CONFIGS = {
    "feishu": {
        "open_base": "https://open.feishu.cn",
        "accounts_domain": "https://accounts.feishu.cn",
        "lark_domain": "https://accounts.larksuite.com",
        "default_greeting": "Hi，我是你刚刚使用 Octop 创建的飞书机器人，你现在可以跟我聊天了！",
        "app_desc": "由 Octop 一键创建的飞书机器人",
        "state_file_prefix": "octop-feishu-bot",
    },
    "lark": {
        "open_base": "https://open.larksuite.com",
        "accounts_domain": "https://accounts.larksuite.com",
        "lark_domain": "https://accounts.larksuite.com",
        "default_greeting": "Hi, I'm the bot you just created with Octop. You can chat with me now!",
        "app_desc": "Lark bot created by Octop",
        "state_file_prefix": "octop-lark-bot",
    },
}

STATE_DIR = "/tmp"
MIN_LARK_OAPI = (1, 5, 5)


def _pcfg(key: str) -> Any:
    return _PLATFORM_CONFIGS[PLATFORM][key]


def _state_file() -> str:
    return os.path.join(STATE_DIR, f"{_pcfg('state_file_prefix')}-creator-state.json")


def _save_state(data: dict[str, Any]) -> None:
    with open(_state_file(), "w") as f:
        json.dump(data, f, ensure_ascii=False)


def _emit(action: str, level: str, step: str, message: str, **extra: Any) -> None:
    record = {
        "action": action,
        "level": level,
        "step": step,
        "message": message,
        "ts": int(time.time()),
    }
    record.update(extra)
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _log_info(step: str, message: str, **extra: Any) -> None:
    _emit("log", "info", step, message, **extra)


def _log_success(step: str, message: str, **extra: Any) -> None:
    _emit("log", "success", step, message, **extra)


def _log_warn(step: str, message: str, **extra: Any) -> None:
    _emit("log", "warn", step, message, **extra)


def _log_error(step: str, message: str, **extra: Any) -> None:
    _emit("log", "error", step, message, **extra)


def _emit_finish(message: str, data: dict[str, Any]) -> None:
    _emit("finish", "success", "finish", message, data=data)


def _emit_error(step: str, message: str) -> None:
    _emit("finish", "error", step, message)


def _parse_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def _lark_oapi_version() -> str:
    return importlib.metadata.version("lark-oapi")


def _open_base_for_brand(tenant_brand: str | None) -> str:
    if tenant_brand == "lark":
        return str(_PLATFORM_CONFIGS["lark"]["open_base"])
    if tenant_brand == "feishu":
        return str(_PLATFORM_CONFIGS["feishu"]["open_base"])
    return str(_pcfg("open_base"))


def _send_greeting(
    app_id: str, app_secret: str, open_id: str, *, open_base: str, greeting: str
) -> None:
    _log_info("greeting", "Sending initial greeting message")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    token_payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    token_req = urllib.request.Request(
        f"{open_base}/open-apis/auth/v3/tenant_access_token/internal",
        data=token_payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(token_req, context=ctx) as resp:
            token_data = json.loads(resp.read())
        token = token_data.get("tenant_access_token")
        if not token:
            return
    except Exception:
        return

    send_payload = json.dumps(
        {
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": greeting}),
            "uuid": str(uuid.uuid4()),
        }
    ).encode()
    send_req = urllib.request.Request(
        f"{open_base}/open-apis/im/v1/messages?receive_id_type=open_id",
        data=send_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(send_req, context=ctx) as resp:
            resp.read()
    except Exception:
        pass


def _on_qr_code(info: dict[str, Any]) -> None:
    url = str(info.get("url") or "")
    expire_in = int(info.get("expire_in") or 0)
    if not url:
        return
    _save_state(
        {
            "phase": "create",
            "qr_url": url,
            "expire_in": expire_in,
            "deadline": int(time.time()) + expire_in,
        }
    )
    _emit(
        "show_qrcode",
        "info",
        "login",
        "Please scan to create the Feishu app",
        content=json.dumps({"url": url, "expire_in": expire_in}, ensure_ascii=False),
    )
    _log_info("login", f"QR URL ready (expires in {expire_in}s)")


def _on_status_change(info: dict[str, Any]) -> None:
    status = str(info.get("status") or "")
    interval = info.get("interval")
    if status == "slow_down":
        _log_info("login", f"Polling slowed down (interval={interval}s)")
    elif status == "domain_switched":
        _log_info("login", "Switched to Lark accounts domain")
    elif status == "polling":
        _log_info("login", "Waiting for scan confirmation...")


def register_feishu_app(*, avatar_url: str = "", greeting: str = "") -> dict[str, Any]:
    """Run ``lark.register_app`` and return finish data (app_id / app_secret / …)."""
    avatar = avatar_url.strip()
    greeting_text = greeting.strip() or str(_pcfg("default_greeting"))
    app_preset: dict[str, Any] = {"desc": str(_pcfg("app_desc"))}
    if avatar:
        app_preset["avatar"] = avatar
    result = lark.register_app(
        on_qr_code=_on_qr_code,
        on_status_change=_on_status_change,
        source="octop",
        domain=str(_pcfg("accounts_domain")),
        lark_domain=str(_pcfg("lark_domain")),
        app_preset=app_preset,
        create_only=True,
    )
    if not isinstance(result, dict):
        raise RegisterAppError(
            "missing_credentials", "register_app returned empty client_id/client_secret"
        )
    app_id = str(result.get("client_id") or "")
    app_secret = str(result.get("client_secret") or "")
    if not app_id or not app_secret:
        raise RegisterAppError(
            "missing_credentials", "register_app returned empty client_id/client_secret"
        )

    raw_user_info = result.get("user_info")
    user_info = raw_user_info if isinstance(raw_user_info, dict) else {}
    open_id = str(user_info.get("open_id") or "")
    tenant_brand = str(user_info.get("tenant_brand") or PLATFORM)
    open_base = _open_base_for_brand(tenant_brand)
    bot_name = str(result.get("app_name") or result.get("name") or "")
    manage_url = f"{open_base}/app/{app_id}"

    if open_id:
        _send_greeting(app_id, app_secret, open_id, open_base=open_base, greeting=greeting_text)
    else:
        _log_warn("owner", "open_id not obtained, skipping greeting")

    finish = {
        "app_id": app_id,
        "app_secret": app_secret,
        "bot_name": bot_name,
        "open_id": open_id or None,
        "manage_url": manage_url,
        "tenant_brand": tenant_brand,
    }
    _save_state({"phase": "done", **finish})
    return finish


def cmd_init() -> None:
    _log_info("init", "Checking lark-oapi...")
    try:
        version = _lark_oapi_version()
    except importlib.metadata.PackageNotFoundError:
        _emit_error("init", "lark-oapi not installed. Run `pip install 'lark-oapi>=1.5.5'`.")
        sys.exit(1)
    if _parse_version(version) < MIN_LARK_OAPI:
        _emit_error("init", f"lark-oapi {version} is too old; need >= 1.5.5")
        sys.exit(1)
    _log_success("init", f"lark-oapi {version} ready")
    sys.exit(0)


def cmd_create(avatar_url: str = "", greeting: str = "") -> None:
    platform_label = "Lark" if PLATFORM == "lark" else "飞书"
    _log_info("login", f"Starting {platform_label} scan-to-create flow...")
    try:
        finish = register_feishu_app(avatar_url=avatar_url, greeting=greeting)
    except AppAccessDeniedError as exc:
        _emit_error("login", f"User denied authorization: {exc.description}")
        sys.exit(1)
    except AppExpiredError as exc:
        _emit_error("login", f"QR code expired: {exc.description}")
        sys.exit(1)
    except RegisterAppError as exc:
        _emit_error("create_app", f"Failed to create app: {exc.code}: {exc.description}")
        sys.exit(1)
    except Exception as exc:
        _emit_error("create_app", f"Failed to create app: {exc}")
        sys.exit(1)

    bot_name = str(finish.get("bot_name") or "")
    manage_url = str(finish.get("manage_url") or "")
    _log_success("create_app", "App created", app_id=finish["app_id"])
    created = f"Bot「{bot_name}」created" if bot_name else "Bot created"
    _emit_finish(
        f"✅ {created}. Manage URL: {manage_url}",
        finish,
    )


def cmd_cleanup() -> None:
    sf = _state_file()
    if os.path.isfile(sf):
        with contextlib.suppress(OSError):
            os.remove(sf)
    _log_success("cleanup", "Cleaned up")


def main() -> None:
    global PLATFORM

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "init":
        cmd_init()
        return

    avatar_url = ""
    greeting = ""
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--avatar-url" and i + 1 < len(args):
            avatar_url = args[i + 1]
            i += 2
        elif args[i] == "--greeting" and i + 1 < len(args):
            greeting = args[i + 1]
            i += 2
        elif args[i] == "--platform" and i + 1 < len(args):
            p = args[i + 1].lower()
            if p not in ("feishu", "lark"):
                _emit_error("main", f"Unsupported platform: {p}, use feishu or lark")
                sys.exit(1)
            PLATFORM = p
            i += 2
        else:
            i += 1

    if cmd == "create":
        cmd_create(avatar_url=avatar_url, greeting=greeting)
    elif cmd == "cleanup":
        cmd_cleanup()
    else:
        _emit_error("main", f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
