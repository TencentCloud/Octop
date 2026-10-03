"""Unit tests for channels QR scan endpoints."""

from __future__ import annotations

import asyncio
import io
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def mock_server_and_user():
    """Minimal server/user mock for channel QR endpoints."""
    user = MagicMock()
    user.id = 1
    user.is_admin = True

    registry = MagicMock()
    registry.get_row.return_value = MagicMock(id="agent1")

    runtime = MagicMock()
    runtime.app_runtime = MagicMock()
    runtime.app_runtime.agent_registry = registry
    runtime.app_runtime.gateway = MagicMock()
    runtime.services = MagicMock()
    runtime.services.channel_repo.list_by_agent.return_value = []

    return runtime, user


def _make_app(server, user):
    from fastapi import FastAPI

    from octop.api.deps import current_user, get_server
    from octop.api.routers import channels as ch_module

    app = FastAPI()
    app.include_router(ch_module.router)
    app.dependency_overrides[get_server] = lambda: server
    app.dependency_overrides[current_user] = lambda: user
    return app


def test_wecom_qrcode_generate_returns_scode(mock_server_and_user):
    """wecom/qrcode/generate should return scode and auth_url on success."""
    server, user = mock_server_and_user

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"data": {"scode": "sc123", "auth_url": "https://wecom/qr"}}
    fake_resp.raise_for_status = MagicMock()

    mock_async_client = MagicMock()
    mock_async_client.__aenter__ = AsyncMock(
        return_value=AsyncMock(get=AsyncMock(return_value=fake_resp))
    )
    mock_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "octop.infra.gateway.channels.qr_bind.httpx.AsyncClient", return_value=mock_async_client
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post("/agents/agent1/channels/wecom/qrcode/generate")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scode"] == "sc123"
    assert data["auth_url"] == "https://wecom/qr"


