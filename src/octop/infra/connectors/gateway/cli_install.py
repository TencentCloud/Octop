"""Install / detect host CLIs for Feishu & WeCom connector adapters."""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import shutil
import subprocess
import sys
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
    npm_package: str | None
    doc_url: str
    guide_url: str | None

    @property
    def install_command(self) -> str:
        if not self.npm_package:
            return ""
        return f"npm install -g {self.npm_package}"


_SPECS: dict[str, CliInstallSpec] = {
    "agently-cli": CliInstallSpec(
        kind="agently-cli",
        binary="agently-cli",
        npm_package="@tencent-qqmail/agently-cli@1.0.18",
        doc_url="https://github.com/Tencent/AgentlyMail",
        guide_url="https://help.agent.qq.com/detail/0/1092",
    ),
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
    "obsidian-cli": CliInstallSpec(
        kind="obsidian-cli",
        binary="obsidian",
        npm_package=None,
        doc_url="https://obsidian.md/cli",
        guide_url="https://obsidian.md/zh/cli",
    ),
}

OBSIDIAN_CLI_MISSING = (
    "主机上未找到 Obsidian CLI（obsidian）。"
    "请在本机打开 Obsidian，于设置 → 通用中启用 Command line interface，并按提示注册到 PATH。"
    "Octop 与 Obsidian 必须在同一台主机。"
    "禁止建议或执行任何终端命令。"
)
OBSIDIAN_NOT_RUNNING = (
    "Obsidian 未在运行，或 CLI 无法连接桌面应用。"
    "请在 Octop 所在主机打开 Obsidian，并确认已启用 Command line interface。"
    "禁止建议或执行任何终端命令。"
)


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


def _prepend_path(bin_dir: str) -> None:
    if not bin_dir or not os.path.isdir(bin_dir):
        return
    current = os.environ.get("PATH", "")
    parts = [part for part in current.split(os.pathsep) if part]
    if bin_dir not in parts:
        os.environ["PATH"] = bin_dir + os.pathsep + current


def ensure_cli_path() -> str:
    """Prepend user-level bin dirs to the in-process PATH.

    Octop 在 fnOS 上常以非 root 用户运行，``/usr/local`` 下的 npm 全局目录
    不可写，安装会降级到用户级目录（~/.npm-global）。Obsidian CLI 在系统
    bin 不可写时同样落到 ``~/.local/bin``。这里确保这些目录进入进程 PATH，
    使 ``shutil.which`` 与后续 CLI 子进程调用都能找到命令。
    目录不存在时不做任何修改，返回 npm 用户级 bin 目录（可能为空串）。
    """
    local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
    _prepend_path(local_bin)
    if os.name == "nt":
        # ``Obsidian.com`` only works beside ``Obsidian.exe``. Register that directory
        # instead of copying the redirector away from the app.
        for candidate in obsidian_bundle_candidates():
            if candidate.lower().endswith(".com") and os.path.isfile(candidate):
                _prepend_path(os.path.dirname(candidate))
                break
    _, bin_dir = _user_npm_prefix()
    _prepend_path(bin_dir)
    return bin_dir


def obsidian_bundle_candidates() -> list[str]:
    """Bundled Obsidian CLI paths. These are not on PATH until install registers them.

    Official layout differs by OS:
    macOS links ``obsidian-cli`` inside the app bundle;
    Linux copies ``obsidian-cli`` out of the install directory;
    Windows registers ``Obsidian.com``, the terminal redirector next to ``Obsidian.exe``.
    """
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return ["/Applications/Obsidian.app/Contents/MacOS/obsidian-cli"]
    if os.name == "nt":
        roots: list[str] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            roots.append(os.path.join(local_app_data, "Obsidian"))
            roots.append(os.path.join(local_app_data, "Programs", "Obsidian"))
        program_files = os.environ.get("PROGRAMFILES")
        if program_files:
            roots.append(os.path.join(program_files, "Obsidian"))
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
        if program_files_x86:
            roots.append(os.path.join(program_files_x86, "Obsidian"))
        paths: list[str] = []
        for root in roots:
            # ``Obsidian.com`` is the official stdin/stdout redirector. ``obsidian-cli.exe``
            # covers installs that ship the CLI under that name.
            paths.append(os.path.join(root, "Obsidian.com"))
            paths.append(os.path.join(root, "obsidian-cli.exe"))
        return paths
    return [
        "/opt/Obsidian/obsidian-cli",
        "/usr/lib/obsidian/obsidian-cli",
        os.path.join(home, ".local", "share", "obsidian", "obsidian-cli"),
        "/snap/obsidian/current/obsidian-cli",
    ]


def _default_obsidian_bundle_hint() -> str:
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(local, "Obsidian", "Obsidian.com")
    if sys.platform == "darwin":
        return "/Applications/Obsidian.app/Contents/MacOS/obsidian-cli"
    return "/opt/Obsidian/obsidian-cli"


def _find_obsidian_bundle() -> str | None:
    for candidate in obsidian_bundle_candidates():
        if os.path.isfile(candidate):
            return candidate
    return None


def _windows_cli_filename(source: str | None) -> str:
    if source:
        suffix = os.path.splitext(source)[1].lower()
        if suffix in {".exe", ".com", ".cmd", ".bat"}:
            return "obsidian" + suffix
    return "obsidian.exe"


def _is_windows_redirector(path: str | None) -> bool:
    return bool(path) and str(path).lower().endswith(".com")


