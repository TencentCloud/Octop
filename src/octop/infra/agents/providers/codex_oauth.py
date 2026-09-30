"""OpenAI Codex (ChatGPT) OAuth — device code flow.

Ported from finnie/lightclaw; constants match openclaw wire contract.
Tokens live at ``~/.octop/codex_oauth.json``.

Octop is a server (not a local CLI), so it cannot use the PKCE browser
redirect flow: that flow's shared client only accepts the exact
``http://localhost:1455/auth/callback`` redirect_uri that OpenAI's own
Codex CLI binds locally, which a hosted backend can never match. The
device code flow has no redirect_uri at all — the user visits a
verification URL and enters a short code, and the backend polls for
completion — so it works regardless of how/where Octop is deployed.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TypedDict

from octop.infra.utils.json_file import write_json_atomic
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

# ★★ N 批（`PLAN §4` · `N-3`）刷新单飞：**进程内锁** —— 并发调用者不再各刷一次
#   （★ `get_valid_access_token` 由 `asyncio.to_thread` 调用 ⇒ 用 `threading.Lock` ✓）
_REFRESH_LOCK = threading.Lock()

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
DEVICE_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
DEVICE_CALLBACK_URL = "https://auth.openai.com/deviceauth/callback"
DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
DEVICE_POLL_TIMEOUT_S = 15 * 60
DEVICE_POLL_DEFAULT_INTERVAL_S = 5
TOKEN_REQUEST_TIMEOUT_S = 30
TOKEN_EXPIRY_BUFFER_MS = 5 * 60 * 1000
CODEX_ATTRIBUTION_ORIGINATOR = "openclaw"
_OPENCLAW_UPSTREAM_VERSION = "2026.6.9"
CODEX_ATTRIBUTION_VERSION = (
    os.environ.get("OCTOP_CODEX_ATTRIBUTION_VERSION", "").strip() or _OPENCLAW_UPSTREAM_VERSION
)
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"


class CodexOAuthCredentials(TypedDict):
    access: str
    refresh: str
    expires: int
    account_id: str


class CodexOAuthRefreshError(RuntimeError):
    def __init__(self, message: str, *, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason


class CodexOAuthDeviceCodeError(RuntimeError):
    """A sanitized failure while starting the ChatGPT device-code flow."""

    def __init__(self, *, reason: str, upstream_status: int | None = None) -> None:
        super().__init__("Codex device code request failed")
        self.reason = reason
        self.upstream_status = upstream_status


def oauth_token_file(paths: PathLayout) -> Path:
    return paths.root / "codex_oauth.json"


def _decode_jwt_payload(access_token: str) -> dict[str, object] | None:
    parts = access_token.split(".")
    if len(parts) != 3:
        return None
    try:
        padded = parts[1] + "=="[: (4 - len(parts[1]) % 4) % 4]
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        result: dict[str, object] = json.loads(decoded)
        return result
    except Exception:
        return None


def extract_account_id(access_token: str) -> str:
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return ""
    auth = payload.get("https://api.openai.com/auth", {})
    if not isinstance(auth, dict):
        return ""
    account_id = auth.get("chatgpt_account_id", "")
    return str(account_id).strip() if account_id else ""


def extract_token_expiry_ms(access_token: str, fallback_expires_in_s: int = 3600) -> int:
    payload = _decode_jwt_payload(access_token)
    if payload:
        exp = payload.get("exp")
        if isinstance(exp, int | float) and exp > 0:
            return int(exp) * 1000
    return int(time.time() * 1000) + fallback_expires_in_s * 1000


def cleanup_stale_tmp(path: Path) -> None:
    """★ `N-2` 启动/写入前清理：删除 `.{name}.*.tmp`（上次中断留下的临时文件）。

    ★ 只删本文件的临时前缀 ⇒ 不碰他人文件 · ★ 幂等 ✓。
    """
    for stale in path.parent.glob(f".{path.name}.*.tmp"):
        with contextlib.suppress(OSError):
            stale.unlink()


def _ensure_private_target(path: Path) -> None:
    """★ `N-1`：目标文件先以 **`0600`** 就位。

    ★ 关键：`write_json_atomic` 沿用【被替换文件的权限】（新文件则随 umask ⇒ 可能 0644 ✗）⇒
    ★ 先把目标建/修成 `0600` ⇒ **tmp 与目标**都落在 `0600` ✓（★ 文件含 refresh token ⇒ 必须私有）。
    """
    if not path.exists():
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(handle)
    if os.name == "posix":
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)


def save_codex_token(paths: PathLayout, cred: CodexOAuthCredentials) -> None:
    """★ `N-1`：**原子写**（tmp + `os.replace`）⇒ 中断不会留下被截断的 JSON。

    ★ 目标与 tmp 均 `0600`（★ 该文件含 `access` + **`refresh`** 明文）· ★ 写前清理陈旧 tmp ✓。
    """
    path = oauth_token_file(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_tmp(path)
    _ensure_private_target(path)
    write_json_atomic(path, dict(cred))
    if os.name == "posix":
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)


def load_codex_token(paths: PathLayout) -> CodexOAuthCredentials | None:
    path = oauth_token_file(paths)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if all(k in data for k in ("access", "refresh", "expires")):
            return CodexOAuthCredentials(
                access=data["access"],
                refresh=data["refresh"],
                expires=int(data["expires"]),
                account_id=data.get("account_id", ""),
            )
    except Exception as exc:
        logger.warning("Failed to load Codex OAuth token: %s", exc)
    return None


def delete_codex_token(paths: PathLayout) -> None:
    path = oauth_token_file(paths)
    if path.exists():
        path.unlink()


def is_token_valid(cred: CodexOAuthCredentials) -> bool:
    return time.time() * 1000 < cred["expires"] - TOKEN_EXPIRY_BUFFER_MS


def refresh_codex_token(paths: PathLayout, cred: CodexOAuthCredentials) -> CodexOAuthCredentials:
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": cred["refresh"],
            "client_id": CLIENT_ID,
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_REQUEST_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise CodexOAuthRefreshError(
            f"Codex token refresh failed (HTTP {exc.code}): {body_text}"
        ) from exc
    new_access = data["access_token"]
    new_cred = CodexOAuthCredentials(
        access=new_access,
        refresh=data.get("refresh_token", cred["refresh"]),
        expires=extract_token_expiry_ms(new_access, int(data.get("expires_in", 3600))),
        account_id=extract_account_id(new_access) or cred.get("account_id", ""),
    )
    save_codex_token(paths, new_cred)
    return new_cred


def get_valid_access_token(paths: PathLayout) -> str | None:
    """★ `N-3` **刷新单飞**：刷新在进程内锁内进行，锁内**二次读盘**（别人可能已刷好）。

    ★ 否则并发首调会各自 `refresh` 一次 ⇒ 后到者的 `refresh_token` 可能已被轮换而失效 ✗。
    """
    cred = load_codex_token(paths)
    if cred is None:
        return None
    if is_token_valid(cred):
        return cred["access"]
    with _REFRESH_LOCK:
        # ★ 二次检查：拿锁后重新读盘 —— 若已由别的线程刷新成功 ⇒ 直接用（不再发第二次请求）
        current = load_codex_token(paths)
        if current is not None and is_token_valid(current):
            return current["access"]
        cred = current if current is not None else cred
        try:
            cred = refresh_codex_token(paths, cred)
        except CodexOAuthRefreshError as exc:
            logger.warning("Codex OAuth refresh failed: %s", exc)
            return None
    return cred["access"]


def build_codex_headers(account_id: str) -> dict[str, str]:
    headers = {
        "originator": CODEX_ATTRIBUTION_ORIGINATOR,
        "version": CODEX_ATTRIBUTION_VERSION,
        "User-Agent": f"{CODEX_ATTRIBUTION_ORIGINATOR}/{CODEX_ATTRIBUTION_VERSION}",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id
    return headers


class DeviceCodeInfo(TypedDict):
    device_auth_id: str
    user_code: str
    verification_url: str
    interval_s: float


def _device_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "originator": CODEX_ATTRIBUTION_ORIGINATOR,
        "User-Agent": f"{CODEX_ATTRIBUTION_ORIGINATOR}/{CODEX_ATTRIBUTION_VERSION}",
    }


def request_device_code() -> DeviceCodeInfo:
    """Start a device-code login. The user visits ``verification_url`` and enters ``user_code``."""
    req = urllib.request.Request(
        DEVICE_USERCODE_URL,
        data=json.dumps({"client_id": CLIENT_ID}).encode(),
        headers=_device_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_REQUEST_TIMEOUT_S) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise CodexOAuthDeviceCodeError(
            reason="upstream_http_error", upstream_status=exc.code
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CodexOAuthDeviceCodeError(reason="network_error") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexOAuthDeviceCodeError(reason="invalid_response") from exc
    if not isinstance(body, dict):
        raise CodexOAuthDeviceCodeError(reason="invalid_response")
    device_auth_id = body.get("device_auth_id", "")
    user_code = body.get("user_code") or body.get("usercode") or ""
    if not device_auth_id or not user_code:
        raise CodexOAuthDeviceCodeError(reason="invalid_response")
    return DeviceCodeInfo(
        device_auth_id=device_auth_id,
        user_code=user_code,
        verification_url=DEVICE_VERIFICATION_URL,
        interval_s=float(body.get("interval") or DEVICE_POLL_DEFAULT_INTERVAL_S),
    )


def poll_device_token(device_auth_id: str, user_code: str) -> tuple[str, str] | None:
    """One poll attempt. Returns ``(auth_code, code_verifier)`` once the user authorizes, else None."""
    req = urllib.request.Request(
        DEVICE_TOKEN_URL,
        data=json.dumps({"device_auth_id": device_auth_id, "user_code": user_code}).encode(),
        headers=_device_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_REQUEST_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return None
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"Codex device code poll failed (HTTP {exc.code}): {body_text}") from exc
    auth_code = data.get("authorization_code")
    code_verifier = data.get("code_verifier")
    if auth_code and code_verifier:
        return auth_code, code_verifier
    return None


def exchange_device_code(code: str, verifier: str) -> CodexOAuthCredentials:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": DEVICE_CALLBACK_URL,
        }
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_REQUEST_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"Codex token exchange failed (HTTP {exc.code}): {body_text}") from exc
    access = data["access_token"]
    return CodexOAuthCredentials(
        access=access,
        refresh=data["refresh_token"],
        expires=extract_token_expiry_ms(access, int(data.get("expires_in", 3600))),
        account_id=extract_account_id(access),
    )