def test_wecom_qrcode_poll_returns_status(mock_server_and_user):
    """wecom/qrcode/poll should proxy WeCom status."""
    server, user = mock_server_and_user

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"data": {"status": "pending"}}
    fake_resp.raise_for_status = MagicMock()

    mock_async_client = MagicMock()
    mock_async_client.__aenter__ = AsyncMock(
        return_value=AsyncMock(get=AsyncMock(return_value=fake_resp))
    )
    mock_async_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "octop.infra.gateway.channels.qr_bind.httpx.AsyncClient", return_value=mock_async_client
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post(
            "/agents/agent1/channels/wecom/qrcode/poll",
            json={"scode": "sc123"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"


def test_qq_qrcode_generate_returns_task(mock_server_and_user):
    """qq/qrcode/generate should return the task token and render URL."""
    server, user = mock_server_and_user
    with patch(
        "octop.api.routers.channels.qr_bind.qq_qr_generate",
        new=AsyncMock(
            return_value={"qrcode_token": "qq-task", "qrcode_url": "https://q.qq.com/qr"}
        ),
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post("/agents/agent1/channels/qq/qrcode/generate")

    assert resp.status_code == 200
    assert resp.json() == {"qrcode_token": "qq-task", "qrcode_url": "https://q.qq.com/qr"}


def test_qq_qrcode_poll_returns_credentials(mock_server_and_user):
    """qq/qrcode/poll should return credentials after mobile confirmation."""
    server, user = mock_server_and_user
    result = {
        "status": "success",
        "app_id": "qq-app",
        "secret": "qq-secret",
        "user_openid": "operator-openid",
    }
    with patch(
        "octop.api.routers.channels.qr_bind.qq_qr_poll",
        new=AsyncMock(return_value=result),
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post(
            "/agents/agent1/channels/qq/qrcode/poll",
            json={"qrcode_token": "qq-task"},
        )

    assert resp.status_code == 200
    assert resp.json() == result


def test_dingtalk_qrcode_generate_keeps_device_code_server_side(mock_server_and_user):
    """Only an opaque Octop registration ID and public QR metadata reach the browser."""
    server, user = mock_server_and_user
    from octop.api.routers import channels as ch_module

    ch_module._dingtalk_registration_sessions.clear()
    result = {
        "device_code": "device-secret",
        "user_code": "ABCD-EFGH-IJKL",
        "verification_uri_complete": "https://open-dev.dingtalk.com/scan?code=public",
        "expires_in": 7200,
        "interval": 5,
    }
    with patch(
        "octop.api.routers.channels.dingtalk_registration.generate",
        new=AsyncMock(return_value=result),
    ):
        client = TestClient(_make_app(server, user))
        resp = client.post("/agents/agent1/channels/dingtalk/qrcode/generate")

    assert resp.status_code == 200
    data = resp.json()
    assert data["qrcode_url"] == result["verification_uri_complete"]
    assert data["user_code"] == result["user_code"]
    assert data["interval"] == 5
    assert "device_code" not in data
    stored = ch_module._dingtalk_registration_sessions[data["registration_id"]]
    assert stored.device_code == "device-secret"


def test_dingtalk_qrcode_poll_creates_channel_without_returning_secret(
    mock_server_and_user,
):
    """Successful authorization probes and persists credentials only on the server."""
    server, user = mock_server_and_user
    from octop.api.routers import channels as ch_module

    ch_module._dingtalk_registration_sessions.clear()
    gateway = server.app_runtime.gateway
    gateway.probe_config = AsyncMock(return_value={"ok": True})
    gateway.create_channel = AsyncMock(return_value=MagicMock(channel_id="channel-1"))
    generated = {
        "device_code": "device-secret",
        "user_code": "ABCD-EFGH-IJKL",
        "verification_uri_complete": "https://open-dev.dingtalk.com/scan?code=public",
        "expires_in": 7200,
        "interval": 5,
    }
    authorized = {
        "status": "SUCCESS",
        "client_id": "ding-client",
        "client_secret": "ding-secret",
    }
    with (
        patch(
            "octop.api.routers.channels.dingtalk_registration.generate",
            new=AsyncMock(return_value=generated),
        ),
        patch(
            "octop.api.routers.channels.dingtalk_registration.poll",
            new=AsyncMock(return_value=authorized),
        ),
    ):
        client = TestClient(_make_app(server, user))
        generated_resp = client.post("/agents/agent1/channels/dingtalk/qrcode/generate")
        registration_id = generated_resp.json()["registration_id"]
        resp = client.post(
            "/agents/agent1/channels/dingtalk/qrcode/poll",
            json={"registration_id": registration_id},
        )
        repeated_resp = client.post(
            "/agents/agent1/channels/dingtalk/qrcode/poll",
            json={"registration_id": registration_id},
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "channel_id": "channel-1"}
    assert repeated_resp.json() == resp.json()
    assert "ding-secret" not in resp.text
    probe_config = gateway.probe_config.await_args.kwargs["config"]
    assert probe_config["client_id"] == "ding-client"
    assert probe_config["client_secret"] == "ding-secret"
    spec = gateway.create_channel.await_args.args[0]
    assert spec.kind == "dingtalk"
    assert spec.config["client_secret"] == "ding-secret"
    gateway.create_channel.assert_awaited_once()
    session = ch_module._dingtalk_registration_sessions[registration_id]
    assert session.credentials is None
    assert session.device_code == ""


def test_dingtalk_qrcode_poll_rejects_different_user(mock_server_and_user):
    server, user = mock_server_and_user
    from octop.api.routers import channels as ch_module

    ch_module._dingtalk_registration_sessions.clear()
    generated = {
        "device_code": "device-secret",
        "user_code": "ABCD-EFGH-IJKL",
        "verification_uri_complete": "https://open-dev.dingtalk.com/scan?code=public",
        "expires_in": 7200,
        "interval": 5,
    }
    with patch(
        "octop.api.routers.channels.dingtalk_registration.generate",
        new=AsyncMock(return_value=generated),
    ):
        client = TestClient(_make_app(server, user))
        generated_resp = client.post("/agents/agent1/channels/dingtalk/qrcode/generate")
        registration_id = generated_resp.json()["registration_id"]

    user.id = 2
    resp = client.post(
        "/agents/agent1/channels/dingtalk/qrcode/poll",
        json={"registration_id": registration_id},
    )
    assert resp.status_code == 404


def test_dingtalk_registration_client_uses_official_device_flow_endpoints():
    from octop.infra.gateway.channels import dingtalk_registration

    init_response = MagicMock()
    init_response.json.return_value = {
        "errcode": 0,
        "errmsg": "ok",
        "nonce": "nonce-1",
        "expires_in": 300,
    }
    begin_response = MagicMock()
    begin_response.json.return_value = {
        "errcode": 0,
        "errmsg": "ok",
        "device_code": "device-1",
        "user_code": "ABCD-EFGH-IJKL",
        "verification_uri_complete": "https://open-dev.dingtalk.com/scan",
        "expires_in": 7200,
        "interval": 5,
    }
    post = AsyncMock(side_effect=[init_response, begin_response])
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock(post=post))
    context.__aexit__ = AsyncMock(return_value=False)

    with patch.object(dingtalk_registration.httpx, "AsyncClient", return_value=context):
        result = asyncio.run(dingtalk_registration.generate())

    assert result["device_code"] == "device-1"
    assert post.await_args_list == [
        call("/app/registration/init", json={}),
        call("/app/registration/begin", json={"nonce": "nonce-1"}),
    ]


def test_pkill_chrome_profile_accepts_resolved_path(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """pkill pattern must not fail validation on the '=' separator."""
    from octop.api.routers.channels import _pkill_chrome_profile, _safe_profile_directory

    # Isolate from BROWSER_USE_PROFILES_DIR left by earlier agent/browser tests.
    root = (tmp_path / "browser-profiles").resolve()
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BROWSER_USE_PROFILES_DIR", str(root))
    monkeypatch.delenv("HARNESS_BROWSER_PROFILES_DIR", raising=False)

    profile_dir = _safe_profile_directory("feishu")
    assert profile_dir == root / "octop-feishu-bot"

    with patch("octop.api.routers.channels.asyncio.to_thread", new_callable=AsyncMock):
        import asyncio

        asyncio.run(_pkill_chrome_profile(profile_dir))


def test_feishu_bot_creator_start_without_pkill_mock(mock_server_and_user):
    """feishu/bot-creator/start launches the scan-to-create subprocess."""
    server, user = mock_server_and_user

    mock_proc = MagicMock()
    mock_proc.pid = 1234

    with (
        patch("octop.api.routers.channels.subprocess.Popen", return_value=mock_proc),
        patch(
            "octop.api.routers.channels._bot_creator_script",
            return_value="/fake/feishu_bot_creator.py",
        ),
        patch("octop.api.routers.channels.asyncio.to_thread", new_callable=AsyncMock),
        patch("octop.api.routers.channels.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=1)
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post(
            "/agents/agent1/channels/feishu/bot-creator/start",
            json={},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_feishu_bot_creator_start_returns_pid(mock_server_and_user):
    """feishu/bot-creator/start should launch subprocess and return pid."""
    server, user = mock_server_and_user

    mock_proc = MagicMock()
    mock_proc.pid = 1234

    with (
        patch("octop.api.routers.channels.subprocess.Popen", return_value=mock_proc),
        patch(
            "octop.api.routers.channels._bot_creator_script",
            return_value="/fake/feishu_bot_creator.py",
        ),
        patch("octop.api.routers.channels.asyncio.to_thread", new_callable=AsyncMock),
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post(
            "/agents/agent1/channels/feishu/bot-creator/start",
            json={},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["pid"] == 1234


def test_feishu_bot_creator_stop_not_running(mock_server_and_user):
    """feishu/bot-creator/stop returns not_running when no process."""
    server, user = mock_server_and_user
    app = _make_app(server, user)
    client = TestClient(app)
    resp = client.post("/agents/agent1/channels/feishu/bot-creator/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("stopped", "not_running")


def test_yuanbao_bot_creator_start_returns_pid(mock_server_and_user):
    """yuanbao/bot-creator/start should launch subprocess and return pid."""
    server, user = mock_server_and_user

    mock_proc = MagicMock()
    mock_proc.pid = 9999

    with (
        patch("octop.api.routers.channels.subprocess.Popen", return_value=mock_proc),
        patch(
            "octop.api.routers.channels._bot_creator_script",
            return_value="/fake/yuanbao_bot_creator.py",
        ),
    ):
        app = _make_app(server, user)
        client = TestClient(app)
        resp = client.post(
            "/agents/agent1/channels/yuanbao/bot-creator/start",
            json={},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert data["pid"] == 9999


def test_yuanbao_bot_creator_stop_not_running(mock_server_and_user):
    """yuanbao/bot-creator/stop returns not_running when no process."""
    server, user = mock_server_and_user
    app = _make_app(server, user)
    client = TestClient(app)
    resp = client.post("/agents/agent1/channels/yuanbao/bot-creator/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("stopped", "not_running")


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        (
            "/agents/agent1/channels/feishu/bot-creator/start",
            {"platform": "feishu|whoami"},
        ),
        (
            "/agents/agent1/channels/feishu/bot-creator/start",
            {"greeting": "hello|whoami"},
        ),
        (
            "/agents/agent1/channels/feishu/bot-creator/start",
            {"avatar_url": "https://example.com/a.png;id"},
        ),
        (
            "/agents/agent1/channels/yuanbao/bot-creator/start",
            {"instance_id": "i|id"},
        ),
        (
            "/agents/agent1/channels/yuanbao/bot-creator/start",
            {"instance_id": "i1", "ip": "127.0.0.1;id"},
        ),
        (
            "/agents/agent1/channels/wecom/qrcode/poll",
            {"scode": "sc|id"},
        ),
        (
            "/agents/agent1/channels/weixin/qrcode/poll",
            {"qrcode_token": "tok|id"},
        ),
        (
            "/agents/agent1/channels/qq/qrcode/poll",
            {"qrcode_token": "tok|id"},
        ),
    ],
)
def test_channel_endpoints_reject_shell_metacharacters(mock_server_and_user, endpoint, payload):
    """User-controlled values must not reach subprocess or outbound calls unvalidated."""
    server, user = mock_server_and_user
    app = _make_app(server, user)
    client = TestClient(app)
    resp = client.post(endpoint, json=payload)
    assert resp.status_code == 400


# ── YuanBao bot creator pipes ────────────────────────────────────────────────
# The creator endpoints stream newline-delimited JSON from the child's stdout
# through `parse_subprocess_json_lines`, which is bytes-only (it decodes what it
# reads) on both platforms. These tests spawn a real stub child: mocking Popen
# would hide the pipe configuration, which is exactly what breaks.


def _yuanbao_stub(tmp_path, source: str):
    script = tmp_path / "yuanbao_bot_creator.py"
    script.write_text(source, encoding="utf-8")
    return script


def _yuanbao_start(client, agent_id: str, script):
    with patch("octop.api.routers.channels._bot_creator_script", return_value=script):
        resp = client.post(f"/agents/{agent_id}/channels/yuanbao/bot-creator/start", json={})
    assert resp.status_code == 200
    return resp


def _yuanbao_run_to_end(client, agent_id: str) -> list[dict]:
    """Poll until the creator exits, returning every event the caller was told."""
    events: list[dict] = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        resp = client.post(f"/agents/{agent_id}/channels/yuanbao/bot-creator/poll")
        assert resp.status_code == 200
        payload = resp.json()
        events.extend(payload.get("events", []))
        if payload.get("status") in ("finished", "failed"):
            return events
        time.sleep(0.05)
    raise AssertionError("creator subprocess did not finish")


def test_yuanbao_creator_start_keeps_the_reader_contract(tmp_path, mock_server_and_user):
    """stdout must stay binary and stderr merged: the shared reader decodes bytes."""
    from octop.api.routers import channels as ch_module

    server, user = mock_server_and_user
    agent_id = "yuanbao-pipes"
    script = _yuanbao_stub(tmp_path, "import time\n\ntime.sleep(30)\n")
    app = _make_app(server, user)
    client = TestClient(app)
    _yuanbao_start(client, agent_id, script)
    try:
        proc = ch_module._get_yuanbao_state(agent_id)["proc"]
        assert proc.stdout is not None
        assert not isinstance(proc.stdout, io.TextIOBase), (
            "parse_subprocess_json_lines decodes what it reads, so a text-mode stdout pipe "
            "raises AttributeError on the first poll that has output"
        )
        assert proc.stderr is None, (
            "a stderr pipe nobody drains swallows the child's traceback and blocks it "
            "once the OS pipe buffer is full"
        )
    finally:
        client.post(f"/agents/{agent_id}/channels/yuanbao/bot-creator/stop")


def test_yuanbao_creator_poll_reports_events(tmp_path, mock_server_and_user):
    """The scan code the creator prints on stdout reaches the dashboard."""
    server, user = mock_server_and_user
    agent_id = "yuanbao-events"
    script = _yuanbao_stub(
        tmp_path,
        "import json\n\n"
        'print(json.dumps({"action": "scan_code", "scan_code": "SCAN-1", '
        '"scan_url": "https://qr.example/1"}), flush=True)\n',
    )
    app = _make_app(server, user)
    client = TestClient(app)
    _yuanbao_start(client, agent_id, script)
    try:
        events = _yuanbao_run_to_end(client, agent_id)
    finally:
        client.post(f"/agents/{agent_id}/channels/yuanbao/bot-creator/stop")
    assert [ev for ev in events if ev.get("action") == "scan_code"]


def test_yuanbao_creator_poll_surfaces_stderr(tmp_path, mock_server_and_user):
    """A creator that only logs to stderr must not fail silently."""
    server, user = mock_server_and_user
    agent_id = "yuanbao-stderr"
    script = _yuanbao_stub(
        tmp_path,
        "import sys\n\n"
        'sys.stderr.write("Traceback: yuanbao token exchange rejected\\n")\n'
        "sys.stderr.flush()\n"
        "sys.exit(1)\n",
    )
    app = _make_app(server, user)
    client = TestClient(app)
    _yuanbao_start(client, agent_id, script)
    try:
        events = _yuanbao_run_to_end(client, agent_id)
    finally:
        client.post(f"/agents/{agent_id}/channels/yuanbao/bot-creator/stop")
    messages = [str(ev.get("message", "")) for ev in events]
    assert any("token exchange rejected" in message for message in messages), messages
