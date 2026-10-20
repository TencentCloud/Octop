"""Tests for octop_browser.install (Playwright Chromium installer)."""

from __future__ import annotations

from typing import Any

import pytest

from octop_browser import install as install_mod
from octop_browser.install import (
    chromium_executable,
    ensure_chromium,
    install_chromium_stream,
)
from octop_browser.playwright_download import DownloadCandidate


@pytest.fixture(autouse=True)
def _skip_cdn_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep install tests offline; CDN race is covered in test_playwright_download."""
    monkeypatch.setattr(
        install_mod, "race_download_sources", lambda cands, **_kw: list(cands)
    )
    monkeypatch.setattr(
        install_mod,
        "build_download_candidates",
        lambda: [
            DownloadCandidate(
                kind="npmmirror", host="http://mirror", probe_url="http://mirror"
            ),
            DownloadCandidate(kind="official", host="", probe_url="http://official"),
        ],
    )


# ---------------------------------------------------------------------------
# chromium_executable / ensure_chromium (sync)
# ---------------------------------------------------------------------------


def test_chromium_executable_delegates_to_launcher(monkeypatch):
    """chromium_executable() forwards to the launcher's lookup."""
    monkeypatch.setattr(
        install_mod, "_find_playwright_chromium", lambda: "/path/to/chrome"
    )
    assert chromium_executable() == "/path/to/chrome"


def test_ensure_chromium_short_circuits_when_installed(monkeypatch):
    """If a binary already exists and verifies, return True without subprocess."""
    monkeypatch.setattr(
        install_mod, "_find_playwright_chromium", lambda: "/path/to/chrome"
    )
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))
    called = {"run": False}

    def fake_run(*_a, **_kw):
        called["run"] = True
        raise AssertionError("subprocess.run must not be called when already installed")

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is True
    assert called["run"] is False


def test_ensure_chromium_reports_missing_playwright_when_skip(monkeypatch, capsys):
    """If playwright is missing AND skip-pip is set, fail fast with a clear message."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: False)
    monkeypatch.setenv("OCTOP_SKIP_PLAYWRIGHT_PIP", "1")
    assert ensure_chromium(quiet=False) is False
    err = capsys.readouterr().err
    assert "Playwright is not installed" in err


def test_ensure_chromium_pip_then_install(monkeypatch):
    """Missing playwright triggers pip install, then the playwright installer."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.delenv("OCTOP_SKIP_PLAYWRIGHT_PIP", raising=False)
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)

    avail = {"flag": False}

    def avail_fn():
        return avail["flag"]

    monkeypatch.setattr(install_mod, "_playwright_available", avail_fn)
    # install-deps is a best-effort, Linux-only step; verification is covered
    # by its own tests. Stub both so this test stays platform-independent.
    monkeypatch.setattr(install_mod, "_run_install_deps", lambda *, quiet=True: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))

    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        if "pip" in cmd or cmd[:2] == ["uv", "pip"]:
            avail["flag"] = True
        return _Result()

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is True
    assert len(calls) == 2
    assert calls[0][-1] == "playwright"
    assert calls[1][-3:] == ["playwright", "install", "chromium"]


def test_ensure_chromium_pip_failure_aborts(monkeypatch):
    """If pip install fails, ensure_chromium returns False without running playwright."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: False)
    monkeypatch.delenv("OCTOP_SKIP_PLAYWRIGHT_PIP", raising=False)

    calls: list[list[str]] = []

    class _Result:
        returncode = 1

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is False
    assert len(calls) == 1  # only pip ran; playwright never invoked


def test_ensure_chromium_invokes_subprocess(monkeypatch):
    """When Chromium is missing but playwright is present, run the installer."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(install_mod, "_run_install_deps", lambda *, quiet=True: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))

    captured: dict[str, Any] = {}

    class _Result:
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is True
    assert "playwright" in captured["cmd"]
    assert captured["cmd"][-2:] == ["install", "chromium"]
    env = captured["kwargs"].get("env") or {}
    assert env.get("PLAYWRIGHT_DOWNLOAD_HOST") == "http://mirror"


