"""Device login lifecycle against a local subprocess, without a real mailbox."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from octop.infra.connectors.gateway import agently_auth


@pytest.fixture
async def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")  # Match the native CLI on Windows too.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "auth").write_text(
        """import json, os, pathlib, sys, time
root = pathlib.Path(os.environ['AGENTLY_CLI_CONFIG_DIR'])
command = sys.argv[1]
with (root / 'calls').open('a') as out:
    out.write(command + '\\n')
if command == 'login':
    (root / 'pid').write_text(str(os.getpid()))
    if (root / 'fail').exists():
        print('access_token=DO-NOT-RETURN-THIS', flush=True)
        sys.exit(1)
    print('请点击以下链接登录并授权邮箱：', flush=True)
    print('https://auth.agent.qq.com/device?user_code=TEST-CODE', flush=True)
    while not (root / 'authorized').exists():
        time.sleep(0.01)
elif command == 'logout':
    (root / 'authorized').unlink(missing_ok=True)
elif command == 'refresh':
    if not (root / 'authorized').exists():
        sys.exit(1)
print(json.dumps({'ok': True, 'data': {
    'logged_in': (root / 'authorized').exists(), 'access_token': 'DO-NOT-RETURN-THIS',
    'token_status': 'expired' if (root / 'expired').exists() else 'auto_refresh'
}}), flush=True)
""",
        encoding="utf-8",
    )

    def prepare(creds):
        directory = tmp_path / creds["cli_config_key"]
        directory.mkdir(exist_ok=True)
        return sys.executable, {**os.environ, "AGENTLY_CLI_CONFIG_DIR": str(directory)}

    monkeypatch.setattr(agently_auth, "_prepare", prepare)
    yield tmp_path
    await agently_auth.close()


async def test_login_isolated_idempotent_and_revoked(cli: Path) -> None:
    first = {"cli_config_key": "first"}
    second = {"cli_config_key": "second"}
    assert (await agently_auth.authorize(first, "status"))["status"] == "idle"
    started = await agently_auth.authorize(first, "start")
    assert started["status"] == "pending"
    assert started["verification_url"] == "https://auth.agent.qq.com/device?user_code=TEST-CODE"
    assert started["user_code"] == "TEST-CODE"
    assert await agently_auth.authorize(first, "start") == started
    assert (cli / "first" / "calls").read_text().splitlines().count("login") == 1
    assert (await agently_auth.authorize(second, "status"))["status"] == "idle"
    (cli / "first" / "authorized").touch()
    task = agently_auth._sessions[agently_auth._key(first)].task
    assert task is not None
    await asyncio.wait_for(task, 5)
    result = await agently_auth.authorize(first, "status")
    assert result["status"] == "authorized"
    assert result["verification_url"] is None
    assert "DO-NOT-RETURN-THIS" not in str(result)
    (cli / "first" / "expired").touch()
    assert (await agently_auth.authorize(first, "status"))["status"] == "expired"
    (cli / "first" / "expired").unlink()
    assert (await agently_auth.authorize(first, "refresh"))["status"] == "authorized"
    assert (await agently_auth.authorize(second, "status"))["status"] == "idle"
    assert (await agently_auth.authorize(first, "logout"))["status"] == "idle"
    assert not (cli / "first" / "authorized").exists()


async def test_login_timeout_and_logout_reap_process(cli: Path, monkeypatch) -> None:
    creds = {"cli_config_key": "timeout"}
    monkeypatch.setattr(agently_auth, "_LOGIN_TIMEOUT", 0.15)
    await agently_auth.authorize(creds, "start")
    session = agently_auth._sessions[agently_auth._key(creds)]
    assert session.task is not None
    await asyncio.wait_for(session.task, 5)
    result = await agently_auth.authorize(creds, "status")
    assert result["status"] == "expired"
    assert result["verification_url"] is None
    assert "login_expired" in (result["error"] or "") or "expired" in (result["error"] or "")
    monkeypatch.setattr(agently_auth, "_LOGIN_TIMEOUT", 10)
    assert (await agently_auth.authorize(creds, "start"))["status"] == "pending"
    session = agently_auth._sessions[agently_auth._key(creds)]
    assert (await agently_auth.authorize(creds, "logout"))["status"] == "idle"
    assert session.task is not None and session.task.done()
    assert agently_auth._key(creds) not in agently_auth._sessions


async def test_login_error_and_refresh_never_expose_cli_output(cli: Path) -> None:
    root = cli / "failed"
    root.mkdir()
    (root / "fail").touch()
    creds = {"cli_config_key": "failed"}
    result = await agently_auth.authorize(creds, "start")
    assert result["status"] == "error"
    assert "DO-NOT-RETURN-THIS" not in str(result)
    assert (await agently_auth.authorize(creds, "refresh"))["status"] == "error"


async def test_disconnect_allows_removing_instance_when_cli_missing(cli: Path, monkeypatch) -> None:
    def missing(_creds):
        raise FileNotFoundError

    monkeypatch.setattr(agently_auth, "_prepare", missing)
    creds = {"cli_config_key": "missing"}
    assert (await agently_auth.authorize(creds, "logout"))["status"] == "error"
    assert (await agently_auth.authorize(creds, "disconnect"))["status"] == "idle"


def test_only_trusted_verification_urls_are_returned() -> None:
    session = agently_auth._Login()
    for url in (
        "https://agent.qq.com.attacker.example/device?user_code=CODE",
        "https://agent.qq.com/device?access_token=SECRET",
        "https://user:secret@agent.qq.com/device",
    ):
        agently_auth._read_verification_url(url, session)
        assert session.verification_url is None
    agently_auth._read_verification_url(
        '{"browser_url":"https://auth.agent.qq.com/device?user_code=OK"}', session
    )
    assert session.verification_url == "https://auth.agent.qq.com/device?user_code=OK"
