"""Unit tests for Feishu scan-to-create (lark-oapi register_app)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from lark_oapi.scene.registration.errors import AppAccessDeniedError, RegisterAppError

from octop.infra.gateway.bot_creators import feishu_bot_creator as creator
from octop.infra.gateway.bot_creators.feishu_runner import extract_feishu_credentials


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


def _staging_files(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


@pytest.fixture()
def state_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "octop-feishu-bot-creator-state.json"
    monkeypatch.setattr(creator, "STATE_DIR", str(tmp_path))
    return path


def test_save_state_writes_the_created_app(state_path: Path) -> None:
    creator._save_state({"phase": "done", "app_id": "cli_1", "app_secret": "secret_1"})
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "phase": "done",
        "app_id": "cli_1",
        "app_secret": "secret_1",
    }
    assert _staging_files(state_path.parent) == []


def test_failed_save_keeps_the_previous_state(state_path: Path) -> None:
    creator._save_state({"phase": "create", "qr_url": "https://accounts.feishu.cn/qr"})
    before = state_path.read_text(encoding="utf-8")

    with pytest.raises(TypeError):
        creator._save_state({"phase": "done", "result": object()})

    assert state_path.read_text(encoding="utf-8") == before
    assert json.loads(before)["qr_url"] == "https://accounts.feishu.cn/qr"
    assert _staging_files(state_path.parent) == []


def test_save_state_does_not_follow_a_planted_symlink(state_path: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("important data", encoding="utf-8")
    try:
        os.symlink(victim, state_path)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"symlink not available: {exc}")

    creator._save_state({"phase": "done", "app_id": "cli_1"})

    assert victim.read_text(encoding="utf-8") == "important data"
    assert not state_path.is_symlink()
    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "phase": "done",
        "app_id": "cli_1",
    }


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
def test_state_file_is_not_world_readable(state_path: Path) -> None:
    creator._save_state({"phase": "done", "app_id": "cli_1", "app_secret": "secret_1"})
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