def test_ensure_chromium_falls_back_to_next_source(monkeypatch):
    """If the fastest host fails, keep going until a later candidate succeeds."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(install_mod, "_run_install_deps", lambda *, quiet=True: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))

    hosts: list[str] = []

    class _Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, **kwargs):
        host = (kwargs.get("env") or {}).get("PLAYWRIGHT_DOWNLOAD_HOST", "")
        hosts.append(host)
        return _Result(1 if host else 0)

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is True
    assert hosts == ["http://mirror", ""]


def test_ensure_chromium_returns_false_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)

    class _Result:
        returncode = 1

    monkeypatch.setattr(install_mod.subprocess, "run", lambda *a, **kw: _Result())
    assert ensure_chromium(quiet=True) is False


def test_ensure_chromium_handles_missing_python(monkeypatch):
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)

    def fake_run(*a, **kw):
        raise FileNotFoundError("python")

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert ensure_chromium(quiet=True) is False


def test_run_install_deps_uses_dnf_when_no_apt(monkeypatch):
    """Sync installer must not invoke playwright install-deps on RPM hosts."""
    monkeypatch.setattr(install_mod.sys, "platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert install_mod._run_install_deps(quiet=True) is True
    # 1 library batch + the first CJK font package; once a font installs the
    # remaining font candidates are skipped (fonts_ok short-circuits).
    assert len(calls) == 2
    assert calls[0][:3] == ["dnf", "install", "-y"]
    assert "at-spi2-atk" in calls[0]
    assert "playwright" not in calls[0]
    assert calls[1] == ["dnf", "install", "-y", "google-noto-sans-cjk-ttc-fonts"]
    assert "--skip-unavailable" not in calls[1]


def test_run_install_deps_ignores_font_failure(monkeypatch):
    """CJK fonts are best-effort; a missing font package must not fail deps."""
    monkeypatch.setattr(install_mod.sys, "platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    class _Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(cmd, **_kw):
        if any("noto" in part or "wqy" in part for part in cmd):
            return _Result(1)
        return _Result(0)

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert install_mod._run_install_deps(quiet=True) is True


def test_run_install_deps_apt_runs_fonts_after_playwright(monkeypatch):
    """Playwright install-deps success must still try CJK fonts."""
    monkeypatch.setattr(install_mod.sys, "platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )

    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        return _Result()

    monkeypatch.setattr(install_mod.subprocess, "run", fake_run)
    assert install_mod._run_install_deps(quiet=True) is True
    assert calls[0][-2:] == ["install-deps", "chromium"]
    # Native apt library fallback is skipped after Playwright succeeds.
    assert not any(
        "libatk-bridge2.0-0" in cmd and "fonts-noto-cjk" not in cmd for cmd in calls
    )
    assert any("fonts-noto-cjk" in cmd for cmd in calls)


def test_verify_chromium_hint_uses_native_manager(monkeypatch):
    monkeypatch.setattr(install_mod, "chromium_executable", lambda: "/chrome")
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    class _Result:
        returncode = 127
        stdout = ""
        stderr = (
            "error while loading shared libraries: libatk-bridge-2.0.so.0: "
            "cannot open shared object file"
        )

    monkeypatch.setattr(install_mod.subprocess, "run", lambda *_a, **_kw: _Result())
    ok, msg = install_mod.verify_chromium()
    assert ok is False
    assert "libatk-bridge-2.0.so.0" in msg
    assert "sudo dnf install" in msg
    assert "playwright install-deps" not in msg


# ---------------------------------------------------------------------------
# install_chromium_stream (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_stream_short_circuits_when_installed(monkeypatch):
    """Stream emits a single log + done(success=True) when binary exists."""
    monkeypatch.setattr(
        install_mod, "_find_playwright_chromium", lambda: "/path/to/chrome"
    )
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))
    events = [e async for e in install_chromium_stream()]
    assert any("already installed" in e.get("log", "") for e in events)
    assert events[-1] == {"done": True, "success": True}


@pytest.mark.asyncio
async def test_install_stream_reports_missing_playwright_when_skip(monkeypatch):
    """When skip-pip is set and playwright is missing, fail with a clear message."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: False)
    monkeypatch.setenv("OCTOP_SKIP_PLAYWRIGHT_PIP", "1")
    events = [e async for e in install_chromium_stream()]
    assert events[0].get("error", "").startswith("Playwright is not installed")
    final = events[-1]
    assert final["done"] is True and final["success"] is False
    assert "Playwright is not installed" in final["error"]


