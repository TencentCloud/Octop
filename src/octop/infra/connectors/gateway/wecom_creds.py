"""Materialize wecom-cli bot.enc + mcp_config.enc for headless Octop instances."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MCP_CONFIG_URL = "https://qyapi.weixin.qq.com/cgi-bin/aibot/cli/get_mcp_config"
_FINGERPRINT_NAME = ".octop_wecom_fingerprint"
_BIND_SOURCE_INTERACTIVE = 1
_USER_AGENT = f"WeComCLI/0.1.9 distribution/octop {platform.system().lower()}/{platform.machine()}"


def materialize_wecom_bot_config(config_dir: Path, *, bot_id: str, bot_secret: str) -> None:
    """Write ``.encryption_key`` + ``bot.enc`` + ``mcp_config.enc`` for wecom-cli.

    Format (from WecomTeam/wecom-cli): AES-256-GCM ciphertext as ``nonce || ct||tag``,
    key stored as base64 in ``.encryption_key``. MCP cache is required — bot.enc alone
    is not enough (``wecom-cli`` errors with “未找到 MCP 配置缓存”).
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(f"{bot_id}\0{bot_secret}".encode()).hexdigest()
    marker = config_dir / _FINGERPRINT_NAME
    mcp_path = config_dir / "mcp_config.enc"
    bot_path = config_dir / "bot.enc"
    if (
        marker.is_file()
        and bot_path.is_file()
        and mcp_path.is_file()
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        return

    key = _load_or_create_key(config_dir)
    bot = {
        "id": bot_id,
        "secret": bot_secret,
        "create_time": int(time.time()),
    }
    _encrypt_json_to(bot_path, bot, key)

    items = _fetch_mcp_config(bot_id=bot_id, bot_secret=bot_secret)
    _encrypt_json_to(mcp_path, items, key)
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    marker.chmod(0o600)


def _load_or_create_key(config_dir: Path) -> bytes:
    key_path = config_dir / ".encryption_key"
    if key_path.is_file():
        raw = key_path.read_text(encoding="utf-8").strip()
        try:
            key = base64.b64decode(raw)
        except Exception:
            key = b""
        if len(key) == 32:
            return key
    key = os.urandom(32)
    key_path.write_text(base64.b64encode(key).decode("ascii") + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    return key


def _encrypt_json_to(path: Path, payload: Any, key: bytes) -> None:
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    path.write_bytes(nonce + ciphertext)
    path.chmod(0o600)


def read_mcp_items_count(config_dir: Path) -> int:
    """Decrypt ``mcp_config.enc`` and count list entries (0 if unreadable)."""
    key_path = config_dir / ".encryption_key"
    mcp_path = config_dir / "mcp_config.enc"
    if not key_path.is_file() or not mcp_path.is_file():
        return 0
    try:
        key = base64.b64decode(key_path.read_text(encoding="utf-8").strip())
        raw = mcp_path.read_bytes()
        if len(key) != 32 or len(raw) < 13:
            return 0
        plain = AESGCM(key).decrypt(raw[:12], raw[12:], None)
        data = json.loads(plain.decode("utf-8"))
    except Exception:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        items = data.get("list")
        return len(items) if isinstance(items, list) else 0
    return 0


def _fetch_mcp_config(*, bot_id: str, bot_secret: str) -> list[dict[str, Any]]:
    """Signed ``get_mcp_config`` — algorithm from wecom-cli: sha256(secret+bot_id+time+nonce)."""
    now = int(time.time())
    nonce = f"mcp_{int(now * 1000)}_{uuid.uuid4().hex[:8]}"
    signature = hashlib.sha256(f"{bot_secret}{bot_id}{now}{nonce}".encode()).hexdigest()
    body = {
        "bot_id": bot_id,
        "time": now,
        "nonce": nonce,
        "signature": signature,
        "bind_source": _BIND_SOURCE_INTERACTIVE,
        "cli_version": _USER_AGENT,
    }
    req = Request(
        _MCP_CONFIG_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed WeCom HTTPS endpoint
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ValueError(f"企业微信 get_mcp_config HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ValueError(f"企业微信 get_mcp_config 网络错误: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"企业微信 get_mcp_config 返回非 JSON: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise ValueError("企业微信 get_mcp_config 返回格式无效")
    errcode = int(data.get("errcode") or 0)
    if errcode != 0:
        errmsg = str(data.get("errmsg") or f"errcode={errcode}").strip()
        raise ValueError(f"企业微信凭证校验失败: {errmsg}")
    items = data.get("list")
    if not isinstance(items, list) or not items:
        raise ValueError("企业微信返回空 MCP 配置列表，请确认机器人已开通 CLI 能力")
    return [item for item in items if isinstance(item, dict)]
