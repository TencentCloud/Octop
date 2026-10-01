#!/usr/bin/env python3
# Copyright (C) 2025 Tencent. All rights reserved.
#
# This software is independently developed by Tencent Lighthouse Team.
# Unauthorized copying, modification, distribution, or commercial use
# of this software, in whole or in part, is strictly prohibited.
# Violators will be held liable under applicable laws.
#
# Author: Tencent Lighthouse Team
"""
YuanBao Open Platform - Auto-bind bot via QR scan (non-interactive).

Usage:
    python3 yuanbao_bot_creator.py create [instance_id] [ip]   # Full flow: get scan_code -> scan -> emit finish
    python3 yuanbao_bot_creator.py cleanup                      # Clean up state files

If instance_id / ip are omitted, they are auto-detected from Tencent Cloud
metadata service (or fallback to local values).

Flow: create (get scan_code + user scan confirm + emit credentials via finish event)
"""

from __future__ import annotations

import sys

# Force stdout line-buffered / write-through so the parent process can read
# structured JSON lines in real time (Python defaults to full buffering in
# pipe environments). Encoding is pinned to UTF-8 because the parent decodes
# these lines as UTF-8 and the ANSI code page (cp936) cannot carry every
# character the messages may contain.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", write_through=True)
elif hasattr(sys.stdout, "buffer"):
    import io as _io

    sys.stdout = _io.TextIOWrapper(
        sys.stdout.buffer,
        write_through=True,
        encoding="utf-8",
        errors="replace",
    )

# ============================================================
# Business imports
# ============================================================
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, cast
from urllib.parse import urlencode

# ============================================================
# Constants
# ============================================================
YUANBAO_DOMAIN = "bot.yuanbao.tencent.com"
API_BASE = f"https://{YUANBAO_DOMAIN}"

POLL_INTERVAL = 3
QR_MAX_RETRIES = 3

STATE_DIR = "/tmp"
STATE_FILE = os.path.join(STATE_DIR, "yuanbao-bot-creator-state.json")

_HEADERS = {
    "User-Agent": "RobotManager/1.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Source": "robot_manager",
}

_SSL_CTX = ssl.create_default_context()


# ============================================================
# State file helpers
# ============================================================
def _save_state(data: dict[str, Any]) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False)


# ============================================================
# Structured JSON output (stdout) — same protocol as feishu bot_creator
# ============================================================
def _emit(action: str, level: str, step: str, message: str, **extra: object) -> None:
    """Write one structured JSON log line to stdout."""
    record: dict[str, Any] = {
        "action": action,
        "level": level,
        "step": step,
        "message": message,
        "ts": int(time.time()),
    }
    record.update(extra)
    print(json.dumps(record, ensure_ascii=False))


def _log_info(step: str, message: str, **extra: object) -> None:
    _emit("log", "info", step, message, **extra)


def _log_success(step: str, message: str, **extra: object) -> None:
    _emit("log", "success", step, message, **extra)


def _log_warn(step: str, message: str, **extra: object) -> None:
    _emit("log", "warn", step, message, **extra)


def _log_error(step: str, message: str, **extra: object) -> None:
    _emit("log", "error", step, message, **extra)


def _emit_progress(step: str, message: str, current: int, total: int) -> None:
    _emit("progress", "info", step, message, current=current, total=total)


def _emit_finish(message: str, data: dict[str, Any]) -> None:
    _emit("finish", "success", "finish", message, data=data)


def _emit_error(step: str, message: str) -> None:
    _emit("finish", "error", step, message)