@pytest.mark.asyncio
async def test_install_stream_pip_then_install(monkeypatch):
    """Missing playwright -> two streamed subprocesses (pip, then playwright)."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.delenv("OCTOP_SKIP_PLAYWRIGHT_PIP", raising=False)
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)

    avail = {"flag": False}
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: avail["flag"])
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))

    invoked: list[list[str]] = []

    async def fake_stream(cmd, *, is_disconnected, env=None):
        invoked.append(list(cmd))
        if "pip" in cmd:
            avail["flag"] = True  # simulate pip succeeding
            yield {"log": f"installed playwright via {cmd[2]}"}
            yield {"done": True, "success": True}
        else:
            yield {"log": "Downloading Chromium..."}
            yield {"done": True, "success": True}

    monkeypatch.setattr(install_mod, "_stream_subprocess", fake_stream)

    events = [e async for e in install_chromium_stream()]
    logs = [e["log"] for e in events if "log" in e]
    assert any("Installing playwright package" in line for line in logs)
    assert any("Downloading Chromium" in line for line in logs)
    assert any("Verifying installation" in line for line in logs)
    assert events[-1] == {"done": True, "success": True}
    # pip bootstrap, then the Chromium download. install-deps is appended on
    # Linux only, so assert on the leading steps rather than the total count.
    assert invoked[0][-1] == "playwright"
    assert invoked[1][-3:] == ["playwright", "install", "chromium"]


@pytest.mark.asyncio
async def test_install_stream_pip_failure_aborts(monkeypatch):
    """If pip install fails, the stream emits a terminal failure and stops."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: False)
    monkeypatch.delenv("OCTOP_SKIP_PLAYWRIGHT_PIP", raising=False)

    invoked: list[list[str]] = []

    async def fake_stream(cmd, *, is_disconnected, env=None):
        invoked.append(list(cmd))
        yield {"log": "pip error"}
        yield {"done": True, "success": False, "error": "pip rc=1"}

    monkeypatch.setattr(install_mod, "_stream_subprocess", fake_stream)

    events = [e async for e in install_chromium_stream()]
    final = events[-1]
    assert final["done"] is True and final["success"] is False
    assert "pip rc=1" in final["error"]
    assert len(invoked) == 1  # second step never ran


@pytest.mark.asyncio
async def test_install_stream_falls_back_to_next_source(monkeypatch):
    """If the first CDN fails, the stream retries the next ranked host."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))
    hosts: list[str | None] = []

    async def fake_stream(cmd, *, is_disconnected, env=None):
        if cmd[-3:] == ["playwright", "install", "chromium"]:
            host = None if env is None else env.get("PLAYWRIGHT_DOWNLOAD_HOST")
            hosts.append(host)
            if host:
                yield {"log": "mirror failed"}
                yield {"done": True, "success": False}
                return
            yield {"log": "official ok"}
            yield {"done": True, "success": True}
            return
        yield {"done": True, "success": True}

    monkeypatch.setattr(install_mod, "_stream_subprocess", fake_stream)
    events = [e async for e in install_chromium_stream()]
    assert events[-1] == {"done": True, "success": True}
    assert hosts == ["http://mirror", None]
    logs = [e["log"] for e in events if "log" in e]
    assert any("trying next source" in line for line in logs)


@pytest.mark.asyncio
async def test_install_stream_uses_dnf_when_apt_missing(monkeypatch):
    """On RPM hosts, skip playwright install-deps (it only knows apt-get)."""
    monkeypatch.setattr(install_mod.sys, "platform", "linux")
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))
    monkeypatch.setattr(install_mod.os, "geteuid", lambda: 0)

    def fake_which(name: str) -> str | None:
        if name == "dnf":
            return "/usr/bin/dnf"
        return None

    monkeypatch.setattr("octop_browser.linux_deps.shutil.which", fake_which)
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)

    invoked: list[list[str]] = []

    async def fake_stream(cmd, *, is_disconnected, env=None):
        invoked.append(list(cmd))
        yield {"done": True, "success": True}

    monkeypatch.setattr(install_mod, "_stream_subprocess", fake_stream)
    events = [e async for e in install_chromium_stream()]
    assert events[-1] == {"done": True, "success": True}
    assert any(c[:3] == ["dnf", "install", "-y"] for c in invoked)
    assert any("google-noto-sans-cjk-ttc-fonts" in c for c in invoked)
    assert not any(c[-2:] == ["install-deps", "chromium"] for c in invoked)
    logs = [e["log"] for e in events if "log" in e]
    assert any("via dnf" in line for line in logs)


@pytest.mark.asyncio
async def test_install_stream_native_hint_when_deps_fail(monkeypatch):
    """Failed system-deps must not claim 'elevated privileges' on dnf hosts."""
    monkeypatch.setattr(install_mod.sys, "platform", "linux")
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(
        install_mod,
        "verify_chromium",
        lambda: (False, "missing system library: libatk-bridge-2.0.so.0"),
    )
    monkeypatch.setattr("octop_browser.linux_deps.sys.platform", "linux")
    monkeypatch.setattr("octop_browser.linux_deps.os.geteuid", lambda: 0)
    monkeypatch.setattr(
        "octop_browser.linux_deps.shutil.which",
        lambda name: "/usr/bin/dnf" if name == "dnf" else None,
    )

    async def fake_stream(cmd, *, is_disconnected, env=None):
        if cmd[:1] == ["dnf"]:
            yield {"log": "sh: apt-get: command not found"}
            yield {"done": True, "success": False}
            return
        yield {"done": True, "success": True}

    monkeypatch.setattr(install_mod, "_stream_subprocess", fake_stream)
    events = [e async for e in install_chromium_stream()]
    logs = [e.get("log", "") + e.get("error", "") for e in events]
    joined = "\n".join(logs)
    assert "elevated privileges" not in joined
    assert "sudo dnf install" in joined
    assert events[-1]["done"] is True
    assert events[-1]["success"] is False


@pytest.mark.asyncio
async def test_install_stream_runs_subprocess(monkeypatch):
    """Happy path: yield logs from the subprocess, then done(success=True)."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)
    monkeypatch.setattr(install_mod, "verify_chromium", lambda: (True, "chrome 120"))

    lines = [b"Downloading Chromium...\n", b"Done.\n", b""]

    class FakeStdout:
        def __init__(self, lines):
            self._lines = list(lines)

        async def readline(self):
            return self._lines.pop(0) if self._lines else b""

    class FakeProc:
        def __init__(self):
            # Fresh stdout per process: the pipeline may spawn more than one
            # subprocess (download, then install-deps on Linux).
            self.stdout = FakeStdout(lines)

        def kill(self):
            pass

        async def wait(self):
            return 0

    async def fake_create(*_a, **_kw):
        return FakeProc()

    monkeypatch.setattr(install_mod.asyncio, "create_subprocess_exec", fake_create)

    events = [e async for e in install_chromium_stream()]
    logs = [e["log"] for e in events if "log" in e]
    assert "Downloading Chromium..." in logs
    assert "Done." in logs
    assert events[-1] == {"done": True, "success": True}


