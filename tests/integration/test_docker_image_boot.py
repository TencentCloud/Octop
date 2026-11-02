"""Live Docker image boot: valid vs invalid OCTOP_DEFAULT_PASSWORD.

Requires a built image (default ``octop:test``) and a working Docker daemon.
These tests start real containers; they are marked ``slow``.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from tests.unit.test_docker_image_arch import native_import_failed, normalized_cpu_arch

IMAGE = os.environ.get("OCTOP_TEST_IMAGE", "octop:test")
READY_TIMEOUT_S = 180


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _image_present() -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            check=False,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


docker_live = pytest.mark.skipif(
    not _docker_available() or not _image_present(),
    reason=f"need docker and image {IMAGE}",
)


def _run(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _http_json(
    name: str, path: str, *, data: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    # DinD: published host ports often never reach this process. Call the API
    # from inside the container instead of relying on -p.
    cmd = [
        "docker",
        "exec",
        name,
        "curl",
        "-sS",
        "-o",
        "/tmp/octop-http-body",
        "-w",
        "%{http_code}",
        "-H",
        "Content-Type: application/json",
    ]
    if data is not None:
        cmd.extend(["-X", "POST", "--data-binary", json.dumps(data)])
    cmd.append(f"http://127.0.0.1:8088{path}")
    result = _run(cmd, timeout=20)
    if result.returncode != 0:
        return 0, {"curl_error": result.stderr or result.stdout}
    try:
        status = int((result.stdout or "0").strip() or "0")
    except ValueError:
        return 0, {"curl_error": result.stdout}
    body = _run(["docker", "exec", name, "cat", "/tmp/octop-http-body"])
    raw = body.stdout
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw}
    return status, parsed


@pytest.fixture
def docker_boot() -> Iterator[Any]:
    name = f"octop-boot-{uuid.uuid4().hex[:10]}"
    volume = f"{name}-data"

    def start(password: str | None) -> dict[str, str]:
        create = _run(["docker", "volume", "create", volume])
        assert create.returncode == 0, create.stderr
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "HOME=/data",
            "-e",
            "OCTOP_PORT=8088",
            "-e",
            "OCTOP_LOG_LEVEL=warning",
            "--shm-size=1g",
            "-v",
            f"{volume}:/data/.octop",
        ]
        if password is not None:
            cmd.extend(["-e", f"OCTOP_DEFAULT_PASSWORD={password}"])
        cmd.append(IMAGE)
        run = _run(cmd)
        assert run.returncode == 0, run.stderr
        deadline = time.time() + READY_TIMEOUT_S
        last_error = "not started"
        while time.time() < deadline:
            status, payload = _http_json(name, "/api/health")
            if status == 200:
                return {"name": name, "volume": volume}
            last_error = f"health={status} {payload}"
            inspect = _run(
                ["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", name]
            )
            state_text = inspect.stdout.strip()
            state, _, exit_code = state_text.partition(" ")
            if state not in {"running", "created"}:
                logs = _run(["docker", "logs", name], timeout=20)
                hint = ""
                if exit_code == "132" or "Illegal instruction" in (logs.stdout + logs.stderr):
                    hint = (
                        " ExitCode 132 is SIGILL. On ARM (including FnOS in a VM) "
                        "this usually means a native wheel uses instructions this CPU "
                        "does not support. See issues #2190 and #2301."
                    )
                raise AssertionError(
                    f"container stopped: {state_text} {logs.stdout}\n{logs.stderr}{hint}"
                )
            time.sleep(2)
        logs = _run(["docker", "logs", name], timeout=20)
        raise AssertionError(
            f"container not healthy in {READY_TIMEOUT_S}s: {last_error}\n{logs.stdout}\n{logs.stderr}"
        )

    try:
        yield start
    finally:
        _run(["docker", "rm", "-f", name], timeout=60)
        _run(["docker", "volume", "rm", "-f", volume], timeout=60)


def _xvnc_running(name: str) -> bool:
    result = _run(
        [
            "docker",
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            (
                "import os\n"
                "me = str(os.getpid())\n"
                "found = False\n"
                "for pid in os.listdir('/proc'):\n"
                "    if not pid.isdigit() or pid == me:\n"
                "        continue\n"
                "    try:\n"
                "        cmd = open(f'/proc/{pid}/cmdline','rb').read()\n"
                "    except OSError:\n"
                "        continue\n"
                "    argv0 = os.path.basename(cmd.split(b'\\0', 1)[0])\n"
                "    if argv0 in {b'Xvnc', b'Xtigervnc'}:\n"
                "        found = True\n"
                "print('yes' if found else 'no')\n"
            ),
        ]
    )
    return result.returncode == 0 and result.stdout.strip() == "yes"


def _exec_text(name: str, path: str) -> str:
    result = _run(["docker", "exec", name, "cat", path])
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.slow
@docker_live
def test_docker_valid_password_creates_admin_and_serves(docker_boot: Any) -> None:
    password = "GoodPass1"
    boot = docker_boot(password)
    name = boot["name"]
    status, setup = _http_json(name, "/api/setup/status")
    assert status == 200
    assert setup["setup_required"] is False
    login_status, login = _http_json(
        name,
        "/api/auth/login",
        data={"username": "admin", "password": password},
    )
    assert login_status == 200, login
    assert login.get("access_token")
    assert (login.get("user") or {}).get("username") == "admin"
    cred = _exec_text(name, "/data/.octop/credential.txt")
    assert "Octop Login Credential" in cred
    assert f"Password: {password}" in cred
    wizard = _run(["docker", "exec", name, "test", "-f", "/data/.octop/octop-login.txt"])
    assert wizard.returncode != 0


@pytest.mark.slow
@docker_live
@pytest.mark.parametrize("password", ["password1", "Ab1", "abcdefgh"])
def test_docker_invalid_password_starts_setup_wizard(docker_boot: Any, password: str) -> None:
    boot = docker_boot(password)
    name = boot["name"]
    status, setup = _http_json(name, "/api/setup/status")
    assert status == 200
    assert setup["setup_required"] is True
    assert setup["wizard_password_exists"] is True
    login_status, login = _http_json(
        name,
        "/api/auth/login",
        data={"username": "admin", "password": password},
    )
    # Setup lockdown blocks /api/auth/login before the route can emit SETUP_REQUIRED.
    assert login_status == 503, login
    assert login.get("setup_required") is True
    hint = _exec_text(name, "/data/.octop/credential.txt")
    assert "Setup Required" in hint
    wizard = _exec_text(name, "/data/.octop/octop-login.txt").strip()
    assert wizard
    logs = _run(["docker", "logs", name], timeout=20).stdout
    assert "未通过密码策略" in logs


@pytest.mark.slow
@docker_live
def test_docker_unset_password_starts_setup_wizard(docker_boot: Any) -> None:
    boot = docker_boot(None)
    name = boot["name"]
    status, setup = _http_json(name, "/api/setup/status")
    assert status == 200
    assert setup["setup_required"] is True
    assert setup["wizard_password_exists"] is True
    logs = _run(["docker", "logs", name], timeout=20).stdout
    assert "未设置 OCTOP_DEFAULT_PASSWORD" in logs
    assert "Setup Required" in _exec_text(name, "/data/.octop/credential.txt")
    login_status, login = _http_json(
        name,
        "/api/auth/login",
        data={"username": "admin", "password": "GoodPass1"},
    )
    assert login_status == 503, login
    assert login.get("setup_required") is True


@pytest.mark.live
@pytest.mark.slow
@docker_live
def test_docker_image_runs_on_this_cpu_and_stays_disabled(docker_boot: Any) -> None:
    """Boot the image on this machine and check it is the matching CPU build.

    Run on the machine that fails, for example an ARM FnOS host::

        OCTOP_TEST_IMAGE=ghcr.io/tencentcloud/octop:1.0.2 \\
            uv run pytest tests/integration/test_docker_image_boot.py -m live -q

    Exit 132 / ``Illegal instruction`` is the failure in issues #2190 and #2301.
    A baked desktop must be installed and stopped, then this test starts Xvnc.
    """
    boot = docker_boot(None)
    name = boot["name"]
    guest = _run(["docker", "exec", name, "uname", "-m"])
    assert guest.returncode == 0, guest.stderr
    host = platform.machine()
    assert normalized_cpu_arch(guest.stdout) == normalized_cpu_arch(host), (
        f"container CPU {guest.stdout.strip()} does not match host {host}. "
        "On ARM this usually means the published tag has no arm64 image "
        "and Docker started the amd64 one."
    )

    probe = _run(
        [
            "docker",
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "import cv2, onnxruntime",
        ],
        timeout=60,
    )
    combined = f"{probe.stdout}\n{probe.stderr}"
    if native_import_failed(probe.returncode, combined):
        raise AssertionError(
            "importing cv2/onnxruntime raised SIGILL (exit 132). "
            "The arm64 wheels in this image use instructions this CPU or VM "
            "does not support (issues #2190 and #2301).\n"
            f"{combined}"
        )
    assert probe.returncode == 0, combined

    marker = _run(["docker", "exec", name, "cat", "/etc/octop/bundled-components.json"])
    if marker.returncode != 0:
        pytest.skip("image has no bundled-components marker; rebuild to check desktop bake")
    payload = json.loads(marker.stdout)
    assert payload.get("desktop") is True
    assert payload.get("laya") is False
    if payload.get("browser") is True:
        chrome = _run(
            [
                "docker",
                "exec",
                name,
                "sh",
                "-c",
                "test -x /usr/bin/chromium || test -x /usr/bin/chromium-browser",
            ]
        )
        assert chrome.returncode == 0, "bundled browser marker set but Chromium missing"
    else:
        firefox = _run(
            [
                "docker",
                "exec",
                name,
                "sh",
                "-c",
                "test -x /usr/bin/firefox-esr || test -x /usr/bin/firefox",
            ]
        )
        assert firefox.returncode == 0, "desktop baked without Chromium or Firefox"
        assert payload.get("browser") is False

    desktop_py = _run(
        [
            "docker",
            "exec",
            name,
            "/app/.venv/bin/python",
            "-c",
            "import mss, pynput",
        ],
        timeout=60,
    )
    assert desktop_py.returncode == 0, desktop_py.stderr
    xvnc = _run(["docker", "exec", name, "sh", "-c", "command -v Xvnc || command -v Xtigervnc"])
    assert xvnc.returncode == 0, xvnc.stderr
    assert not _xvnc_running(name)
    enabled = _run(["docker", "exec", name, "test", "-f", "/data/.octop/browser.enabled"])
    assert enabled.returncode != 0

    shm = _run(["docker", "exec", name, "df", "-B1", "--output=size", "/dev/shm"])
    assert shm.returncode == 0, shm.stderr
    assert int(shm.stdout.strip().splitlines()[-1].strip()) >= 512 * 1024 * 1024, shm.stdout
    started = _run(
        [
            "docker",
            "exec",
            "-e",
            "HOME=/data",
            "-e",
            "OCTOP_HOME=/data/.octop",
            name,
            "bash",
            "/app/src/octop/infra/control/desktop/scripts/linux/v1.0/start.sh",
        ],
        timeout=30,
    )
    desktop_log = _run(
        [
            "docker",
            "exec",
            name,
            "sh",
            "-c",
            "cat /data/.octop/desktop/*.log 2>/dev/null || true",
        ]
    )
    assert started.returncode == 0, f"{started.stdout}\n{started.stderr}\n{desktop_log.stdout}"
    time.sleep(1)
    assert _xvnc_running(name), desktop_log.stdout or started.stderr
