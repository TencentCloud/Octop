"""Shared subprocess runner for official connector CLIs (lark-cli / wecom-cli)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from typing import Any

DEFAULT_TIMEOUT_S = 30.0
_MAX_ERR_CHARS = 4000


def resolve_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ValueError(
            f"未找到主机命令 {name!r}。"
            "请打开 Octop「连接器」抽屉，由管理员安装 CLI，或在主机 PATH 中自行安装。"
            "禁止在 Agent 终端中查找或安装该命令。"
        )
    return path


def run_cli(
    argv: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    cwd: str | None = None,
    stdin_text: str | None = None,
) -> str:
    """Run argv; return stdout on success. Raise ValueError on failure."""
    if not argv:
        raise ValueError("CLI argv is empty")
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            env=dict(env) if env is not None else None,
            timeout=timeout_s,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"未找到命令 {argv[0]!r}，请检查 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"CLI 超时（>{timeout_s:.0f}s）: {' '.join(argv[:4])}") from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode == 0:
        return stdout or "{}"

    raise ValueError(_format_cli_error(completed.returncode, stdout, stderr))


def _format_cli_error(returncode: int, stdout: str, stderr: str) -> str:
    payload = _parse_error_payload(stderr) or _parse_error_payload(stdout)
    if payload is not None:
        message = str(payload.get("message") or payload.get("msg") or "").strip()
        hint = str(payload.get("hint") or "").strip()
        err = payload.get("error")
        if isinstance(err, dict):
            if not message:
                message = str(err.get("message") or "").strip()
            if not hint:
                hint = str(err.get("hint") or "").strip()
        # Never forward CLI "run xxx" hints to agents — they cause shell/auth loops.
        if hint and ("lark-cli" in hint.lower() or "wecom-cli" in hint.lower()):
            hint = ""
        parts = [p for p in (message, hint) if p]
        if parts:
            return " | ".join(parts)

    raw = stderr or stdout or f"CLI exited with code {returncode}"
    if len(raw) > _MAX_ERR_CHARS:
        raw = raw[:_MAX_ERR_CHARS] + "…"
    return raw


def _parse_error_payload(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
