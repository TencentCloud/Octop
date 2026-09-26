"""The FnOS package must free only its own processes, never a third party's (issue #985).

``free_octop_ports`` runs from the install/uninstall callbacks as root. Before the fix it
sent SIGTERM/SIGKILL to whatever held 8088/8089 — including ``docker-proxy`` backing an
unrelated container — and the native ``config_callback`` rewrote ``OCTOP_PORT`` back to
the packaged default on every save.

Each case spawns a throwaway ``sleep`` inside the same bash process, so the pid the
stubbed ``ss`` reports is a pid that shell can really signal.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMON_SH = REPO / "scripts" / "fnos" / "common.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is required to source common.sh")

# argv: <common.sh> <log file>; __PROBE__ decides how the ownership probe answers.
_FREE_PORTS_SCRIPT = """
set -u
source "$1"
export TRIM_APPDEST=/var/apps/octop-native
export TRIM_TEMP_LOGFILE="$2"

sleep 30 &
victim=$!

ss() {
    [ "${1:-}" = "-ltnp" ] && \\
        echo "LISTEN 0 4096 0.0.0.0:8089 0.0.0.0:* users:((\\"held\\",pid=${victim},fd=6))"
    return 0
}
fuser() { :; }
lsof() { :; }
pgrep() { return 1; }
__PROBE__

free_octop_ports
if kill -0 "$victim" 2>/dev/null; then
    echo "holder=alive"
else
    echo "holder=killed"
fi
kill -9 "$victim" 2>/dev/null || true
"""

_REAL_PROBE = ""
_UNREADABLE_PROBE = "octop_proc_cmdline() { return 0; }"


def _own_cmdline_probe(cmdline: str) -> str:
    quoted = cmdline.replace("\\", "\\\\").replace('"', '\\"')
    return f'octop_proc_cmdline() {{ printf "%s" "{quoted}"; }}'


def _release(tmp_path: Path, probe: str) -> tuple[str, str]:
    """Run ``free_octop_ports`` against a live holder of port 8089; return (stdout, log)."""
    log = tmp_path / "install.log"
    log.write_text("", encoding="utf-8")
    script = _FREE_PORTS_SCRIPT.replace("__PROBE__", probe)
    proc = subprocess.run(
        [BASH or "bash", "-c", script, "bash", str(COMMON_SH), str(log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"bash failed: {proc.stdout}\n{proc.stderr}"
    return proc.stdout, log.read_text(encoding="utf-8")


def test_third_party_port_holder_is_left_alone(tmp_path: Path) -> None:
    """Real probe, real process: a `sleep` is not Octop, so it must survive."""
    out, log = _release(tmp_path, _REAL_PROBE)
    assert "holder=alive" in out
    assert "非本应用进程占用" in log
    assert "清理本应用占用" not in log


def test_unreadable_command_line_is_not_treated_as_ours(tmp_path: Path) -> None:
    """No /proc and no `ps` means unknown ownership — the fail-safe is to leave it."""
    out, _log = _release(tmp_path, _UNREADABLE_PROBE)
    assert "holder=alive" in out


def test_leftover_octop_launcher_is_still_cleaned_up(tmp_path: Path) -> None:
    _out, log = _release(
        tmp_path,
        _own_cmdline_probe(
            "runuser -u octop-native -- /var/apps/octop-native/bin/octop --port 8089"
        ),
    )
    assert "清理本应用占用 8089" in log
    assert "非本应用进程占用" not in log


def test_leftover_octop_server_module_is_still_cleaned_up(tmp_path: Path) -> None:
    _out, log = _release(
        tmp_path,
        _own_cmdline_probe(
            "/var/apps/python312/target/bin/python3.12 -m octop.cli.main run --port 8089"
        ),
    )
    assert "清理本应用占用 8089" in log
    assert "非本应用进程占用" not in log


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("9999", "9999"),
        ("8089", "8089"),
        ("abc", "8089"),
        ("0", "8089"),
        ("70000", "8089"),
        ("99999999999999999999", "8089"),
        ("", "8089"),
    ],
)
def test_effective_port_follows_the_env_file(tmp_path: Path, stored: str, expected: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"OCTOP_PORT={stored}\n" if stored else "OCTOP_ADMIN_USERNAME=admin\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            BASH or "bash",
            "-c",
            'set -u\nsource "$1"\nprintf "%s" "$(octop_effective_port "$2" 8089)"\n',
            "bash",
            str(COMMON_SH),
            str(env_file),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == expected


def test_native_settings_save_no_longer_forces_the_default_port() -> None:
    text = (REPO / "fnos" / "native" / "cmd" / "config_callback").read_text(encoding="utf-8")
    assert 'octop_env_set "$ENV_FILE" OCTOP_PORT "$CUR_PORT"' in text
    assert 'OCTOP_PORT "8089"' not in text
    assert '"$ADMIN_PASS" "$CUR_PORT"' in text


@pytest.mark.skipif(os.name != "posix", reason="signal semantics are POSIX-only")
def test_killed_holder_is_really_gone(tmp_path: Path) -> None:
    """The cleanup path must still terminate a leftover Octop process, not just log."""
    out, _log = _release(
        tmp_path,
        _own_cmdline_probe("/var/apps/octop-native/bin/octop --host 0.0.0.0 --port 8089"),
    )
    assert "holder=killed" in out
