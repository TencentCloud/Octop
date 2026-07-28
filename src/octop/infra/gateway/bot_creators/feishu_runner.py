"""Feishu bot-creator subprocess runner (shared by API and CLI)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from octop.infra.utils.subprocess_io import parse_subprocess_json_lines

ALLOWED_PLATFORMS = frozenset({"feishu", "lark"})
PROFILE_NAMES = {
    "feishu": "octop-feishu-bot",
    "lark": "octop-lark-bot",
}


def bot_creator_script(name: str) -> Path:
    script = (Path(__file__).resolve().parent / name).resolve()
    expected_parent = script.parent.resolve()
    if not str(script).startswith(str(expected_parent)):
        raise RuntimeError("invalid bot creator script path")
    if not script.is_file():
        raise FileNotFoundError(f"{name} not found")
    return script


def resolve_profiles_root() -> Path:
    """Shared Octop profiles root; honor env overrides when present."""
    raw = (os.environ.get("BROWSER_USE_PROFILES_DIR") or "").strip()
    if not raw:
        raw = (os.environ.get("HARNESS_BROWSER_PROFILES_DIR") or "").strip()
    if raw and len(raw) <= 2048:
        return Path(raw).expanduser()
    from octop.infra.utils.browser_media import octop_browser_profiles_dir  # noqa: PLC0415

    return octop_browser_profiles_dir()


def feishu_profile_dir(platform: str) -> Path:
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError(f"platform must be one of {sorted(ALLOWED_PLATFORMS)}")
    root = resolve_profiles_root().resolve()
    profile = (root / PROFILE_NAMES[platform]).resolve()
    profile.relative_to(root)
    return profile


def clear_profile_locks(profile_dir: Path) -> None:
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (profile_dir / lock_name).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def start_feishu_creator(
    *,
    platform: str,
    avatar_url: str | None = None,
    greeting: str | None = None,
) -> subprocess.Popen[bytes]:
    if platform not in ALLOWED_PLATFORMS:
        raise ValueError(f"platform must be one of {sorted(ALLOWED_PLATFORMS)}")
    clear_profile_locks(feishu_profile_dir(platform))
    script_path = bot_creator_script("feishu_bot_creator.py")
    cmd = [sys.executable, str(script_path), "create", "--platform", platform]
    if avatar_url:
        cmd.extend(["--avatar-url", avatar_url])
    if greeting:
        cmd.extend(["--greeting", greeting])
    # NOCA:DangerousSubprocessUseAudit(argv list with shell=False; platform allowlisted, script path validated)
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        shell=False,
    )


def extract_feishu_credentials(
    lines: list[dict[str, Any]],
) -> tuple[str | None, str | None, str | None]:
    qr_token = None
    app_id = None
    app_secret = None
    for ev in lines:
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
    return qr_token, app_id, app_secret


def poll_feishu_creator(
    proc: subprocess.Popen[bytes], lines: list[dict[str, Any]]
) -> dict[str, Any]:
    """Read new JSON lines from *proc* and update accumulated *lines*."""
    new_lines = parse_subprocess_json_lines(proc)
    lines.extend(new_lines)
    return_code = proc.poll()
    finished = return_code is not None
    if finished and proc.stdout:
        remaining_bytes = proc.stdout.read()
        if remaining_bytes:
            for line in remaining_bytes.decode("utf-8", errors="replace").strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    lines.append({"action": "log", "level": "info", "step": "raw", "message": line})
    status = "running"
    if finished:
        status = "finished" if return_code == 0 else "failed"
    qr_token, app_id, app_secret = extract_feishu_credentials(lines)
    return {
        "status": status,
        "events": new_lines,
        "qr_token": qr_token,
        "app_id": app_id,
        "app_secret": app_secret,
        "return_code": return_code,
    }


def stop_feishu_creator(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)
