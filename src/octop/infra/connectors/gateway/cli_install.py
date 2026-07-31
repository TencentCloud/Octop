"""Install / detect host CLIs for Feishu & WeCom connector adapters."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

_INSTALL_TIMEOUT_S = 300.0
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)")


@dataclass(frozen=True)
class CliInstallSpec:
    kind: str
    binary: str
    npm_package: str
    doc_url: str
    guide_url: str | None

    @property
    def install_command(self) -> str:
        return f"npm install -g {self.npm_package}"


_SPECS: dict[str, CliInstallSpec] = {
    "feishu-cli": CliInstallSpec(
        kind="feishu-cli",
        binary="lark-cli",
        npm_package="@larksuite/cli",
        doc_url="https://github.com/larksuite/cli",
        guide_url=(
            "https://open.feishu.cn/document/mcp_open_tools/feishu-cli/"
            "set-up-lark-cli-for-ai-agents-in-openclaw_hermes.md"
        ),
    ),
    "wecom-cli": CliInstallSpec(
        kind="wecom-cli",
        binary="wecom-cli",
        npm_package="@wecom/cli",
        doc_url="https://github.com/WecomTeam/wecom-cli",
        guide_url="https://open.work.weixin.qq.com/help2/pc/21676",
    ),
}


def get_cli_install_spec(kind: str) -> CliInstallSpec | None:
    return _SPECS.get(kind)


def cli_install_status(kind: str) -> dict[str, Any]:
    spec = get_cli_install_spec(kind)
    if spec is None:
        raise ValueError(f"kind {kind!r} does not support CLI install")
    path = shutil.which(spec.binary)
    version = _read_version(path) if path else None
    return {
        "kind": kind,
        "binary": spec.binary,
        "npm_package": spec.npm_package,
        "install_command": spec.install_command,
        "doc_url": spec.doc_url,
        "guide_url": spec.guide_url,
        "installed": bool(path),
        "binary_path": path,
        "version": version,
    }


def install_connector_cli(kind: str) -> dict[str, Any]:
    """Ensure the host CLI is installed. Never raises for install failure — returns ok=False."""
    status = cli_install_status(kind)
    if status["installed"]:
        return {
            "ok": True,
            "already_installed": True,
            **status,
        }

    npm = shutil.which("npm")
    if not npm:
        return _fail(
            status,
            f"未找到 npm，请先在 Octop 主机安装 Node.js，然后执行：{status['install_command']}",
        )

    try:
        completed = subprocess.run(
            [npm, "install", "-g", status["npm_package"]],
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _fail(
            status,
            f"安装超时（>{int(_INSTALL_TIMEOUT_S)}s）。请在主机手动执行：{status['install_command']}",
        )
    except OSError as exc:
        return _fail(status, f"无法启动 npm：{exc}")

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if len(detail) > 800:
            detail = detail[-800:]
        msg = f"npm install 失败（exit {completed.returncode}）"
        if detail:
            msg = f"{msg}：{detail}"
        msg = f"{msg}。请在主机手动执行：{status['install_command']}"
        return _fail(status, msg)

    refreshed = cli_install_status(kind)
    if not refreshed["installed"]:
        return _fail(
            refreshed,
            "npm install 已完成，但 PATH 中仍找不到 "
            f"{refreshed['binary']!r}。请确认全局 bin 目录在 PATH 中，"
            f"或手动执行：{refreshed['install_command']}",
        )
    return {
        "ok": True,
        "already_installed": False,
        **refreshed,
    }


def _fail(status: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "already_installed": False,
        "error": error,
        **status,
        "installed": bool(status.get("installed")),
    }


def _read_version(binary_path: str) -> str | None:
    for args in ([binary_path, "--version"], [binary_path, "-V"], [binary_path, "version"]):
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        if completed.returncode != 0 or not text:
            continue
        match = _VERSION_RE.search(text)
        return match.group(1) if match else text.splitlines()[0][:80]
    return None
