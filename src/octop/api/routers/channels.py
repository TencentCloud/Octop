"""Channels router."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform as _platform
import re
import subprocess
import sys
from pathlib import Path as _FsPath
from typing import Any, Literal, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from octop.api.common.agent import require_agent_row
from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.channels import qr_bind
from octop.infra.gateway.gateway import ChannelKind
from octop.infra.utils.locale import DEFAULT_LOCALE, resolve_request_locale
from octop.infra.utils.subprocess_io import parse_subprocess_json_lines

logger = logging.getLogger(__name__)

router = APIRouter()


class ChannelCreateBody(BaseModel):
    kind: ChannelKind
    name: str
    config: dict[str, Any] = {}


class ChannelPatchBody(BaseModel):
    kind: ChannelKind | None = None
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ChannelProbeBody(BaseModel):
    kind: ChannelKind
    config: dict[str, Any] = {}


class FeishuBotCreatorStartBody(BaseModel):
    platform: Literal["feishu", "lark"] = "feishu"
    avatar_url: str = ""
    greeting: str = ""


class YuanbaoBotCreatorStartBody(BaseModel):
    instance_id: str = ""
    ip: str = ""


def _parse_bot_creator_body(model: type[BaseModel], raw: dict[str, Any] | None) -> BaseModel:
    try:
        return model.model_validate(raw or {})
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid request body.") from exc


def _row_to_dict(
    r: Any, *, gateway: Any | None = None, locale: Any = DEFAULT_LOCALE
) -> dict[str, Any]:
    out = {
        "id": r.channel_id,
        "agent_id": r.agent_id,
        "kind": r.kind,
        "name": r.name,
        "enabled": bool(r.enabled),
    }
    if gateway is not None:
        runtime = gateway.runtime_status_to_dict(r.channel_id, locale=locale)
        if runtime is not None:
            out["runtime"] = runtime
    return out


def _row_to_detail(
    r: Any, *, gateway: Any | None = None, locale: Any = DEFAULT_LOCALE
) -> dict[str, Any]:
    detail = _row_to_dict(r, gateway=gateway, locale=locale)
    try:
        detail["config"] = json.loads(r.config_json or "{}")
    except json.JSONDecodeError:
        detail["config"] = {}
    return detail


def _require_agent_access(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Any:
    return require_agent_row(agent_id, user=user, as_user=as_user, server=server)


def _acting_user_id(user: Any, as_user: int | None) -> int:
    return int(as_user if as_user is not None else user.id)


@router.get("/agents/{agent_id}/channels")
async def list_channels(
    agent_id: str,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    gw = server.app_runtime.gateway
    rows = gw.list_channels(agent_id)
    locale = resolve_request_locale(request)
    return [_row_to_dict(r, gateway=gw, locale=locale) for r in rows]


@router.post("/agents/{agent_id}/channels", status_code=201)
async def create_channel(
    agent_id: str,
    body: ChannelCreateBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    from octop.infra.gateway.gateway import ChannelCreateSpec  # noqa: PLC0415
    from octop.infra.utils.ulid import new_ulid as _new_ulid  # noqa: PLC0415

    spec = ChannelCreateSpec(
        channel_id=_new_ulid(),
        agent_id=agent_id,
        user_id=_acting_user_id(user, as_user),
        kind=body.kind,
        name=body.name,
        config=body.config,
    )
    row = await server.app_runtime.gateway.create_channel(spec)
    return _row_to_dict(
        row, gateway=server.app_runtime.gateway, locale=resolve_request_locale(request)
    )


@router.get("/agents/{agent_id}/channels/{channel_id}")
async def get_channel(
    agent_id: str,
    channel_id: str,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    row = server.app_runtime.gateway.get_channel(channel_id)
    if row is None or row.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
    return _row_to_detail(
        row, gateway=server.app_runtime.gateway, locale=resolve_request_locale(request)
    )


@router.patch("/agents/{agent_id}/channels/{channel_id}")
async def patch_channel(
    agent_id: str,
    channel_id: str,
    body: ChannelPatchBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    existing = server.app_runtime.gateway.get_channel(channel_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
    row = await server.app_runtime.gateway.update_channel(
        channel_id,
        kind=str(body.kind) if body.kind is not None else None,
        name=body.name,
        config_json=json.dumps(body.config) if body.config is not None else None,
        enabled=int(body.enabled) if body.enabled is not None else None,
    )
    return _row_to_dict(
        row, gateway=server.app_runtime.gateway, locale=resolve_request_locale(request)
    )


@router.delete("/agents/{agent_id}/channels/{channel_id}", status_code=204)
async def delete_channel(
    agent_id: str,
    channel_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    existing = server.app_runtime.gateway.get_channel(channel_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
    await server.app_runtime.gateway.delete_channel(channel_id)


@router.post("/agents/{agent_id}/channels/{channel_id}/test")
async def test_channel(
    agent_id: str,
    channel_id: str,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe a channel via Gateway.probe_channel()."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    existing = server.app_runtime.gateway.get_channel(channel_id)
    if existing is None or existing.agent_id != agent_id:
        raise OctopError(ErrorCode.NOT_FOUND, "channel not found")
    return cast(
        dict[str, Any],
        await server.app_runtime.gateway.probe_channel(
            channel_id, locale=resolve_request_locale(request)
        ),
    )


@router.post("/agents/{agent_id}/channels/probe")
async def probe_channel_config(
    agent_id: str,
    body: ChannelProbeBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Probe channel credentials from a draft config (no save required)."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    return cast(
        dict[str, Any],
        await server.app_runtime.gateway.probe_config(
            agent_id=agent_id,
            kind=str(body.kind),
            config=body.config,
            locale=resolve_request_locale(request),
        ),
    )


# ─── QR scan helpers ────────────────────────────────────────────────────────

_SAFE_ARG_RE = re.compile(r"^[a-zA-Z0-9_.:/\\\-]+$")
_MAX_ARG_LEN = 2048
_ALLOWED_PLATFORM_VALUES = frozenset({"feishu", "lark"})
_INSTANCE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_.\-]{1,512}$")
_FEISHU_PROFILE_NAMES = {
    "feishu": "octop-feishu-bot",
    "lark": "octop-lark-bot",
}


def _sanitize_subprocess_arg(value: str, field_name: str) -> str:
    """Validate subprocess arg to prevent command injection (CWE-78).

    Rejects values that start with ``-`` to block option-injection (argument
    injection, CWE-88) in addition to the character-whitelist check.
    """
    if not value or len(value) > _MAX_ARG_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be 1-{_MAX_ARG_LEN} characters.",
        )
    if value.startswith("-"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: value must not start with '-'.",
        )
    if not _SAFE_ARG_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: contains disallowed characters.",
        )
    return value


def _sanitize_token(value: str, field_name: str) -> str:
    """Validate opaque tokens passed to downstream services."""
    if not value or len(value) > _MAX_ARG_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: must be 1-{_MAX_ARG_LEN} characters.",
        )
    if not _TOKEN_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: contains disallowed characters.",
        )
    return value


def _sanitize_instance_id(value: str) -> str:
    if not _INSTANCE_ID_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail="Invalid instance_id: use letters, digits, underscore, or hyphen only.",
        )
    return value


def _sanitize_ip_address(value: str) -> str:
    import ipaddress

    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid ip: must be a valid IP address."
        ) from exc
    return value


def _resolve_profiles_root() -> _FsPath:
    """Resolve browser profile root; ignore unsafe env overrides."""
    default = _FsPath.home() / ".harness-browser" / "profiles"
    raw = os.environ.get("HARNESS_BROWSER_PROFILES_DIR")
    if not raw:
        return default
    if len(raw) > _MAX_ARG_LEN or not _SAFE_ARG_RE.match(raw):
        logger.warning("Ignoring unsafe HARNESS_BROWSER_PROFILES_DIR=%r", raw)
        return default
    return _FsPath(raw).expanduser()


def _safe_profile_directory(platform: str) -> _FsPath:
    """Return a profile directory guaranteed to live under profiles_root."""
    if platform not in _ALLOWED_PLATFORM_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: must be one of {sorted(_ALLOWED_PLATFORM_VALUES)}.",
        )
    root = _resolve_profiles_root().resolve()
    profile = (root / _FEISHU_PROFILE_NAMES[platform]).resolve()
    try:
        profile.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid browser profile path.") from exc
    return profile


def _bot_creator_script(name: str) -> str:
    """Resolve bundled bot-creator script path (not user-controlled)."""
    script = (
        _FsPath(__file__).resolve().parent.parent.parent
        / "infra"
        / "gateway"
        / "bot_creators"
        / name
    ).resolve()
    expected_parent = (
        _FsPath(__file__).resolve().parent.parent.parent / "infra" / "gateway" / "bot_creators"
    ).resolve()
    if not str(script).startswith(str(expected_parent)):
        raise HTTPException(status_code=500, detail="Invalid bot creator script path.")
    if not script.is_file():
        raise HTTPException(status_code=404, detail=f"{name} not found.")
    return str(script)


async def _pkill_chrome_profile(profile_dir: _FsPath) -> None:
    """Best-effort kill of stale Chromium processes for a validated profile dir."""
    dir_str = _sanitize_subprocess_arg(str(profile_dir), "profile_dir")
    pattern = f"user-data-dir={dir_str}"
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["pkill", "-9", "-f", pattern],
            check=False,
            capture_output=True,
            timeout=5,
            shell=False,
        )
        if result.returncode == 0:
            await asyncio.sleep(0.5)
    except Exception:
        pass  # best-effort cleanup


def _get_plat_code() -> int:
    system = _platform.system().lower()
    if system == "darwin":
        return 1
    if system == "windows":
        return 2
    if system == "linux":
        return 3
    return 0


# ─── WeCom QR code ──────────────────────────────────────────────────────────


@router.post("/agents/{agent_id}/channels/wecom/qrcode/generate")
async def wecom_qrcode_generate(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Generate WeCom AI Bot QR code for registration."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    try:
        return await qr_bind.wecom_qr_generate()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch WeCom QR code")
        raise HTTPException(status_code=502, detail=f"Failed to fetch QR code: {exc}") from exc


@router.post("/agents/{agent_id}/channels/wecom/qrcode/poll")
async def wecom_qrcode_poll(
    agent_id: str,
    as_user: int | None = None,
    scode: str = Body(..., embed=True),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Poll WeCom QR scan result."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    scode = _sanitize_token(scode, "scode")
    try:
        return await qr_bind.wecom_qr_poll(scode)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to poll WeCom QR result")
        raise HTTPException(status_code=502, detail=f"Failed to poll QR result: {exc}") from exc


# ─── WeChat (Weixin) QR code ─────────────────────────────────────────────────


def _get_weixin_qr_login() -> Any:
    """Import WeixinQRLogin lazily from harness-gateway weixin channel."""
    try:
        from harness_gateway.channels.weixin.login_qr import WeixinQRLogin

        return WeixinQRLogin
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="WeChat QR login requires harness-gateway with weixin channel support.",
        ) from None


@router.post("/agents/{agent_id}/channels/weixin/qrcode/generate")
async def weixin_qrcode_generate(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Generate WeChat iLink Bot QR code."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    cls = _get_weixin_qr_login()
    try:
        login = cls()
        result = await login.fetch_qr_code()
        return {
            "qrcode_token": result.qrcode,
            "qrcode_url": result.qrcode_img_content,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch WeChat QR code")
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch WeChat QR code: {exc}"
        ) from exc


@router.post("/agents/{agent_id}/channels/weixin/qrcode/poll")
async def weixin_qrcode_poll(
    agent_id: str,
    as_user: int | None = None,
    qrcode_token: str = Body(..., embed=True),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Poll WeChat QR scan result (single long-poll, ~40s)."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    qrcode_token = _sanitize_token(qrcode_token, "qrcode_token")
    cls = _get_weixin_qr_login()
    try:
        login = cls()
        result = await asyncio.wait_for(
            login.wait_for_login(qrcode_token),
            timeout=40.0,
        )
    except TimeoutError:
        return {"status": "wait"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to poll WeChat QR result")
        raise HTTPException(
            status_code=502, detail=f"Failed to poll WeChat QR result: {exc}"
        ) from exc

    if not result.connected:
        return {"status": "error", "message": result.message}

    return {
        "status": "success",
        "account_id": result.account_id,
        "token": result.bot_token,
        "base_url": result.base_url,
    }


# ─── Feishu Bot Creator ──────────────────────────────────────────────────────

# Per-agent-id creator state: agent_id -> {proc, lines, lock}
_feishu_creator_states: dict[str, dict[str, Any]] = {}


def _get_feishu_state(agent_id: str) -> dict[str, Any]:
    if agent_id not in _feishu_creator_states:
        _feishu_creator_states[agent_id] = {
            "proc": None,
            "lines": [],
            "lock": asyncio.Lock(),
        }
    return _feishu_creator_states[agent_id]


@router.post("/agents/{agent_id}/channels/feishu/bot-creator/start")
async def feishu_bot_creator_start(
    agent_id: str,
    as_user: int | None = None,
    body: dict[str, Any] = Body(default=None),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Start the Feishu bot creator subprocess."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_feishu_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is not None and proc.poll() is None:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)
        state["proc"] = None
        state["lines"] = []

    parsed = _parse_bot_creator_body(FeishuBotCreatorStartBody, body)
    assert isinstance(parsed, FeishuBotCreatorStartBody)
    target_platform = parsed.platform
    avatar_url = parsed.avatar_url
    greeting = parsed.greeting

    if avatar_url:
        _sanitize_subprocess_arg(avatar_url, "avatar_url")
    if greeting:
        _sanitize_subprocess_arg(greeting, "greeting")

    profile_dir = _safe_profile_directory(target_platform)
    await _pkill_chrome_profile(profile_dir)

    # Remove stale Chrome singleton lock files
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = profile_dir / lock_name
        try:
            await asyncio.to_thread(lock_path.unlink)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Failed to remove stale %s: %s", lock_name, exc)

    script_path = _bot_creator_script("feishu_bot_creator.py")

    cmd = [sys.executable, script_path, "create", "--platform", target_platform]
    if avatar_url:
        cmd.extend(["--avatar-url", avatar_url])
    if greeting:
        cmd.extend(["--greeting", greeting])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            shell=False,
        )
        async with state["lock"]:
            state["proc"] = proc
        logger.info("Feishu bot creator started for agent %s, pid=%s", agent_id, proc.pid)
        return {"status": "started", "pid": proc.pid}
    except Exception as exc:
        logger.exception("Failed to start feishu bot creator for agent %s", agent_id)
        raise HTTPException(status_code=500, detail=f"Failed to start creator: {exc}") from exc


@router.post("/agents/{agent_id}/channels/feishu/bot-creator/poll")
async def feishu_bot_creator_poll(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Poll feishu bot creator subprocess for new output."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_feishu_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is None:
            return {"status": "not_started", "events": []}

        new_lines = await asyncio.to_thread(parse_subprocess_json_lines, proc)
        state["lines"].extend(new_lines)

        return_code = proc.poll()
        finished = return_code is not None

        if finished and proc.stdout:
            remaining_bytes = proc.stdout.read()
            if remaining_bytes:
                remaining = remaining_bytes.decode("utf-8", errors="replace")
                for line in remaining.strip().split("\n"):
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            new_lines.append(data)
                            state["lines"].append(data)
                        except json.JSONDecodeError:
                            new_lines.append(
                                {"action": "log", "level": "info", "step": "raw", "message": line}
                            )

        status = "running"
        if finished:
            status = "finished" if return_code == 0 else "failed"

        qr_token = None
        app_id = None
        app_secret = None
        for ev in state["lines"]:
            if ev.get("action") == "show_qrcode":
                content = ev.get("content", "")
                try:
                    qr_data = json.loads(content) if isinstance(content, str) else content
                    qr_token = qr_data.get("qrlogin", {}).get("token")
                except (json.JSONDecodeError, AttributeError):
                    pass
            if ev.get("action") == "finish" and ev.get("level") == "success":
                data = ev.get("data", {})
                app_id = data.get("app_id")
                app_secret = data.get("app_secret")

        return {
            "status": status,
            "events": new_lines,
            "qr_token": qr_token,
            "app_id": app_id,
            "app_secret": app_secret,
            "return_code": return_code,
        }


@router.post("/agents/{agent_id}/channels/feishu/bot-creator/stop")
async def feishu_bot_creator_stop(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Stop the feishu bot creator subprocess."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_feishu_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is None:
            return {"status": "not_running"}
        if proc.poll() is None:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)
        state["proc"] = None
        state["lines"] = []
    return {"status": "stopped"}


# ─── YuanBao Bot Creator ─────────────────────────────────────────────────────

_yuanbao_creator_states: dict[str, dict[str, Any]] = {}


def _get_yuanbao_state(agent_id: str) -> dict[str, Any]:
    if agent_id not in _yuanbao_creator_states:
        _yuanbao_creator_states[agent_id] = {
            "proc": None,
            "lines": [],
            "lock": asyncio.Lock(),
        }
    return _yuanbao_creator_states[agent_id]


@router.post("/agents/{agent_id}/channels/yuanbao/bot-creator/start")
async def yuanbao_bot_creator_start(
    agent_id: str,
    as_user: int | None = None,
    body: dict[str, Any] = Body(default=None),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Start the YuanBao bot creator subprocess."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_yuanbao_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is not None and proc.poll() is None:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)
        state["proc"] = None
        state["lines"] = []

    parsed = _parse_bot_creator_body(YuanbaoBotCreatorStartBody, body)
    assert isinstance(parsed, YuanbaoBotCreatorStartBody)
    instance_id = parsed.instance_id
    ip_addr = parsed.ip

    if instance_id:
        _sanitize_instance_id(instance_id)
    if ip_addr:
        _sanitize_ip_address(ip_addr)

    script_path = _bot_creator_script("yuanbao_bot_creator.py")

    cmd = [sys.executable, script_path, "create"]
    if instance_id:
        cmd.append(instance_id)
        if ip_addr:
            cmd.append(ip_addr)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            shell=False,
        )
        async with state["lock"]:
            state["proc"] = proc
        logger.info("YuanBao bot creator started for agent %s, pid=%s", agent_id, proc.pid)
        return {"status": "started", "pid": proc.pid}
    except Exception as exc:
        logger.exception("Failed to start yuanbao bot creator for agent %s", agent_id)
        raise HTTPException(status_code=500, detail=f"Failed to start creator: {exc}") from exc


@router.post("/agents/{agent_id}/channels/yuanbao/bot-creator/poll")
async def yuanbao_bot_creator_poll(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Poll YuanBao bot creator subprocess for new output."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_yuanbao_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is None:
            return {"status": "not_started", "events": []}

        new_lines = await asyncio.to_thread(parse_subprocess_json_lines, proc)
        state["lines"].extend(new_lines)

        return_code = proc.poll()
        finished = return_code is not None

        if finished and proc.stdout:
            remaining = proc.stdout.read()
            if remaining:
                for line in remaining.strip().split("\n"):
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            new_lines.append(data)
                            state["lines"].append(data)
                        except json.JSONDecodeError:
                            new_lines.append(
                                {"action": "log", "level": "info", "step": "raw", "message": line}
                            )

        status = "running"
        if finished:
            status = "finished" if return_code == 0 else "failed"

        scan_code = None
        scan_url = None
        app_key = None
        app_secret = None
        for ev in state["lines"]:
            if ev.get("action") == "scan_code":
                scan_code = ev.get("scan_code")
                scan_url = ev.get("scan_url")
            if ev.get("action") == "finish" and ev.get("level") == "success":
                data = ev.get("data", {})
                app_key = data.get("app_key")
                app_secret = data.get("app_secret")

        return {
            "status": status,
            "events": new_lines,
            "scan_code": scan_code,
            "scan_url": scan_url,
            "app_key": app_key,
            "app_secret": app_secret,
            "return_code": return_code,
        }


@router.post("/agents/{agent_id}/channels/yuanbao/bot-creator/stop")
async def yuanbao_bot_creator_stop(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Stop the YuanBao bot creator subprocess."""
    _require_agent_access(agent_id, user=user, as_user=as_user, server=server)
    state = _get_yuanbao_state(agent_id)

    async with state["lock"]:
        proc = state["proc"]
        if proc is None:
            return {"status": "not_running"}
        if proc.poll() is None:
            proc.kill()
            await asyncio.to_thread(proc.wait, 5)
        state["proc"] = None
        state["lines"] = []
    return {"status": "stopped"}