@pytest.mark.asyncio
async def test_install_stream_disconnect_kills_proc(monkeypatch):
    """When is_disconnected returns True, the subprocess is killed and stream ends."""
    monkeypatch.setattr(install_mod, "_find_playwright_chromium", lambda: None)
    monkeypatch.setattr(install_mod, "_playwright_available", lambda: True)

    killed = {"v": False}

    class FakeStdout:
        async def readline(self):
            return b"slow line\n"

    class FakeProc:
        stdout = FakeStdout()

        def kill(self):
            killed["v"] = True

        async def wait(self):
            return 130  # killed

    async def fake_create(*_a, **_kw):
        return FakeProc()

    monkeypatch.setattr(install_mod.asyncio, "create_subprocess_exec", fake_create)

    # Disconnect after the first iteration
    state = {"calls": 0}

    def disc():
        state["calls"] += 1
        return state["calls"] >= 2

    events = []
    async for e in install_chromium_stream(is_disconnected=disc):
        events.append(e)
        if len(events) > 5:
            break  # safety net
    assert killed["v"] is True


@pytest.mark.asyncio
async def test_stream_subprocess_disables_cli_color(monkeypatch):
    """Playwright child processes get NO_COLOR so they do not emit SGR."""

    class FakeStdout:
        def __init__(self) -> None:
            self._lines = [b"linux64.zip\n", b""]

        async def readline(self) -> bytes:
            return self._lines.pop(0)

    class FakeProc:
        stdout = FakeStdout()

        def kill(self) -> None:
            return None

        async def wait(self) -> int:
            return 0

    captured: dict[str, object] = {}

    async def fake_create(*_a: object, **_kw: object) -> FakeProc:
        captured["env"] = _kw.get("env")
        return FakeProc()

    monkeypatch.setattr(install_mod.asyncio, "create_subprocess_exec", fake_create)
    events = [
        e async for e in install_mod._stream_subprocess(["pw"], is_disconnected=None)
    ]
    logs = [e["log"] for e in events if "log" in e]
    assert logs == ["linux64.zip"]
    assert events[-1] == {"done": True, "success": True}
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["NO_COLOR"] == "1"
    assert env["FORCE_COLOR"] == "0"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_install_browser_already_installed(monkeypatch, capsys):
    from octop_browser import cli as cli_mod

    monkeypatch.setattr(cli_mod, "chromium_executable", lambda: "/path/to/chrome")
    rc = cli_mod.main(["install-browser"])
    assert rc == 0
    assert "/path/to/chrome" in capsys.readouterr().out