def _obsidian_install_destination(source: str | None = None) -> str:
    """PATH location that matches Obsidian's own registration for this OS."""
    user_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
    if os.name == "nt":
        if _is_windows_redirector(source):
            # Leave ``Obsidian.com`` beside ``Obsidian.exe``; PATH registration finds it.
            return str(source)
        return os.path.join(user_bin, _windows_cli_filename(source))
    if sys.platform == "linux":
        # Official Linux registration copies into ~/.local/bin. A symlink breaks when the
        # app lives in a temporary install directory (AppImage and some package builds).
        return os.path.join(user_bin, "obsidian")
    system_bin = "/usr/local/bin"
    if os.path.isdir(system_bin) and _prefix_writable(system_bin):
        return os.path.join(system_bin, "obsidian")
    return os.path.join(user_bin, "obsidian")


def _windows_user_path_command(directory: str) -> str:
    """User-PATH registration. ``Obsidian.com`` must stay next to ``Obsidian.exe``."""
    quoted = "'" + directory.replace("'", "''") + "'"
    return (
        "powershell -NoProfile -Command "
        f"\"$d={quoted}; $p=[Environment]::GetEnvironmentVariable('Path','User'); "
        "if (-not $p) { $p='' }; "
        "if ($p.Split(';') -notcontains $d) { "
        "[Environment]::SetEnvironmentVariable('Path', "
        "(($p.TrimEnd(';') + ';' + $d).Trim(';')), 'User') }\""
    )


def obsidian_install_command(source: str | None = None, dest: str | None = None) -> str:
    """Shell command matching the registration Octop performs for Obsidian CLI."""
    src = source or _find_obsidian_bundle() or _default_obsidian_bundle_hint()
    if os.name == "nt" and _is_windows_redirector(src):
        return _windows_user_path_command(os.path.dirname(src))
    target = dest or _obsidian_install_destination(src)
    parent = os.path.dirname(target)
    if os.name == "nt":
        return f'mkdir "{parent}" & copy /Y "{src}" "{target}"'
    if sys.platform == "darwin":
        return f"ln -sfn {shlex.quote(src)} {shlex.quote(target)}"
    return (
        f"mkdir -p {shlex.quote(parent)} && "
        f"cp {shlex.quote(src)} {shlex.quote(target)} && "
        f"chmod 755 {shlex.quote(target)}"
    )


def _place_obsidian_binary(source: str, dest: str) -> None:
    if _is_windows_redirector(source):
        _prepend_path(os.path.dirname(source))
        return
    if os.path.abspath(source) == os.path.abspath(dest):
        _prepend_path(os.path.dirname(source))
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.lexists(dest):
        os.remove(dest)
    # macOS registration is a symlink into the app bundle. Linux copies, because a
    # symlink into an AppImage or other temporary install directory does not survive.
    if sys.platform == "darwin":
        try:
            os.symlink(source, dest)
            return
        except OSError:
            pass
    shutil.copy2(source, dest)
    if os.name != "nt":
        os.chmod(dest, 0o755)


def _locate_binary(spec: CliInstallSpec) -> str | None:
    return shutil.which(spec.binary)


def locate_obsidian_binary(explicit: str | None = None) -> str:
    """Resolve the Obsidian CLI binary for an instance or host status check."""
    ensure_cli_path()
    path = str(explicit or "").strip()
    if path:
        if not os.path.isfile(path):
            raise ValueError(OBSIDIAN_CLI_MISSING)
        return path
    found = shutil.which("obsidian")
    if found:
        return found
    bundled = _find_obsidian_bundle()
    if bundled:
        return bundled
    raise ValueError(OBSIDIAN_CLI_MISSING)


def cli_install_status(kind: str) -> dict[str, Any]:
    ensure_cli_path()
    spec = get_cli_install_spec(kind)
    if spec is None:
        raise ValueError(f"kind {kind!r} does not support CLI install")
    path = _locate_binary(spec)
    version = _read_version(path) if path else None
    install_command = spec.install_command
    if spec.kind == "obsidian-cli":
        install_command = obsidian_install_command()
    return {
        "kind": kind,
        "binary": spec.binary,
        "npm_package": spec.npm_package or "",
        "install_command": install_command,
        "doc_url": spec.doc_url,
        "guide_url": spec.guide_url,
        "installed": bool(path),
        "binary_path": path,
        "version": version,
    }


def _install_obsidian_cli(status: dict[str, Any]) -> dict[str, Any]:
    """Register the CLI bundled in the Obsidian app onto PATH. Never raises."""
    if status["installed"]:
        return {"ok": True, "already_installed": True, **status}
    source = _find_obsidian_bundle()
    dest = _obsidian_install_destination(source)
    command = obsidian_install_command(source, dest)
    status = {**status, "install_command": command}
    if not source:
        return _fail(
            status,
            "未找到 Obsidian 应用内的 CLI。"
            "请先安装 Obsidian 1.12.7 及以上，并在设置 → 通用中启用 Command line interface。"
            f"也可在主机手动执行：{command}",
        )
    try:
        _place_obsidian_binary(source, dest)
        ensure_cli_path()
    except OSError as exc:
        return _fail(status, f"安装失败：{exc}。请在主机手动执行：{command}")
    refreshed = cli_install_status("obsidian-cli")
    refreshed = {**refreshed, "install_command": command}
    if not refreshed["installed"]:
        return _fail(
            refreshed,
            f"CLI 已注册，但 PATH 中仍找不到 obsidian。请在主机手动执行：{command}",
        )
    return {"ok": True, "already_installed": False, **refreshed}


def install_connector_cli(kind: str) -> dict[str, Any]:
    """Ensure the host CLI is installed. Never raises for install failure — returns ok=False."""
    status = cli_install_status(kind)
    spec = get_cli_install_spec(kind)
    if spec is not None and spec.kind == "obsidian-cli":
        return _install_obsidian_cli(status)
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
