"""Live Docker image boot: valid vs invalid OCTOP_DEFAULT_PASSWORD.

Requires a built image (default ``octop:test``) and a working Docker daemon.
These tests start real containers; they are marked ``slow``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

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
            inspect = _run(["docker", "inspect", "-f", "{{.State.Status}}", name])
            if inspect.stdout.strip() not in {"running", "created"}:
                logs = _run(["docker", "logs", name], timeout=20)
                raise AssertionError(
                    f"container stopped: {inspect.stdout} {logs.stdout}\n{logs.stderr}"
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