# ============================================================
# HTTP helpers (stdlib only, no third-party deps)
# ============================================================
def _http_get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Send GET request and return parsed JSON dict."""
    if params:
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as resp:
            return cast(dict[str, Any] | None, json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        try:
            return cast(dict[str, Any] | None, json.loads(e.read().decode("utf-8")))
        except Exception:
            _log_error("http", f"GET {url} HTTP {e.code}: {e.reason}")
            return None
    except Exception as e:
        _log_error("http", f"GET {url} error: {e}")
        return None


def _http_post(url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Send POST request and return parsed JSON dict."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=30) as resp:
            return cast(dict[str, Any] | None, json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        try:
            return cast(dict[str, Any] | None, json.loads(e.read().decode("utf-8")))
        except Exception:
            _log_error("http", f"POST {url} HTTP {e.code}: {e.reason}")
            return None
    except Exception as e:
        _log_error("http", f"POST {url} error: {e}")
        return None


# ============================================================
# Core: YuanBao Bot Creator
# ============================================================
class YuanbaoBotCreator:
    """YuanBao bot creator — complete scan-bind flow via REST API."""

    def __init__(self, instance_id: str, ip: str) -> None:
        self.scan_code: str | None = None
        self.access_code: str | None = None
        self.scan_url: str | None = None
        self.expires_in: int = 900  # default 15 min, overridden by API response
        self.app_key: str | None = None
        self.app_secret: str | None = None
        self.instance_id: str = instance_id
        self.ip: str = ip

    # ---------- Step 1: Get scan-bind code ----------
    def step1_get_scan_bind_code(self) -> bool:
        """Call get-scan-bind-code (GET) to obtain scan_code and access_code."""
        _log_info("bind_code", "Requesting scan-bind code...")

        params = {
            "instance_id": self.instance_id,
            "ip": self.ip,
            "source": "tx_cloud_lighthouse",
            "bot_type": 1,
        }

        resp = _http_get(f"{API_BASE}/api/v5/robotLogic/get-scan-bind-code", params)
        if resp is None:
            _log_error("bind_code", "Request failed, cannot generate QR code")
            return False

        code = resp.get("code")
        if code != 0:
            _log_error(
                "bind_code",
                f"Failed to generate QR code: code={code}, msg={resp.get('msg', 'unknown')}",
            )
            return False

        data = resp.get("data", {})
        self.scan_code = data.get("scan_code")
        self.access_code = data.get("access_code")
        self.scan_url = data.get("scan_url")
        self.expires_in = data.get("expires_in", 900)

        if not self.scan_code or not self.access_code:
            _log_error("bind_code", f"Response missing required fields: {data}")
            return False

        _log_success("bind_code", f"Got scan_code={self.scan_code}")
        return True

    # ---------- Step 2: Emit scan_code for frontend ----------
    def step2_display_qrcode(self) -> None:
        """Emit scan_code / scan_url for the parent process to consume."""
        _log_info("scan_code", f"scan_code={self.scan_code}")
        if self.scan_url:
            _log_info("scan_code", f"scan_url={self.scan_url}")
        _emit(
            "scan_code",
            "info",
            "scan_code",
            "Scan code ready",
            scan_code=self.scan_code,
            scan_url=self.scan_url,
        )

    # ---------- Step 3: Poll scan status ----------
    def step3_poll_scan_status(self) -> bool:
        """Poll check-scan-bind-status until user confirms or timeout.

        Status codes:
            0 -> waiting for scan
            1 -> scanned, waiting for confirm
            2 -> confirmed (success, got app_key + app_secret)
            3 -> cancelled
            4 -> expired
        """
        _log_info("poll", f"Waiting for user scan (expires in {self.expires_in}s)...")

        deadline = time.time() + self.expires_in
        attempt = 0
        total_attempts = self.expires_in // POLL_INTERVAL
        last_status = -1

        while time.time() < deadline:
            attempt += 1

            resp = _http_post(
                f"{API_BASE}/api/v5/robotLogic/check-scan-bind-status",
                {
                    "scan_code": self.scan_code,
                    "access_code": self.access_code,
                },
            )

            if resp is None:
                _log_warn("poll", f"Poll attempt {attempt} failed, retrying...")
                time.sleep(POLL_INTERVAL)
                continue

            resp_code = resp.get("code")
            if resp_code != 0:
                _log_warn("poll", f"Poll error: code={resp_code}, msg={resp.get('msg')}")
                time.sleep(POLL_INTERVAL)
                continue

            data = resp.get("data", {})
            status = data.get("status", 0)

            if status != last_status:
                last_status = status

                if status == 0:
                    _emit_progress(
                        "poll", "Waiting for scan...", current=attempt, total=total_attempts
                    )
                elif status == 1:
                    _log_info("poll", "User scanned, please confirm on phone")
                elif status == 2:
                    self.app_key = data.get("app_key")
                    self.app_secret = data.get("app_secret")

                    if not self.app_key or not self.app_secret:
                        _log_error("poll", f"Bind succeeded but missing credentials: {data}")
                        return False

                    _log_success("poll", "User confirmed, got bot credentials")
                    _log_info("poll", f"  app_key:    {self.app_key}")
                    _log_info("poll", f"  app_secret: {self.app_secret}")
                    return True
                elif status == 3:
                    _log_error("poll", "User cancelled binding")
                    return False
                elif status == 4:
                    _log_warn("poll", "QR code expired")
                    return False
            elif status == 0 and attempt % 10 == 0:
                _emit_progress("poll", "Waiting for scan...", current=attempt, total=total_attempts)

            time.sleep(POLL_INTERVAL)

        _log_error("poll", "Scan wait timed out")
        return False

    # ---------- Main orchestration ----------
    def run(self) -> bool:
        """Execute the full creation flow: generate QR -> scan -> emit credentials."""
        for attempt in range(1, QR_MAX_RETRIES + 1):
            _log_info("main", f"Attempt {attempt}/{QR_MAX_RETRIES}")

            # Step 1: Generate QR code
            if not self.step1_get_scan_bind_code():
                if attempt < QR_MAX_RETRIES:
                    _log_warn("main", "Failed to generate QR code, retrying...")
                    time.sleep(3)
                    continue
                return False

            # Step 2: Emit scan code
            self.step2_display_qrcode()

            # Save intermediate state
            _save_state(
                {
                    "phase": "waiting_scan",
                    "scan_code": self.scan_code,
                    "instance_id": self.instance_id,
                    "ip": self.ip,
                }
            )

            # Step 3: Poll scan status
            poll_result = self.step3_poll_scan_status()

            if poll_result:
                break
            elif attempt < QR_MAX_RETRIES:
                _log_info("main", "Regenerating QR code...")
                time.sleep(2)
                continue
            else:
                return False
        else:
            _log_error("main", f"Max retries reached ({QR_MAX_RETRIES})")
            return False

        # orca: credentials are returned via finish event, caller handles storage
        _emit_finish(
            "YuanBao bot binding complete",
            {
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "instance_id": self.instance_id,
                "ip": self.ip,
            },
        )
        return True


# ============================================================
# Auto-detect helpers (Tencent Cloud metadata service)
# ============================================================
def _detect_instance_id() -> str:
    """Try to fetch instance-id from Tencent Cloud metadata service."""
    try:
        req = urllib.request.Request(
            "http://metadata.tencentyun.com/latest/meta-data/instance-id",
            headers={"User-Agent": "RobotManager/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            val = resp.read().decode("utf-8").strip()
            if val:
                return cast(str, val)
    except Exception:
        pass
    return f"local-{uuid.uuid4().hex[:8]}"


def _detect_public_ip() -> str:
    """Try to fetch public IPv4 from Tencent Cloud metadata service."""
    try:
        req = urllib.request.Request(
            "http://metadata.tencentyun.com/latest/meta-data/public-ipv4",
            headers={"User-Agent": "RobotManager/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            val = resp.read().decode("utf-8").strip()
            if val:
                return cast(str, val)
    except Exception:
        pass
    # Fallback: local hostname IP
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


# ============================================================
# Command: create
# ============================================================
def cmd_create() -> None:
    # instance_id and ip are optional; auto-detect if not provided
    instance_id = sys.argv[2] if len(sys.argv) > 2 else ""
    ip = sys.argv[3] if len(sys.argv) > 3 else ""

    if not instance_id or not ip:
        # Detect in parallel to avoid sequential 1s+1s timeout on non-cloud envs
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_id = pool.submit(_detect_instance_id) if not instance_id else None
            fut_ip = pool.submit(_detect_public_ip) if not ip else None
            if fut_id:
                instance_id = fut_id.result()
                _log_info("create", f"Auto-detected instance_id={instance_id}")
            if fut_ip:
                ip = fut_ip.result()
                _log_info("create", f"Auto-detected ip={ip}")

    _log_info("create", f"Starting YuanBao bot bind flow (instance_id={instance_id}, ip={ip})")

    creator = YuanbaoBotCreator(instance_id=instance_id, ip=ip)
    ok = creator.run()

    if not ok:
        _emit_error("create", "YuanBao bot binding failed")
        sys.exit(1)

    result = {
        "app_key": creator.app_key,
        "app_secret": creator.app_secret,
        "instance_id": creator.instance_id,
        "ip": creator.ip,
    }

    _save_state({"phase": "done", **result})


# ============================================================
# Command: cleanup
# ============================================================
def cmd_cleanup() -> None:
    if os.path.isfile(STATE_FILE):
        os.remove(STATE_FILE)
    _log_success("cleanup", "State files cleaned up")


# ============================================================
# Entry point
# ============================================================
def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "create":
        cmd_create()
    elif cmd == "cleanup":
        cmd_cleanup()
    else:
        _emit_error("main", f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
