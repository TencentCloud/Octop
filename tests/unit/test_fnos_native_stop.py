"""FnOS native stop must free 8089 so App Center checkport can start again."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash helpers")
# 飞牛停服务按 Linux 进程树实现。macOS 也是 posix，但没有 /proc，
# 读子进程和按树杀进程都会落空。
linux_proc = pytest.mark.skipif(
    not Path("/proc").is_dir(),
    reason="FnOS native stop walks /proc",
)

REPO = Path(__file__).resolve().parents[2]
COMMON_SH = REPO / "scripts" / "fnos" / "common.sh"
FNOS_NATIVE = REPO / "fnos" / "native"


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_until(predicate, *, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _listen_script(port: int) -> str:
    return (
        "import signal,socket,time;"
        "signal.signal(signal.SIGHUP,signal.SIG_IGN);"
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        f"s.bind(('127.0.0.1',{port}));s.listen(1);time.sleep(120)"
    )


def _start_wrapper_listener(port: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        ["bash", "-c", f"python3 -c {_listen_script(port)!r} & wait"],
    )


def _direct_children(pid: int) -> list[int]:
    path = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        return [int(x) for x in path.read_text(encoding="utf-8").split() if x.isdigit()]
    except OSError:
        return []


# pgrep/ss walk all of /proc; a crowded host (zombies, leftover suites) makes them stall.
# After sourcing common.sh, override tree-kill to read /proc/<pid>/task/<pid>/children.
_FAST_KILL_TREE = r"""
octop_kill_pid_tree() {
  local pid="${1:-}" sig="${2:-TERM}" child
  [ -n "$pid" ] || return 0
  if [ -r "/proc/${pid}/task/${pid}/children" ]; then
    for child in $(cat "/proc/${pid}/task/${pid}/children" 2>/dev/null || true); do
      octop_kill_pid_tree "$child" "$sig"
    done
  fi
  kill -s "$sig" "$pid" 2>/dev/null || true
}
"""


def _octop_native_user_exists() -> bool:
    return (
        subprocess.call(
            ["id", "octop-native"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        == 0
    )


def test_native_main_stop_releases_listen_port() -> None:
    text = (FNOS_NATIVE / "cmd" / "main").read_text(encoding="utf-8")
    assert "free_octop_ports" in text
    assert "octop_kill_pid_tree" in text
    assert "run_as_service_bg" in text
    assert "setsid" in text
    assert "_abort_start" in text
    assert "trap '_abort_start_and_exit'" in text
    assert "_abort_start_and_exit() {" in text
    abort_fn = text[
        text.index("_abort_start_and_exit() {") : text.index("trap '_abort_start_and_exit'")
    ]
    assert "exit 1" in abort_fn
    assert 'printf "%s" "$octop_pid" > "${PID_FILE}"' in text
    helpers = COMMON_SH.read_text(encoding="utf-8")
    assert "pgrep -P" in helpers
    assert "ss -ltnp" in helpers
    assert "pgrep -f -- 'octop.cli.main run'" in helpers
    assert "OCTOP_INSTALL_MODE=fpk-native" in helpers


def test_native_manifest_does_not_block_start_on_stale_port() -> None:
    text = (FNOS_NATIVE / "manifest").read_text(encoding="utf-8")
    assert "checkport=false" in text
    assert "service_port=8089" in text
    assert "ctl_stop=true" in text


@posix_only
def test_free_octop_ports_kills_listener(tmp_path: Path) -> None:
    port = _free_tcp_port()
    proc = subprocess.Popen(["python3", "-c", _listen_script(port)])
    try:
        assert _wait_until(lambda: _port_open(port)), f"listener did not bind {port}"
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
{_FAST_KILL_TREE}
export TRIM_APPDEST="{tmp_path / "no-such-octop-app"}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
octop_port_pids() {{ printf '%s' '{proc.pid}'; }}
octop_fpk_native_run_pids() {{ :; }}
free_octop_ports {port}
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=15)
        assert _wait_until(lambda: not _port_open(port)), f"port {port} still listening"
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


@linux_proc
def test_free_octop_ports_kills_orphan_child(tmp_path: Path) -> None:
    """Killing only the wrapper (old stop) leaves the listener; free_octop_ports must catch it."""
    port = _free_tcp_port()
    wrapper = _start_wrapper_listener(port)
    try:
        assert _wait_until(lambda: _port_open(port)), f"child did not bind {port}"
        children = _direct_children(wrapper.pid)
        assert children, "wrapper had no listener child"
        orphan_pid = children[0]
        wrapper.terminate()
        wrapper.wait(timeout=3)
        assert _port_open(port), "expected orphan listener to survive wrapper death"
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
{_FAST_KILL_TREE}
export TRIM_APPDEST="{tmp_path / "no-such-octop-app"}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
octop_port_pids() {{ printf '%s' '{orphan_pid}'; }}
octop_fpk_native_run_pids() {{ :; }}
free_octop_ports {port}
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=15)
        assert _wait_until(lambda: not _port_open(port)), f"orphan still listening on {port}"
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=3)


@linux_proc
def test_octop_kill_pid_tree_stops_child_listener() -> None:
    port = _free_tcp_port()
    wrapper = _start_wrapper_listener(port)
    try:
        assert _wait_until(lambda: _port_open(port)), f"child did not bind {port}"
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
{_FAST_KILL_TREE}
octop_kill_pid_tree {wrapper.pid} TERM
sleep 1
if kill -0 {wrapper.pid} 2>/dev/null; then
  octop_kill_pid_tree {wrapper.pid} KILL
fi
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=15)
        assert _wait_until(lambda: not _port_open(port)), f"child still listening on {port}"
        assert wrapper.poll() is not None
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=3)


@linux_proc
def test_native_main_stop_frees_port_after_wrapper_start(tmp_path: Path) -> None:
    if shutil.which("python3") is None:
        pytest.skip("python3 required")
    if _octop_native_user_exists() and os.geteuid() != 0:
        pytest.skip("octop-native 存在且当前非 root，runuser 后无法在测试里停掉服务")
    port = _free_tcp_port()
    appdest = tmp_path / "app"
    pkgvar = tmp_path / "var"
    data = tmp_path / "data"
    bindir = appdest / "bin"
    cmd = tmp_path / "cmd"
    bindir.mkdir(parents=True)
    pkgvar.mkdir()
    (data / ".octop").mkdir(parents=True)
    (data / ".octop" / "octop.db").write_text("", encoding="utf-8")
    cmd.mkdir()
    shutil.copy(FNOS_NATIVE / "cmd" / "main", cmd / "main")
    shutil.copy(COMMON_SH, cmd / "common.sh")
    (cmd / "main").chmod(0o755)
    # stop 末尾的 free_octop_ports 会跑 ss / pgrep -f；本用例只验证 pid 文件杀树后端口释放。
    with (cmd / "common.sh").open("a", encoding="utf-8") as fh:
        fh.write("\nfree_octop_ports() { return 0; }\n")
        fh.write(_FAST_KILL_TREE)
    launcher = bindir / "octop"
    launcher.write_text(
        "#!/bin/bash\n"
        'if [ "${1:-}" = "--prepare" ]; then exit 0; fi\n'
        "port=8089\n"
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in --port) port="$2"; shift 2 ;; *) shift ;; esac\n'
        "done\n"
        'python3 -c "import signal,socket,time;signal.signal(signal.SIGHUP,signal.SIG_IGN);'
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        "s.bind(('127.0.0.1',int('$port')));s.listen(1);time.sleep(120)\" &\n"
        "wait\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    env = {
        **os.environ,
        "TRIM_APPDEST": str(appdest),
        "TRIM_PKGVAR": str(pkgvar),
        "TRIM_DATA_SHARE_PATHS": str(data),
        "TRIM_TEMP_LOGFILE": str(pkgvar / "appcenter.log"),
        "OCTOP_PORT": str(port),
        "OCTOP_START_WAIT_SECS": "10",
    }
    start = subprocess.run(
        ["bash", str(cmd / "main"), "start"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    try:
        assert start.returncode == 0, start.stderr or start.stdout
        assert _port_open(port), "fake native service did not listen"
        stop = subprocess.run(
            ["bash", str(cmd / "main"), "stop"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert stop.returncode == 0, stop.stderr or (pkgvar / "info.log").read_text(
            encoding="utf-8"
        )
        assert _wait_until(lambda: not _port_open(port)), f"stop left {port} listening"
        again = subprocess.run(
            ["bash", str(cmd / "main"), "start"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert again.returncode == 0, again.stderr or (pkgvar / "info.log").read_text(
            encoding="utf-8"
        )
        assert _wait_until(lambda: _port_open(port)), "restart did not bind after stop"
    finally:
        subprocess.run(
            ["bash", str(cmd / "main"), "stop"],
            env=env,
            check=False,
            capture_output=True,
            timeout=20,
        )
        pid_file = pkgvar / "octop.pid"
        if pid_file.is_file():
            with contextlib.suppress(OSError, ValueError):
                os.kill(int(pid_file.read_text(encoding="utf-8").strip()), signal.SIGKILL)


@posix_only
def test_native_main_start_term_cleans_unready_child(tmp_path: Path) -> None:
    """飞牛若在端口就绪前杀掉 start，trap 必须退出并收掉未就绪子进程。

    不驱动完整 ``main start``：就绪轮询会调 ``ss`` / ``pgrep -f``，预提交负载下会把套件卡住。
    生产脚本的 trap 文案由 ``test_native_main_stop_releases_listen_port`` 锁住；这里只回放
    abort+exit 语义。
    """
    pid_file = tmp_path / "octop.pid"
    ready_file = tmp_path / "ready"
    wrapper = tmp_path / "abort.sh"
    wrapper.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        "sleep 120 &\n"
        "octop_pid=$!\n"
        f'printf "%s" "$octop_pid" > "{pid_file}"\n'
        "_abort_start() {\n"
        "  trap - INT TERM HUP\n"
        '  kill -TERM "$octop_pid" 2>/dev/null || true\n'
        '  kill -KILL "$octop_pid" 2>/dev/null || true\n'
        f'  rm -f "{pid_file}"\n'
        "}\n"
        "_abort_start_and_exit() {\n"
        "  _abort_start\n"
        "  exit 1\n"
        "}\n"
        "trap '_abort_start_and_exit' INT TERM HUP\n"
        f': > "{ready_file}"\n'
        "while sleep 1; do :; done\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    proc = subprocess.Popen(
        ["bash", str(wrapper)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    child_pid = 0
    try:
        assert _wait_until(ready_file.is_file, timeout=2), "abort wrapper did not install trap"
        child_pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(proc.pid, signal.SIGTERM)
        try:
            rc = proc.wait(timeout=2)
        except subprocess.TimeoutExpired as exc:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
            raise AssertionError("abort trap did not exit after SIGTERM") from exc
        assert rc == 1
        assert not pid_file.exists()
        try:
            os.kill(child_pid, 0)
        except OSError:
            pass
        else:
            raise AssertionError(f"unready child {child_pid} still alive")
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
        if child_pid:
            with contextlib.suppress(OSError):
                os.kill(child_pid, signal.SIGKILL)


@posix_only
def test_octop_fpk_native_run_pids_and_sweep(tmp_path: Path) -> None:
    env = {**os.environ, "OCTOP_INSTALL_MODE": "fpk-native"}
    proc = subprocess.Popen(
        ["python3", "-c", "import time; time.sleep(120)  # octop.cli.main run"],
        env=env,
    )
    try:
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
{_FAST_KILL_TREE}
export TRIM_APPDEST="{tmp_path}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
octop_fpk_native_run_pids() {{ printf '%s\\n' '{proc.pid}'; }}
found="$(octop_fpk_native_run_pids)"
echo "$found" | grep -qx "{proc.pid}"
octop_kill_pid_tree {proc.pid} TERM
octop_wait_pids_gone 15 {proc.pid} || octop_kill_pid_tree {proc.pid} KILL
"""
        subprocess.run(["bash", "-c", script], check=True, timeout=15)
        assert _wait_until(lambda: proc.poll() is not None), "fpk-native run was not swept"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