def test_cli_install_browser_invokes_ensure(monkeypatch):
    from octop_browser import cli as cli_mod

    monkeypatch.setattr(cli_mod, "chromium_executable", lambda: None)
    captured = {"called": False, "quiet": None}

    def fake_ensure(quiet: bool) -> bool:
        captured["called"] = True
        captured["quiet"] = quiet
        return True

    monkeypatch.setattr(cli_mod, "ensure_chromium", fake_ensure)
    assert cli_mod.main(["install-browser", "--quiet"]) == 0
    assert captured == {"called": True, "quiet": True}


def test_cli_install_browser_failure_returns_one(monkeypatch):
    from octop_browser import cli as cli_mod

    monkeypatch.setattr(cli_mod, "chromium_executable", lambda: None)
    monkeypatch.setattr(cli_mod, "ensure_chromium", lambda quiet: False)
    assert cli_mod.main(["install-browser"]) == 1


def test_cli_no_subcommand_errors(capsys):
    from octop_browser import cli as cli_mod

    with pytest.raises(SystemExit):
        cli_mod.main([])


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_install_browser_tool_returns_summary(monkeypatch):
    from octop_browser import mcp_server

    async def fake_stream():
        yield {"log": "downloading"}
        yield {"log": "done"}
        yield {"done": True, "success": True}

    monkeypatch.setattr(mcp_server, "install_chromium_stream", lambda: fake_stream())
    out = await mcp_server._handle_install_browser()
    assert len(out) == 1
    text = out[0].text
    assert text.startswith("OK")
    assert "downloading" in text and "done" in text


@pytest.mark.asyncio
async def test_mcp_install_browser_tool_reports_failure(monkeypatch):
    from octop_browser import mcp_server

    async def fake_stream():
        yield {"log": "boom"}
        yield {"done": True, "success": False, "error": "not installed"}

    monkeypatch.setattr(mcp_server, "install_chromium_stream", lambda: fake_stream())
    out = await mcp_server._handle_install_browser()
    text = out[0].text
    assert text.startswith("FAILED: not installed")
    assert "boom" in text


def test_mcp_tool_listed():
    """install_browser must be advertised in the MCP tool list."""
    from octop_browser.mcp_server import _TOOLS

    names = [t.name for t in _TOOLS]
    assert "install_browser" in names
    assert "browser_record_list" in names
    assert "browser_record_show" in names


def test_mcp_fill_and_type_accept_selector():
    """MCP schema should match CLI/browser_tool selector support."""
    from octop_browser.mcp_server import _TOOLS

    schemas = {t.name: t.inputSchema for t in _TOOLS}
    assert "selector" in schemas["browser_fill"]["properties"]
    assert "selector" in schemas["browser_type"]["properties"]


@pytest.mark.asyncio
async def test_mcp_record_show_uses_recording_store(monkeypatch):
    from octop_browser import mcp_server

    class FakeStore:
        def recording_summary(self, recording_id: str):
            return {"recordingId": recording_id, "status": "stopped", "steps": 1}

    monkeypatch.setattr(mcp_server, "RecordingStore", FakeStore)

    out = await mcp_server.call_tool(
        "browser_record_show", {"recording_id": "rec_demo"}
    )

    assert len(out) == 1
    assert "rec_demo" in out[0].text
    assert "stopped" in out[0].text


@pytest.mark.asyncio
async def test_mcp_record_list_uses_recording_store(monkeypatch):
    from types import SimpleNamespace

    from octop_browser import mcp_server

    class FakeManifest(SimpleNamespace):
        def model_dump(self, mode: str = "json", by_alias: bool = True):
            return {"recordingId": self.recording_id, "status": "stopped"}

    class FakeStore:
        def list_recordings(self):
            return [FakeManifest(recording_id="rec_demo")]

    monkeypatch.setattr(mcp_server, "RecordingStore", FakeStore)

    out = await mcp_server.call_tool("browser_record_list", {})

    assert len(out) == 1
    assert "rec_demo" in out[0].text
    assert "recordings" in out[0].text
