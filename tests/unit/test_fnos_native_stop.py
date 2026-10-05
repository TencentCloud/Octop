"""FnOS native stop must free 8089 so App Center checkport can start again."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(os.name != "posix", reason="bash helpers")

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
    assert "trap '_abort_start'" in text
    assert 'printf "%s" "$octop_pid" > "${PID_FILE}"' in text


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
export TRIM_APPDEST="{tmp_path}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
free_octop_ports {port}
"""
        subprocess.check_call(["bash", "-c", script])
        assert _wait_until(lambda: not _port_open(port)), f"port {port} still listening"
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)


@posix_only
def test_free_octop_ports_kills_orphan_child(tmp_path: Path) -> None:
    """Killing only the wrapper (old stop) leaves the listener; free_octop_ports must catch it."""
    port = _free_tcp_port()
    wrapper = _start_wrapper_listener(port)
    try:
        assert _wait_until(lambda: _port_open(port)), f"child did not bind {port}"
        wrapper.terminate()
        wrapper.wait(timeout=3)
        assert _port_open(port), "expected orphan listener to survive wrapper death"
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
export TRIM_APPDEST="{tmp_path}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
free_octop_ports {port}
"""
        subprocess.check_call(["bash", "-c", script])
        assert _wait_until(lambda: not _port_open(port)), f"orphan still listening on {port}"
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=3)


@posix_only
def test_octop_kill_pid_tree_stops_child_listener() -> None:
    port = _free_tcp_port()
    wrapper = _start_wrapper_listener(port)
    try:
        assert _wait_until(lambda: _port_open(port)), f"child did not bind {port}"
        script = f"""
set -euo pipefail
source "{COMMON_SH}"
octop_kill_pid_tree {wrapper.pid} TERM
sleep 1
if kill -0 {wrapper.pid} 2>/dev/null; then
  octop_kill_pid_tree {wrapper.pid} KILL
fi
"""
        subprocess.check_call(["bash", "-c", script])
        assert _wait_until(lambda: not _port_open(port)), f"child still listening on {port}"
        assert wrapper.poll() is not None
    finally:
        if wrapper.poll() is None:
            wrapper.kill()
            wrapper.wait(timeout=3)


@posix_only
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
        )
        if _port_open(port):
            subprocess.run(
                ["bash", "-c", f'source "{COMMON_SH}"; free_octop_ports {port}'],
                check=False,
            )


def _copy_ctl(cmd: Path) -> None:
    cmd.mkdir(parents=True, exist_ok=True)
    shutil.copy(FNOS_NATIVE / "cmd" / "main", cmd / "main")
    shutil.copy(COMMON_SH, cmd / "common.sh")
    (cmd / "main").chmod(0o755)


@posix_only
def test_native_main_start_term_cleans_unready_child(tmp_path: Path) -> None:
    """飞牛若在端口就绪前杀掉 start，必须把已拉起的后台进程一起收掉。"""
    if shutil.which("python3") is None:
        pytest.skip("python3 required")
    if _octop_native_user_exists() and os.geteuid() != 0:
        pytest.skip("octop-native 存在且当前非 root，runuser 后无法在测试里停掉服务")
    port = _free_tcp_port()
    appdest = tmp_path / "app"
    pkgvar = tmp_path / "var"
    data = tmp_path / "data"
    (appdest / "bin").mkdir(parents=True)
    pkgvar.mkdir()
    (data / ".octop").mkdir(parents=True)
    (data / ".octop" / "octop.db").write_text("", encoding="utf-8")
    cmd = tmp_path / "cmd"
    _copy_ctl(cmd)
    launcher = appdest / "bin" / "octop"
    launcher.write_text(
        "#!/bin/bash\n"
        'if [ "${1:-}" = "--prepare" ]; then exit 0; fi\n'
        "sleep 20\n"
        'python3 -c "import socket,time;'
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        "s.bind(('127.0.0.1',int('$OCTOP_PORT')));s.listen(1);time.sleep(120)\"\n",
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
        "OCTOP_START_WAIT_SECS": "30",
    }
    proc = subprocess.Popen(
        ["bash", str(cmd / "main"), "start"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _wait_until(lambda: (pkgvar / "octop.pid").is_file(), timeout=3)
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        assert not _wait_until(lambda: _port_open(port), timeout=1.5)
        assert not (pkgvar / "octop.pid").exists() or not _pid_file_alive(pkgvar / "octop.pid")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
        subprocess.run(
            [
                "bash",
                "-c",
                f'source "{COMMON_SH}"; export TRIM_APPDEST="{appdest}"; free_octop_ports {port}',
            ],
            check=False,
        )


def _pid_file_alive(path: Path) -> bool:
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
export TRIM_APPDEST="{tmp_path}"
export TRIM_TEMP_LOGFILE="{tmp_path / "octop.log"}"
found="$(octop_fpk_native_run_pids)"
echo "$found" | grep -qx "{proc.pid}"
octop_kill_pid_tree {proc.pid} TERM
octop_wait_pids_gone 15 {proc.pid} || octop_kill_pid_tree {proc.pid} KILL
"""
        subprocess.check_call(["bash", "-c", script])
        assert _wait_until(lambda: proc.poll() is not None), "fpk-native run was not swept"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=3)
