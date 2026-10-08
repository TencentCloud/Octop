"""Unit tests for Feishu scan-to-create (lark-oapi register_app)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.request import Request

import pytest
from lark_oapi.scene.registration.errors import AppAccessDeniedError, RegisterAppError

from octop.infra.gateway.bot_creators import feishu_bot_creator as creator
from octop.infra.gateway.bot_creators.feishu_runner import extract_feishu_credentials


@pytest.mark.parametrize("open_base", ["https://open.feishu.cn", "https://open.larksuite.com"])
def test_send_greeting_bounds_both_http_calls(
    monkeypatch: pytest.MonkeyPatch,
    open_base: str,
) -> None:
    calls: list[tuple[Request, Any]] = []

    def fake_urlopen(request: Request, **kwargs: Any) -> BytesIO:
        calls.append((request, kwargs.get("timeout")))
        payload = {"tenant_access_token": "test-token"} if len(calls) == 1 else {}
        return BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(creator.urllib.request, "urlopen", fake_urlopen)
    creator._send_greeting(
        "test-app",
        "test-secret",
        "test-owner",
        open_base=open_base,
        greeting="Hello",
    )

    assert [timeout for _, timeout in calls] == [30, 30]
    token_request, send_request = [request for request, _ in calls]
    assert token_request.full_url == open_base + "/open-apis/auth/v3/tenant_access_token/internal"
    assert send_request.full_url == open_base + "/open-apis/im/v1/messages?receive_id_type=open_id"
    assert send_request.get_header("Authorization") == "Bearer test-token"
    assert send_request.data is not None
    payload = json.loads(send_request.data)
    assert payload["receive_id"] == "test-owner"
    assert json.loads(payload["content"]) == {"text": "Hello"}


@pytest.mark.parametrize("failed_request", [1, 2], ids=["token", "message"])
@pytest.mark.parametrize("failure_phase", ["connect", "read"])
def test_greeting_timeout_does_not_prevent_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failed_request: int,
    failure_phase: str,
) -> None:
    timeouts = []

    def fake_urlopen(_request: Request, **kwargs: Any) -> MagicMock:
        timeouts.append(kwargs.get("timeout"))
        fail = len(timeouts) == failed_request
        if fail and failure_phase == "connect":
            raise TimeoutError("greeting connection timed out")
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"tenant_access_token":"test-token"}'
        if fail:
            response.read.side_effect = TimeoutError("greeting response timed out")
        return response

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(creator, "PLATFORM", "feishu")
    monkeypatch.setattr(creator, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(creator.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        creator.lark,
        "register_app",
        lambda **_kwargs: {
            "client_id": "test-app",
            "client_secret": "test-secret",
            "user_info": {"open_id": "test-owner", "tenant_brand": "feishu"},
        },
    )

    creator.cmd_create(greeting="Hello")

    assert timeouts == [30] * failed_request
    finish = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert finish["action"] == "finish"
    assert finish["level"] == "success"
    assert finish["data"]["app_id"] == "test-app"
    assert finish["data"]["app_secret"] == "test-secret"
    saved = json.loads(
        (tmp_path / "octop-feishu-bot-creator-state.json").read_text(encoding="utf-8")
    )
    assert saved == {"phase": "done", **finish["data"]}


def test_extract_feishu_credentials_from_url_payload() -> None:
    lines = [
        {
            "action": "show_qrcode",
            "content": json.dumps(
                {"url": "https://accounts.feishu.cn/oauth/v1/device/verify?x=1", "expire_in": 600}
            ),
        },
        {
            "action": "finish",
            "level": "success",
            "data": {"app_id": "cli_1", "app_secret": "sec"},
        },
    ]
    qr_url, app_id, app_secret = extract_feishu_credentials(lines)
    assert qr_url == "https://accounts.feishu.cn/oauth/v1/device/verify?x=1"
    assert app_id == "cli_1"
    assert app_secret == "sec"


def test_extract_feishu_credentials_from_bare_url() -> None:
    lines = [{"action": "show_qrcode", "content": "https://accounts.larksuite.com/x"}]
    qr_url, app_id, app_secret = extract_feishu_credentials(lines)
    assert qr_url == "https://accounts.larksuite.com/x"
    assert app_id is None
    assert app_secret is None


def test_register_feishu_app_maps_sdk_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_register_app(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        kwargs["on_qr_code"]({"url": "https://accounts.feishu.cn/qr", "expire_in": 120})
        return {
            "client_id": "cli_new",
            "client_secret": "secret_new",
            "user_info": {"open_id": "ou_1", "tenant_brand": "feishu"},
        }

    sent: dict[str, Any] = {}

    def fake_send(
        app_id: str, app_secret: str, open_id: str, *, open_base: str, greeting: str
    ) -> None:
        sent.update(
            {
                "app_id": app_id,
                "app_secret": app_secret,
                "open_id": open_id,
                "open_base": open_base,
                "greeting": greeting,
            }
        )

    monkeypatch.setattr(creator.lark, "register_app", fake_register_app)
    monkeypatch.setattr(creator, "_send_greeting", fake_send)
    monkeypatch.setattr(creator, "_save_state", lambda _data: None)

    finish = creator.register_feishu_app(greeting="hello")
    assert finish["app_id"] == "cli_new"
    assert finish["app_secret"] == "secret_new"
    assert finish["open_id"] == "ou_1"
    assert finish["manage_url"] == "https://open.feishu.cn/app/cli_new"
    assert captured["create_only"] is True
    assert captured["source"] == "octop"
    assert "name" not in captured["app_preset"]
    assert "avatar" not in captured["app_preset"]
    assert sent["open_id"] == "ou_1"
    assert sent["greeting"] == "hello"
    # No addons: the scan page skips the extra scope-confirmation step.
    assert "addons" not in captured


def test_cmd_create_denied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_register(**_kwargs: Any) -> dict[str, Any]:
        raise AppAccessDeniedError("access_denied", "user cancelled")

    monkeypatch.setattr(creator.lark, "register_app", fake_register)
    with pytest.raises(SystemExit) as exc:
        creator.cmd_create()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload["action"] == "finish"
    assert payload["level"] == "error"
    assert "denied" in payload["message"].lower()


def test_register_feishu_app_rejects_none_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(creator.lark, "register_app", lambda **_kwargs: None)
    monkeypatch.setattr(creator, "_save_state", lambda _data: None)
    with pytest.raises(RegisterAppError, match=r"missing_credentials"):
        creator.register_feishu_app()


def test_cmd_create_register_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_register(**_kwargs: Any) -> dict[str, Any]:
        raise RegisterAppError("unsupported_auth_method", "client_secret missing")

    monkeypatch.setattr(creator.lark, "register_app", fake_register)
    with pytest.raises(SystemExit) as exc:
        creator.cmd_create()
    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["step"] == "create_app"


def test_parse_version() -> None:
    assert creator._parse_version("1.5.5") >= creator.MIN_LARK_OAPI
    assert creator._parse_version("1.5.4") < creator.MIN_LARK_OAPI
    assert creator._parse_version("1.7.0") >= creator.MIN_LARK_OAPI
