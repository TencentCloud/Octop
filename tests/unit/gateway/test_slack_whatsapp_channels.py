"""Slack and WhatsApp channel registration, quote prompt, and webhook tests in Octop."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from typing import Any
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
    from octop_gateway.channels.slack import SlackChannel, SlackConfig
    from octop_gateway.channels.whatsapp import WhatsAppChannel, WhatsAppConfig
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
                                    "metadata": {"phone_number_id": "12345"},
                                    "messages": [
                                        {
                                            "id": "wamid.1",
                                            "from": "8613800001111",
                                            "type": "text",
                                            "text": {"body": "hello wa"},
                                        }
                                    ],
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


@pytest.mark.asyncio
async def test_whatsapp_webhook_route_fails_closed_without_extractor(tmp_path) -> None:
    """Public WhatsApp webhook route must never enqueue raw dicts if a channel lacks extract_webhook_messages."""
    enqueued: list[object] = []

    class _StubChannel:
        channel_type = "whatsapp"

        def verify_webhook_request(self, headers, raw_body, *, require_secret=True) -> bool:
            return True

        def enqueue(self, ev) -> None:
            enqueued.append(ev)

    gateway = _make_gateway(tmp_path)
    gateway._channel_manager = SimpleNamespace(
        get_channel=lambda cid: _StubChannel() if cid == "wa-stub" else None
    )
    fake_server = SimpleNamespace(app_runtime=SimpleNamespace(gateway=gateway))
    req = SimpleNamespace(
        headers={"X-Api-Key": "k"},
        body=AsyncMock(
            return_value=b'{"_format":"waha","payload":{"id":"m","from":"1@c.us","fromMe":false,"body":"hi"}}'
        ),
    )
    res = await whatsapp_webhook_ingest("wa-stub", req, server=fake_server)
    assert res == {"ok": True, "enqueued": 0}
    assert enqueued == []


@pytest.mark.asyncio
async def test_whatsapp_webhook_route_enforces_account_binding_and_rejects_normalized_payloads(
    tmp_path,
) -> None:
    """Route-level regression test: missing/mismatched accounts and pre-normalized payloads are rejected before
    identity updates, deduplication, or enqueueing across Cloud API, WAHA, and Evolution API."""
    from octop_gateway.channels.whatsapp import WhatsAppChannel, WhatsAppConfig

    async def processor(msg):
        yield MessageEvent.completed()

    def _make_channel(cfg: Any, cid: str) -> tuple[Any, list[dict[str, Any]]]:
        ch = WhatsAppChannel(processor, cfg, channel_id=cid)
        enqueued: list[dict[str, Any]] = []
        ch.enqueue = enqueued.append
        return ch, enqueued

    cloud_ch, cloud_enq = _make_channel(
        WhatsAppConfig(
            provider="cloud",
            access_token="EAAB",
            phone_number_id="PHONE_A",
            app_secret="shared_sec",
        ),
        "wa-cloud",
    )
    waha_ch, waha_enq = _make_channel(
        WhatsAppConfig(
            provider="waha",
            bridge_url="http://127.0.0.1:3000",
            bridge_api_key="shared_key",
            session_name="sales",
            use_websocket=False,
        ),
        "wa-waha",
    )
    waha_ch._self_jid = "8611100001111@c.us"
    waha_ch._self_lid = "11100001111@lid"

    evo_ch, evo_enq = _make_channel(
        WhatsAppConfig(
            provider="evolution",
            bridge_url="http://127.0.0.1:8080",
            bridge_api_key="shared_key",
            session_name="inst-a",
        ),
        "wa-evo",
    )
    evo_ch._self_jid = "8611100001111@s.whatsapp.net"

    channels = {"wa-cloud": cloud_ch, "wa-waha": waha_ch, "wa-evo": evo_ch}
    gateway = _make_gateway(tmp_path)
    gateway._channel_manager = SimpleNamespace(get_channel=lambda cid: channels.get(cid))
    fake_server = SimpleNamespace(app_runtime=SimpleNamespace(gateway=gateway))

    def _signed_cloud_req(payload: dict[str, object]) -> SimpleNamespace:
        raw = json.dumps(payload).encode("utf-8")
        sig = "sha256=" + hmac.new(b"shared_sec", raw, hashlib.sha256).hexdigest()
        return SimpleNamespace(
            headers={"X-Hub-Signature-256": sig}, body=AsyncMock(return_value=raw)
        )

    def _bridge_req(payload: dict[str, object], header_name: str = "X-Api-Key") -> SimpleNamespace:
        raw = json.dumps(payload).encode("utf-8")
        return SimpleNamespace(
            headers={header_name: "shared_key"}, body=AsyncMock(return_value=raw)
        )

    # 1. Cloud API: mismatched phone_number_id, missing metadata, and forged _format are all rejected
    cloud_msg = {
        "id": "wamid.ROUTE1",
        "from": "8613800001111",
        "type": "text",
        "text": {"body": "hi"},
    }
    for bad_cloud in (
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "PHONE_B"},
                                "messages": [cloud_msg],
                            }
                        }
                    ]
                }
            ]
        },
        {"entry": [{"changes": [{"value": {"messages": [cloud_msg]}}]}]},
        {"_format": "cloud", "metadata": {"phone_number_id": "PHONE_A"}, "message": cloud_msg},
    ):
        res = await whatsapp_webhook_ingest(
            "wa-cloud", _signed_cloud_req(bad_cloud), server=fake_server
        )
        assert res == {"ok": True, "enqueued": 0}
    assert cloud_enq == []
    assert "wamid.ROUTE1" not in cloud_ch._seen_messages
    assert cloud_ch.dropped_duplicate == 0

    good_cloud = {
        "entry": [
            {
                "changes": [
                    {"value": {"metadata": {"phone_number_id": "PHONE_A"}, "messages": [cloud_msg]}}
                ]
            }
        ]
    }
    assert await whatsapp_webhook_ingest(
        "wa-cloud", _signed_cloud_req(good_cloud), server=fake_server
    ) == {
        "ok": True,
        "enqueued": 1,
    }
    assert len(cloud_enq) == 1

    # 2. WAHA: forged normalized/raw payloads and mismatched/missing sessions are rejected without mutating self identity or dedup
    for bad_waha in (
        {
            "_format": "waha",
            "payload": {"id": "m", "from": "8613800001111@c.us", "fromMe": False, "body": "hello"},
        },
        {"id": "m", "from": "8613800001111@c.us", "fromMe": False, "body": "hello"},
        {
            "event": "message",
            "session": "support",
            "me": {"id": "8622200002222@c.us", "lid": "22200002222@lid"},
            "payload": {"id": "m", "from": "8613800001111@c.us", "fromMe": False, "body": "wrong"},
        },
        {
            "event": "message",
            "me": {"id": "8622200002222@c.us", "lid": "22200002222@lid"},
            "payload": {
                "id": "m",
                "from": "8613800001111@c.us",
                "fromMe": False,
                "body": "missing",
            },
        },
    ):
        res = await whatsapp_webhook_ingest("wa-waha", _bridge_req(bad_waha), server=fake_server)
        assert res == {"ok": True, "enqueued": 0}
    assert waha_enq == []
    assert waha_ch._self_jid == "8611100001111@c.us"
    assert waha_ch._self_lid == "11100001111@lid"
    assert "m" not in waha_ch._seen_messages
    assert waha_ch.dropped_duplicate == 0

    good_waha = {
        "event": "message",
        "session": "sales",
        "me": {"id": "8611100009999@c.us", "lid": "11100009999@lid"},
        "payload": {"id": "m", "from": "8613800001111@c.us", "fromMe": False, "body": "ok"},
    }
    assert await whatsapp_webhook_ingest("wa-waha", _bridge_req(good_waha), server=fake_server) == {
        "ok": True,
        "enqueued": 1,
    }
    assert len(waha_enq) == 1
    assert waha_ch._self_jid == "8611100009999@c.us"
    assert waha_ch._self_lid == "11100009999@lid"

    # 3. Evolution API: forged normalized/raw payloads and mismatched/missing instances are rejected
    evo_data = {
        "key": {"remoteJid": "8613800001111@s.whatsapp.net", "fromMe": False, "id": "evo1"},
        "message": {"conversation": "hello"},
    }
    for bad_evo in (
        {"_format": "evolution", "data": evo_data},
        evo_data,
        {
            "event": "messages.upsert",
            "instance": "inst-b",
            "sender": "86222@s.whatsapp.net",
            "data": evo_data,
        },
        {"event": "messages.upsert", "sender": "86222@s.whatsapp.net", "data": evo_data},
    ):
        res = await whatsapp_webhook_ingest(
            "wa-evo", _bridge_req(bad_evo, "apikey"), server=fake_server
        )
        assert res == {"ok": True, "enqueued": 0}
    assert evo_enq == []
    assert evo_ch._self_jid == "8611100001111@s.whatsapp.net"
    assert "evo1" not in evo_ch._seen_messages
    assert evo_ch.dropped_duplicate == 0

    good_evo = {
        "event": "messages.upsert",
        "instance": "inst-a",
        "sender": "8611100009999@s.whatsapp.net",
        "data": evo_data,
    }
    assert await whatsapp_webhook_ingest(
        "wa-evo", _bridge_req(good_evo, "apikey"), server=fake_server
    ) == {
        "ok": True,
        "enqueued": 1,
    }
    assert len(evo_enq) == 1
    assert evo_ch._self_jid == "8611100009999@s.whatsapp.net"
