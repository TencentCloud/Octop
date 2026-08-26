"""Install / detect host CLIs for Feishu & WeCom connector adapters."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_INSTALL_TIMEOUT_S = 300.0
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)")
# fnOS / 容器里 Octop 常以非 root 用户运行，npm 全局目录（/usr/local）不可写，
# 此时降级到用户级目录安装，目录名沿用 npm 官方推荐的 ~/.npm-global。
_NPM_USER_PREFIX_NAME = ".npm-global"


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


def _prefix_bin_dir(prefix: str) -> str:
    # npm 在 POSIX 下把全局 bin 放在 <prefix>/bin，Windows 下放在 <prefix> 根目录。
    return prefix if os.name == "nt" else str(Path(prefix) / "bin")


def _npm_prefix_info(npm: str) -> tuple[str, str]:
    """Return ``(prefix, bin_dir)`` reported by ``npm config get prefix``."""
    try:
        completed = subprocess.run(
            [npm, "config", "get", "prefix"],
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", ""
    prefix = (completed.stdout or "").strip()
    if not prefix:
        return "", ""
    return prefix, _prefix_bin_dir(prefix)


def _user_npm_prefix() -> tuple[str, str]:
    """Return ``(prefix, bin_dir)`` for the user-level npm global directory."""
    prefix = os.path.join(os.path.expanduser("~"), _NPM_USER_PREFIX_NAME)
    return prefix, _prefix_bin_dir(prefix)


def _manual_install_command(npm_package: str, *, prefix: str | None = None) -> str:
    """Shell command users can paste; include ``--prefix`` when global is not writable."""
    if prefix:
        return f"npm install -g --prefix {prefix} {npm_package}"
    return f"npm install -g {npm_package}"


def _prefix_writable(prefix: str) -> bool:
    if not prefix:
        return False
    try:
        return os.access(prefix, os.W_OK)
    except OSError:
        return False


def ensure_cli_path() -> str:
    """Prepend the user-level npm global bin dir to the in-process PATH.

    Octop 在 fnOS 上常以非 root 用户运行，``/usr/local`` 下的 npm 全局目录
    不可写，安装会降级到用户级目录（~/.npm-global）。这里确保该 bin 目录
    进入进程 PATH，使 ``shutil.which`` 与后续 CLI 子进程调用都能找到命令。
    目录不存在时不做任何修改，返回 bin 目录（可能为空串）。
    """
    _, bin_dir = _user_npm_prefix()
    if bin_dir and os.path.isdir(bin_dir):
        current = os.environ.get("PATH", "")
        if bin_dir not in [part for part in current.split(os.pathsep) if part]:
            os.environ["PATH"] = bin_dir + os.pathsep + current
    return bin_dir


def cli_install_status(kind: str) -> dict[str, Any]:
    ensure_cli_path()
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

    # npm 全局目录（默认 /usr/local）不可写时（fnOS/容器内非 root 用户），
    # 自动降级到用户级目录 ~/.npm-global 安装，避免 EACCES 导致安装失败。
    prefix, _ = _npm_prefix_info(npm)
    install_args = [npm, "install", "-g"]
    user_prefix: str | None = None
    if not _prefix_writable(prefix):
        user_prefix, _user_bin = _user_npm_prefix()
        with contextlib.suppress(OSError):
            os.makedirs(user_prefix, exist_ok=True)
        install_args += ["--prefix", user_prefix]
        # Keep error / guide text aligned with the command that actually ran.
        status = {
            **status,
            "install_command": _manual_install_command(status["npm_package"], prefix=user_prefix),
        }

    try:
        completed = subprocess.run(
            install_args + [status["npm_package"]],
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
        if user_prefix is not None:
            msg = (
                f"{msg}。已尝试写入用户级目录（~/.npm-global）仍失败，"
                f"请在主机手动执行：{status['install_command']}"
            )
        else:
            msg = f"{msg}。请在主机手动执行：{status['install_command']}"
        return _fail(status, msg)

    # 降级安装到用户级目录后，把该 bin 目录加入进程 PATH，使状态检测与后续 CLI 调用可见。
    if user_prefix is not None:
        ensure_cli_path()

    refreshed = cli_install_status(kind)
    if user_prefix is not None:
        refreshed = {
            **refreshed,
            "install_command": _manual_install_command(
                refreshed["npm_package"], prefix=user_prefix
            ),
        }
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
