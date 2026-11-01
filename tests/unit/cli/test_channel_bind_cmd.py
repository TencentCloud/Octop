"""Re-binding a channel must keep the config keys it does not touch."""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from octop.cli.commands import channel as channel_cmd
from octop.infra.errors import ErrorCode, OctopError


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the offline channel store and the QR helpers; capture the patch call."""
    import octop.cli.support.offline_ops as offline_ops
    import octop.cli.support.qr as qr_support
    from octop.infra.gateway.channels import qr_bind

    state: dict[str, Any] = {"config": None}

    monkeypatch.setattr(channel_cmd, "require_agent", lambda _agent_id: "agent-1")
    monkeypatch.setattr(channel_cmd, "_resolve_user", lambda _aid, _as_user: 7)
    monkeypatch.setattr(qr_support, "render_qrcode_terminal", lambda _url: None)

    def fake_get_channel(_aid: str, channel_id: str) -> dict[str, Any]:
        if channel_id not in state:
            raise OctopError(ErrorCode.NOT_FOUND, f"channel {channel_id!r} not found")
        return {"id": channel_id, "config": dict(state[channel_id])}

    def fake_patch_channel(
        _aid: str,
        channel_id: str,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        state["config"] = config
        return {"id": channel_id, "enabled": enabled}

    monkeypatch.setattr(offline_ops, "get_channel_offline", fake_get_channel)
    monkeypatch.setattr(offline_ops, "patch_channel_offline", fake_patch_channel)

    async def wecom_generate() -> dict[str, Any]:
        return {"scode": "sc-1", "auth_url": "https://wecom/qr"}

    async def wecom_poll(_scode: str) -> dict[str, Any]:
        return {"status": "success", "bot_id": "new-bot", "secret": "new-secret"}

    async def weixin_generate() -> dict[str, Any]:
        return {"qrcode_token": "tok-1", "qrcode_url": "https://weixin/qr"}

    async def weixin_poll(_token: str) -> dict[str, Any]:
        return {"status": "success", "account_id": "acc-new", "token": "session-token"}

    monkeypatch.setattr(qr_bind, "wecom_qr_generate", wecom_generate)
    monkeypatch.setattr(qr_bind, "wecom_qr_poll", wecom_poll)
    monkeypatch.setattr(qr_bind, "weixin_qr_generate", weixin_generate)
    monkeypatch.setattr(qr_bind, "weixin_qr_poll", weixin_poll)
    return state


def test_wecom_rebind_keeps_existing_display_config(offline: dict[str, Any]) -> None:
    channel_id = "ch-wecom"
    offline[channel_id] = {
        "bot_id": "old-bot",
        "secret": "old-secret",
        "enabled": True,
        "response_mode": "invoke",
        "show_thinking": True,
    }
    result = CliRunner().invoke(
        channel_cmd.channel,
        ["bind", "wecom", "--agent", "agent-1", "--channel-id", channel_id],
    )
    assert result.exit_code == 0, result.output
    cfg = offline["config"]
    assert cfg["bot_id"] == "new-bot"
    assert cfg["secret"] == "new-secret"
    assert cfg["response_mode"] == "invoke"
    assert cfg["show_thinking"] is True


def test_weixin_rebind_keeps_existing_display_config(offline: dict[str, Any]) -> None:
    channel_id = "ch-weixin"
    offline[channel_id] = {
        "response_mode": "invoke",
        "show_tool_hints": True,
        "accounts": [{"account_id": "acc-old", "configured": True}],
    }
    result = CliRunner().invoke(
        channel_cmd.channel,
        ["bind", "weixin", "--agent", "agent-1", "--channel-id", channel_id],
    )
    assert result.exit_code == 0, result.output
    cfg = offline["config"]
    assert cfg["accounts"] == [
        {
            "account_id": "acc-new",
            "token": "session-token",
            "base_url": "https://ilink.b.qq.com",
            "bot_uin": "acc-new",
            "configured": True,
        }
    ]
    assert cfg["response_mode"] == "invoke"
    assert cfg["show_tool_hints"] is True
