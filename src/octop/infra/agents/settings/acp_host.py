"""Detect and best-effort install ACP CLIs on the Octop host.

Mirrors :mod:`octop.infra.utils.docker_env`: never raise for a missing binary.
Return a status payload the dashboard can show with an install script and an
agent prompt. A successful probe means the process answered ACP ``initialize``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from octop.infra.agents.settings.acp import host_runner_argv

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_SEC = 180
_PROBE_TIMEOUT_SEC = 20
_NPX_PROBE_TIMEOUT_SEC = 50
_ASK_TIMEOUT_SEC = 90
_ASK_PROMPT = "who are you?"

_PLATFORMS = ("linux", "darwin", "win32")


@dataclass(frozen=True)
class _PlatformScript:
    script: str
    auto: bool


@dataclass(frozen=True)
class _RunnerSpec:
    command: str
    args: tuple[str, ...]
    requires: tuple[str, ...]
    docs_url: str
    label_zh: str
    label_en: str
    scripts: dict[str, _PlatformScript]


def _posix(script: str, *, auto: bool = True) -> _PlatformScript:
    return _PlatformScript(script=script, auto=auto)


def _win(script: str, *, auto: bool = True) -> _PlatformScript:
    return _PlatformScript(script=script, auto=auto)


_CATALOG: dict[str, _RunnerSpec] = {
    "opencode": _RunnerSpec(
        command="opencode",
        args=("acp",),
        requires=(),
        docs_url="https://opencode.ai/docs",
        label_zh="OpenCode",
        label_en="OpenCode",
        scripts={
            "linux": _posix("curl -fsSL https://opencode.ai/v2/install | bash"),
            "darwin": _posix("curl -fsSL https://opencode.ai/v2/install | bash"),
            "win32": _win(
                "# OpenCode 2 has no PowerShell installer.\n"
                "# Install inside WSL:\n"
                "#   curl -fsSL https://opencode.ai/v2/install | bash\n"
                "# Or download the Windows zip from\n"
                "# https://github.com/anomalyco/opencode/releases\n"
                "# and put opencode.exe on PATH.",
                auto=False,
            ),
        },
    ),
    "codebuddy": _RunnerSpec(
        command="codebuddy",
        args=("--acp",),
        requires=(),
        docs_url="https://www.codebuddy.cn/docs/cli/installation",
        label_zh="CodeBuddy",
        label_en="CodeBuddy",
        scripts={
            "linux": _posix("curl -fsSL https://www.codebuddy.cn/cli/install.sh | bash"),
            "darwin": _posix("curl -fsSL https://www.codebuddy.cn/cli/install.sh | bash"),
            "win32": _win("irm https://www.codebuddy.cn/cli/install.ps1 | iex"),
        },
    ),
    "claude_code": _RunnerSpec(
        command="npx",
        args=("-y", "@zed-industries/claude-agent-acp"),
        requires=("claude",),
        docs_url="https://code.claude.com/docs/en/setup",
        label_zh="Claude Code",
        label_en="Claude Code",
        scripts={
            "linux": _posix(
                "curl -fsSL https://claude.ai/install.sh | bash\n"
                "# ACP starts with: npx -y @zed-industries/claude-agent-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "darwin": _posix(
                "curl -fsSL https://claude.ai/install.sh | bash\n"
                "# ACP starts with: npx -y @zed-industries/claude-agent-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "win32": _win(
                "irm https://claude.ai/install.ps1 | iex\n"
                "# ACP starts with: npx -y @zed-industries/claude-agent-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
        },
    ),
    "codex": _RunnerSpec(
        command="npx",
        args=("-y", "@zed-industries/codex-acp"),
        requires=("codex",),
        docs_url="https://developers.openai.com/codex/cli",
        label_zh="Codex",
        label_en="Codex",
        scripts={
            "linux": _posix(
                "curl -fsSL https://chatgpt.com/codex/install.sh | sh\n"
                "# ACP starts with: npx -y @zed-industries/codex-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "darwin": _posix(
                "curl -fsSL https://chatgpt.com/codex/install.sh | sh\n"
                "# ACP starts with: npx -y @zed-industries/codex-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "win32": _win(
                "irm https://chatgpt.com/codex/install.ps1 | iex\n"
                "# ACP starts with: npx -y @zed-industries/codex-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
        },
    ),
    "kimi_code": _RunnerSpec(
        command="kimi",
        args=("acp",),
        requires=(),
        docs_url="https://www.kimi.com/code/docs/en/kimi-code-cli/guides/getting-started.html",
        label_zh="Kimi Code",
        label_en="Kimi Code",
        scripts={
            "linux": _posix("curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash"),
            "darwin": _posix("curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash"),
            "win32": _win("irm https://code.kimi.com/kimi-code/install.ps1 | iex"),
        },
    ),
    "cursor_cli": _RunnerSpec(
        command="agent",
        args=("acp",),
        requires=(),
        docs_url="https://cursor.com/docs/cli/installation",
        label_zh="Cursor CLI",
        label_en="Cursor CLI",
        scripts={
            "linux": _posix("curl https://cursor.com/install -fsS | bash"),
            "darwin": _posix("curl https://cursor.com/install -fsS | bash"),
            "win32": _win("irm 'https://cursor.com/install?win32=true' | iex"),
        },
    ),
    "pi": _RunnerSpec(
        command="npx",
        args=("-y", "pi-acp"),
        requires=("pi",),
        docs_url="https://pi.dev/docs/latest/quickstart",
        label_zh="Pi",
        label_en="Pi",
        scripts={
            "linux": _posix(
                "curl -fsSL https://pi.dev/install.sh | sh\n"
                "# ACP starts with: npx -y pi-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "darwin": _posix(
                "curl -fsSL https://pi.dev/install.sh | sh\n"
                "# ACP starts with: npx -y pi-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
            "win32": _win(
                "irm https://pi.dev/install.ps1 | iex\n"
                "# ACP starts with: npx -y pi-acp\n"
                "# Install Node.js if npx is not on PATH."
            ),
        },
    ),
    "qwen_code": _RunnerSpec(
        command="qwen",
        args=("--acp",),
        requires=(),
        docs_url="https://github.com/QwenLM/qwen-code",
        label_zh="Qwen Code",
        label_en="Qwen Code",
        scripts={
            "linux": _posix(
                "npm install -g @qwen-code/qwen-code@latest\n"
                "# Requires Node.js 20+. Install Node.js if npm is not on PATH."
            ),
            "darwin": _posix(
                "npm install -g @qwen-code/qwen-code@latest\n"
                "# Requires Node.js 20+. Install Node.js if npm is not on PATH."
            ),
            "win32": _win(
                "npm install -g @qwen-code/qwen-code@latest\n"
                "# Requires Node.js 20+. Install Node.js if npm is not on PATH."
            ),
        },
    ),
}


def _platform_key() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "win32"
    return sys.platform


def _host_env(extra: dict[str, str] | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if isinstance(value, str)}
    if extra:
        env.update({str(key): str(value) for key, value in extra.items()})
    home = Path.home()
    candidates = (
        home / ".local" / "bin",
        home / ".opencode" / "bin",
        home / ".claude" / "bin",
        home / ".codebuddy" / "bin",
        home / ".kimi" / "bin",
        home / ".pi" / "bin",
        home / "bin",
        home / ".cursor" / "bin",
        home / "AppData" / "Local" / "codebuddy" / "bin",
        home / "AppData" / "Local" / "cursor-agent",
    )
    existing = [str(path) for path in candidates if path.is_dir()]
    if existing:
        env["PATH"] = os.pathsep.join(existing) + os.pathsep + env.get("PATH", "")
    return env


def _which(name: str, env: dict[str, str]) -> str | None:
    if not name:
        return None
    if os.path.isabs(name) or "/" in name or "\\" in name:
        return name if os.path.isfile(name) else None
    return shutil.which(name, path=env.get("PATH"))


def _shell_ok(plat: str) -> bool:
    if plat == "win32":
        return shutil.which("powershell") is not None or shutil.which("pwsh") is not None
    return shutil.which("bash") is not None or shutil.which("sh") is not None


def _resolve_launch(
    spec: _RunnerSpec | None,
    *,
    command: str,
    args: list[str] | None,
) -> tuple[str, list[str]]:
    if command.strip():
        return command.strip(), [str(item) for item in (args or [])]
    if spec is None:
        return "", []
    return spec.command, list(spec.args)


def _missing_binary(
    *,
    command: str,
    spec: _RunnerSpec | None,
    env: dict[str, str],
) -> str | None:
    if not command:
        return "command_missing"
    if _which(command, env) is None:
        leaf = Path(command).name.lower()
        if leaf in {"npx", "npx.cmd", "npm", "npm.cmd"}:
            return "node_missing"
        return "command_missing"
    if spec is not None:
        for required in spec.requires:
            if _which(required, env) is None:
                return "agent_missing"
    return None


def _run_install(script: str, plat: str) -> tuple[bool, str]:
    line = "\n".join(
        part for part in script.splitlines() if part.strip() and not part.strip().startswith("#")
    ).strip()
    if not line:
        return False, "no_installer"
    env = _host_env(None)
    if plat == "win32":
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if exe is None:
            return False, "powershell_missing"
        argv = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", line]
    else:
        exe = shutil.which("bash") or shutil.which("sh")
        if exe is None:
            return False, "shell_missing"
        argv = [exe, "-c", line]
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_INSTALL_TIMEOUT_SEC,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ACP install timed out")
        return False, "install_timeout"
    except OSError as exc:
        logger.warning("ACP install failed to start: %s", exc)
        return False, "install_failed"
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        logger.warning("ACP install exited %s: %s", result.returncode, stderr[:300])
        return False, stderr[:300] or "install_failed"
    return True, ""


def _kill_process(pid: int) -> None:
    try:
        import psutil
    except ImportError:
        os.kill(pid, signal.SIGTERM)
        return
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for child in parent.children(recursive=True):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            continue
    try:
        parent.kill()
    except psutil.NoSuchProcess:
        return


class _ProbeClient:
    """ACP client for initialize and a single probe prompt."""

    def __init__(self) -> None:
        self.text = ""

    def on_connect(self, conn: Any) -> None:
        _ = conn

    async def request_permission(self, *_args: Any, **_kwargs: Any) -> Any:
        from acp.schema import DeniedOutcome, RequestPermissionResponse

        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, *_args: Any, **kwargs: Any) -> None:
        update = kwargs.get("update")
        if update is None and len(_args) >= 2:
            update = _args[1]
        from acp.schema import AgentMessageChunk

        if isinstance(update, AgentMessageChunk):
            _merge_text(self, _chunk_text(getattr(update, "content", None)))

    async def write_text_file(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def read_text_file(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"content": ""}

    async def create_terminal(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"terminalId": ""}

    async def terminal_output(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"output": "", "truncated": "false"}

    async def release_terminal(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def wait_for_terminal_exit(self, *_args: Any, **_kwargs: Any) -> dict[str, int]:
        return {"exitCode": 0}

    async def kill_terminal(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _ = method, params
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        _ = method, params


def _chunk_text(content: Any) -> str:
    if hasattr(content, "text") and isinstance(getattr(content, "text", None), str):
        return str(content.text)
    if isinstance(content, list):
        return "".join(_chunk_text(item) for item in content)
    if isinstance(content, dict) and content.get("type") == "text":
        return str(content.get("text") or "")
    return ""


def _merge_text(client: _ProbeClient, text: str) -> None:
    if not text or text == client.text:
        return
    if not client.text or text.startswith(client.text):
        client.text = text
        return
    client.text += text


async def _handshake(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.schema import ClientCapabilities, Implementation

    timeout = (
        _NPX_PROBE_TIMEOUT_SEC
        if Path(command).name.lower().startswith("npx")
        else _PROBE_TIMEOUT_SEC
    )
    command, args = host_runner_argv(command, args, env)
    try:
        async with asyncio.timeout(timeout):
            async with spawn_agent_process(
                cast(Any, _ProbeClient()),
                command,
                *args,
                cwd=str(Path.home()),
                env=env,
            ) as (conn, process):
                try:
                    initialized = await conn.initialize(
                        protocol_version=PROTOCOL_VERSION,
                        capabilities=ClientCapabilities(),
                        client_info=Implementation(name="octop-acp-probe", version="0.1.0"),
                    )
                finally:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int) and getattr(process, "returncode", None) is None:
                        _kill_process(pid)
                version = getattr(initialized, "protocol_version", None)
                if version != PROTOCOL_VERSION:
                    return False, f"protocol {version}"
                return True, ""
    except TimeoutError:
        return False, "timed out waiting for ACP initialize"
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        return False, text[:400]


async def _ask(command: str, args: list[str], env: dict[str, str]) -> tuple[bool, str]:
    """Open one ACP session, send a fixed prompt, and return the assistant text."""
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.schema import ClientCapabilities, Implementation, TextContentBlock

    client = _ProbeClient()
    command, args = host_runner_argv(command, args, env)
    try:
        async with asyncio.timeout(_ASK_TIMEOUT_SEC):
            async with spawn_agent_process(
                cast(Any, client),
                command,
                *args,
                cwd=str(Path.home()),
                env=env,
            ) as (conn, process):
                try:
                    initialized = await conn.initialize(
                        protocol_version=PROTOCOL_VERSION,
                        capabilities=ClientCapabilities(),
                        client_info=Implementation(name="octop-acp-probe", version="0.1.0"),
                    )
                    version = getattr(initialized, "protocol_version", None)
                    if version != PROTOCOL_VERSION:
                        return False, f"protocol {version}"
                    session = await conn.new_session(cwd=str(Path.home()))
                    await conn.prompt(
                        session_id=session.session_id,
                        prompt=[TextContentBlock(type="text", text=_ASK_PROMPT)],
                    )
                finally:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int) and getattr(process, "returncode", None) is None:
                        _kill_process(pid)
        text = client.text.strip()
        if not text:
            return False, "empty reply"
        return True, text[:4000]
    except TimeoutError:
        partial = client.text.strip()
        if partial:
            return True, partial[:4000]
        return False, "timed out waiting for ACP reply"
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        return False, text[:400]


def _label(spec: _RunnerSpec | None, runner: str, locale: str) -> str:
    if spec is None:
        return runner or "ACP"
    if locale.startswith("en"):
        return spec.label_en
    return spec.label_zh


def _scripts(spec: _RunnerSpec | None) -> dict[str, str]:
    if spec is None:
        return {}
    return {plat: spec.scripts[plat].script for plat in _PLATFORMS if plat in spec.scripts}


def _host_script(spec: _RunnerSpec | None, plat: str) -> str:
    if spec is None:
        return ""
    item = spec.scripts.get(plat)
    return "" if item is None else item.script


def _can_auto(spec: _RunnerSpec | None, plat: str, *, acp_ok: bool) -> bool:
    if spec is None or acp_ok:
        return False
    item = spec.scripts.get(plat)
    if item is None or not item.auto:
        return False
    return _shell_ok(plat)


def _agent_prompt(
    *,
    locale: str,
    status: str,
    plat: str,
    label: str,
    command: str,
    script: str,
    host: str,
) -> str:
    en = locale.startswith("en")
    plat_name = {"linux": "Linux", "darwin": "macOS", "win32": "Windows"}.get(plat, plat)
    if status in {"ready", "installed"}:
        if en:
            return (
                f"{label} answered ACP initialize on this machine ({host}). "
                "No further install is needed."
            )
        return f"本机的 {label} 已能通过 ACP initialize（系统：{host}）。无需再安装。"
    if not script:
        if en:
            return (
                f"Install `{command or label}` on the machine that runs Octop ({host}, {plat_name}) "
                "and confirm `ACP initialize` succeeds over stdio."
            )
        return (
            f"请在运行 Octop 的这台机器上安装 `{command or label}`（系统：{host}，{plat_name}），"
            "并确认它能通过 stdio 完成 ACP initialize。"
        )
    if en:
        return (
            f"Install {label} on this Octop host ({host}, {plat_name}) with:\n{script}\n"
            "Then confirm the configured command answers ACP initialize. "
            "Do not write tokens into the command."
        )
    return (
        f"请在运行 Octop 的这台机器上安装 {label}（系统：{host}，{plat_name}）。"
        f"使用下面的命令：\n{script}\n"
        "装好后确认当前启动命令能通过 ACP initialize。不要把密钥写进命令。"
    )


async def acp_host_status(
    *,
    runner: str,
    command: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    attempt_install: bool = False,
    locale: str = "zh",
) -> dict[str, Any]:
    """Probe one runner. When ``attempt_install`` is set, run the host installer first."""
    plat = _platform_key()
    spec = _CATALOG.get(runner.strip())
    launch, launch_args = _resolve_launch(spec, command=command, args=args)
    host_env = _host_env(env)
    label = _label(spec, runner.strip(), locale)
    script = _host_script(spec, plat)
    installed_now = False
    install_error = ""

    missing = _missing_binary(command=launch, spec=spec, env=host_env)
    auto = _can_auto(spec, plat, acp_ok=False) and missing is not None
    if attempt_install and auto and missing is not None:
        ok, install_error = await asyncio.to_thread(_run_install, script, plat)
        installed_now = ok
        host_env = _host_env(env)
        missing = _missing_binary(command=launch, spec=spec, env=host_env)

    acp_ok = False
    acp_detail = ""
    if missing is None and launch:
        acp_ok, acp_detail = await _handshake(launch, launch_args, host_env)

    if acp_ok and installed_now:
        status, reason, detail = "installed", "install_ok", ""
    elif acp_ok:
        status, reason, detail = "ready", "already_present", ""
    elif missing == "agent_missing":
        status, reason, detail = "missing", "agent_missing", ""
    elif missing in {"command_missing", "node_missing"}:
        if attempt_install and not auto:
            status, reason, detail = "skipped", "manual_install_required", ""
        elif attempt_install and installed_now:
            status, reason, detail = "degraded", "install_failed", "command still missing"
        elif attempt_install and install_error:
            status, reason, detail = "degraded", "install_failed", install_error
        else:
            status, reason, detail = "missing", missing, ""
    elif "timed out" in acp_detail:
        status, reason, detail = "degraded", "handshake_timeout", acp_detail
    else:
        status, reason, detail = "degraded", "handshake_failed", acp_detail

    return {
        "runner": runner.strip(),
        "platform": plat,
        "command": launch,
        "args": launch_args,
        "binary_found": missing is None,
        "acp_ok": acp_ok,
        "docs_url": "" if spec is None else spec.docs_url,
        "install_script": script,
        "scripts": _scripts(spec),
        "agent_prompt": _agent_prompt(
            locale=locale,
            status=status,
            plat=plat,
            label=label,
            command=launch,
            script=script,
            host=platform.platform(),
        ),
        "can_auto_install": _can_auto(spec, plat, acp_ok=acp_ok),
        "status": status,
        "reason": reason,
        "detail": detail,
    }


async def acp_host_ask(
    *,
    runner: str,
    command: str = "",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send ``who are you?`` to the runner and return the assistant text."""
    spec = _CATALOG.get(runner.strip())
    launch, launch_args = _resolve_launch(spec, command=command, args=args)
    host_env = _host_env(env)
    missing = _missing_binary(command=launch, spec=spec, env=host_env)
    if missing is not None or not launch:
        return {
            "ok": False,
            "prompt": _ASK_PROMPT,
            "text": "",
            "reason": missing or "command_missing",
            "detail": "",
            "command": launch,
        }
    ok, text = await _ask(launch, launch_args, host_env)
    if ok:
        return {
            "ok": True,
            "prompt": _ASK_PROMPT,
            "text": text,
            "reason": "ok",
            "detail": "",
            "command": launch,
        }
    reason = "handshake_timeout" if "timed out" in text else "handshake_failed"
    if text == "empty reply":
        reason = "empty_reply"
    return {
        "ok": False,
        "prompt": _ASK_PROMPT,
        "text": "",
        "reason": reason,
        "detail": "" if text == "empty reply" else text,
        "command": launch,
    }


__all__ = ["acp_host_ask", "acp_host_status"]
