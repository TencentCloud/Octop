"""Slack and WhatsApp channel registration, quote prompt, and webhook tests in Octop."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent
from tests.unit.gateway.test_gateway_runtime_status import _make_gateway

from octop.api.deps import is_jwt_exempt_path
from octop.api.routers.channels import (
    slack_webhook_ingest,
    whatsapp_webhook_ingest,
    whatsapp_webhook_verify,
)
from octop.infra.gateway.gateway import ChannelCreateSpec, ChannelKind
from octop.infra.gateway.process.harness_request import build_content_from_message


def test_webhook_paths_are_jwt_exempt() -> None:
    assert is_jwt_exempt_path("/api/channels/webhook/whatsapp/ch-1") is True
    assert is_jwt_exempt_path("/api/channels/webhook/slack/ch-1") is True


def test_whatsapp_bridge_qr_body_rejects_non_http_url() -> None:
    from pydantic import ValidationError

    from octop.api.routers.channels import WhatsAppBridgeQrBody

    valid = WhatsAppBridgeQrBody(bridge_url="http://127.0.0.1:3000")
    assert valid.bridge_url == "http://127.0.0.1:3000"
    with pytest.raises(ValidationError):
        WhatsAppBridgeQrBody(bridge_url="file:///etc/passwd")


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", ["slack", "whatsapp", "discord", "feishu", "wecom"])
async def test_quote_context_injected_for_new_and_enhanced_channels(channel_type: str) -> None:
    msg = InboundMessage(
        channel_id="ch-1",
        channel_type=channel_type,
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="sub-1", chat_type="direct"),
        content=[TextContent(text="What does this mean?")],
        metadata={"reply_quote_text": "Earlier quoted sentence"},
    )
    rendered = await build_content_from_message(msg, locale="en")
    assert isinstance(rendered, str)
    assert (
        "[Quoted message]\nEarlier quoted sentence\n\n[Current message]\nWhat does this mean?"
        in rendered
    )


@pytest.mark.asyncio
async def test_slack_and_whatsapp_gateway_registration_and_webhooks(tmp_path, monkeypatch) -> None:
    slack_mod = pytest.importorskip("octop_gateway.channels.slack")
    wa_mod = pytest.importorskip("octop_gateway.channels.whatsapp")
    SlackChannel = slack_mod.SlackChannel
    SlackConfig = slack_mod.SlackConfig
    WhatsAppChannel = wa_mod.WhatsAppChannel
    WhatsAppConfig = wa_mod.WhatsAppConfig
    from octop_gateway.manager import ChannelManager
    from octop_gateway.media import FileSystemMediaBackend

    async def processor(msg):
        yield MessageEvent.completed()

    monkeypatch.setattr(SlackChannel, "start", AsyncMock())
    monkeypatch.setattr(SlackChannel, "stop", AsyncMock())
    monkeypatch.setattr(WhatsAppChannel, "start", AsyncMock())
    monkeypatch.setattr(WhatsAppChannel, "stop", AsyncMock())

    gateway = _make_gateway(tmp_path)
    manager = ChannelManager(
        processor=processor, media_backend=FileSystemMediaBackend(str(tmp_path))
    )
    gateway._channel_manager = manager
    gateway._processor = MagicMock()

    slack_row = SimpleNamespace(
        channel_id="slack1",
        agent_id="agent1",
        kind="slack",
        config_json=json.dumps(
            {"bot_token": "xoxb-1", "app_token": "xapp-1", "signing_secret": "ssec"}
        ),
    )
    wa_row = SimpleNamespace(
        channel_id="wa1",
        agent_id="agent1",
        kind="whatsapp",
        config_json=json.dumps(
            {
                "provider": "cloud",
                "access_token": "EAAB",
                "phone_number_id": "12345",
                "verify_token": "vtok",
                "app_secret": "asec",
            }
        ),
    )
    wa_waha_row = SimpleNamespace(
        channel_id="wa_waha",
        agent_id="agent1",
        kind="whatsapp",
        config_json=json.dumps({"provider": "waha", "bridge_url": "http://127.0.0.1:3000"}),
    )

    await manager.start()
    try:
        await gateway._register_channel(slack_row)
        await gateway._register_channel(wa_row)
        await gateway._register_channel(wa_waha_row)

        slack_ch = manager.get_channel("slack1")
        wa_ch = manager.get_channel("wa1")
        waha_ch = manager.get_channel("wa_waha")
        assert isinstance(slack_ch, SlackChannel)
        assert isinstance(slack_ch._config, SlackConfig)
        assert isinstance(wa_ch, WhatsAppChannel)
        assert isinstance(wa_ch._config, WhatsAppConfig)
        assert isinstance(waha_ch, WhatsAppChannel)
        assert waha_ch.provider == "waha"
        assert ChannelCreateSpec("slack1", "agent1", 1, ChannelKind.SLACK, "Slack").kind == "slack"
        assert (
            ChannelCreateSpec("wa1", "agent1", 1, ChannelKind.WHATSAPP, "WhatsApp").kind
            == "whatsapp"
        )

        fake_server = SimpleNamespace(app_runtime=SimpleNamespace(gateway=gateway))

        # Test WhatsApp GET webhook verify
        resp = await whatsapp_webhook_verify(
            "wa1",
            hub_mode="subscribe",
            hub_verify_token="vtok",
            hub_challenge="chal_123",
            server=fake_server,
        )
        assert resp.body == b"chal_123"

        # Test WhatsApp POST webhook ingest with HMAC signature
        wa_body = json.dumps(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "id": "wamid.1",
                                            "from": "8613800001111",
                                            "type": "text",
                                            "text": {"body": "hello wa"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ).encode("utf-8")
        wa_sig = "sha256=" + hmac.new(b"asec", wa_body, hashlib.sha256).hexdigest()
        wa_req = SimpleNamespace(
            headers={"X-Hub-Signature-256": wa_sig},
            body=AsyncMock(return_value=wa_body),
        )
        wa_res = await whatsapp_webhook_ingest("wa1", wa_req, server=fake_server)
        assert wa_res == {"ok": True, "enqueued": 1}

        # Test Slack POST webhook url_verification with signature
        ts_str = str(int(time.time()))
        slack_body = json.dumps({"type": "url_verification", "challenge": "slack_chal"}).encode(
            "utf-8"
        )
        slack_sig = (
            "v0="
            + hmac.new(
                b"ssec", f"v0:{ts_str}:{slack_body.decode()}".encode(), hashlib.sha256
            ).hexdigest()
        )
        slack_req = SimpleNamespace(
            headers={"X-Slack-Request-Timestamp": ts_str, "X-Slack-Signature": slack_sig},
            body=AsyncMock(return_value=slack_body),
        )
        slack_res = await slack_webhook_ingest("slack1", slack_req, server=fake_server)
        assert slack_res == {"challenge": "slack_chal"}
    finally:
        await manager.stop()
