"""Materialize wecom-cli bot.enc + mcp_config.enc for headless Octop instances."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import tempfile
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from octop.infra.connectors.gateway.cli_fingerprint import credential_fingerprint

_MCP_CONFIG_URL = "https://qyapi.weixin.qq.com/cgi-bin/aibot/cli/get_mcp_config"
_FINGERPRINT_NAME = ".octop_wecom_fingerprint"
_BIND_SOURCE_INTERACTIVE = 1
_USER_AGENT = f"WeComCLI/0.1.9 distribution/octop {platform.system().lower()}/{platform.machine()}"


def _write_file_atomic(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    """Replace ``path`` via temp file + ``os.replace``, applying ``mode`` first.

    ``write_text`` / ``write_bytes`` truncate before writing, and the following
    ``chmod(0o600)`` only runs afterwards — a crash in between leaves a torn file
    that is also readable by every local user. The temp file gets its final mode
    before it becomes visible, so readers only ever see a complete file.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if os.name == "posix":
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:  # also covers KeyboardInterrupt / SystemExit
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _existing_key(config_dir: Path) -> bytes | None:
    """Return the usable AES key in ``.encryption_key``, or ``None``.

    The key is the only copy of the material that decrypts ``bot.enc`` and
    ``mcp_config.enc``; it cannot be derived from the bot id/secret. A truncated
    or unreadable file therefore has to be treated as "no key" and re-created,
    never trusted just because the file exists.
    """
    key_path = config_dir / ".encryption_key"
    if not key_path.is_file():
        return None
    try:
        key = base64.b64decode(key_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return key if len(key) == 32 else None


def materialize_wecom_bot_config(config_dir: Path, *, bot_id: str, bot_secret: str) -> None:
    """Write ``.encryption_key`` + ``bot.enc`` + ``mcp_config.enc`` for wecom-cli.

    Format (from WecomTeam/wecom-cli): AES-256-GCM ciphertext as ``nonce || ct||tag``,
    key stored as base64 in ``.encryption_key``. MCP cache is required — bot.enc alone
    is not enough (``wecom-cli`` errors with “未找到 MCP 配置缓存”).
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = credential_fingerprint(bot_id, bot_secret)
    marker = config_dir / _FINGERPRINT_NAME
    mcp_path = config_dir / "mcp_config.enc"
    bot_path = config_dir / "bot.enc"
    if (
        marker.is_file()
        and bot_path.is_file()
        and mcp_path.is_file()
        and _existing_key(config_dir) is not None
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        return

    # Drop the marker before rewriting anything: if this pass fails halfway
    # (for example _fetch_mcp_config raises after the key was rotated), a marker
    # left in place would claim a cache that no longer decrypts, and every later
    # call would take the early return above and never repair it.
    marker.unlink(missing_ok=True)

    key = _load_or_create_key(config_dir)
    bot = {
        "id": bot_id,
        "secret": bot_secret,
        "create_time": int(time.time()),
    }
    _encrypt_json_to(bot_path, bot, key)

    items = _fetch_mcp_config(bot_id=bot_id, bot_secret=bot_secret)
    _encrypt_json_to(mcp_path, items, key)
    _write_file_atomic(marker, (fingerprint + "\n").encode("utf-8"))


def _load_or_create_key(config_dir: Path) -> bytes:
    key_path = config_dir / ".encryption_key"
    existing = _existing_key(config_dir)
    if existing is not None:
        return existing
    key = os.urandom(32)
    _write_file_atomic(key_path, base64.b64encode(key).decode("ascii").encode("ascii") + b"\n")
    return key


def _encrypt_json_to(path: Path, payload: Any, key: bytes) -> None:
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    _write_file_atomic(path, nonce + ciphertext)


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
    """Signed ``get_mcp_config`` — algorithm from wecom-cli: sha256(secret+bot_id+time+nonce).

    SHA-256 here is upstream protocol request signing, not password storage.
    """
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
