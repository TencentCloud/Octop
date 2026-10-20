"""MQTT channel for IoT devices and robots."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import uuid
from dataclasses import dataclass
from typing import Any

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    InboundMessage,
    TextContent,
)

logger = logging.getLogger(__name__)


@dataclass
class MQTTConfig(ChannelConfig):
    """Configuration for MQTT channel.

    Attributes:
        host: MQTT broker hostname.
        port: Broker port (8883 for MQTT over TLS).
        transport: Paho transport — ``"tcp"`` or ``"websockets"``.
        username: Optional broker username.
        password: Optional broker password.
        subscribe_topic: Topic pattern to subscribe for inbound messages.
        publish_topic: Outbound topic template; ``{client_id}`` is substituted.
        clean_session: MQTT clean-session flag.
        qos: QoS level (0, 1, or 2).
        tls_enabled: Enable TLS for the broker connection.
        tls_ca_pem: PEM-encoded CA certificate string (inline).
        tls_ca_certs: Path to CA certificate file.
        tls_certfile: Optional client certificate file.
        tls_keyfile: Optional client private key file.
        show_thinking: Forward thinking/reasoning content to the device.
        show_tool_hints: Show tool-call status messages to the device.
    """

    host: str = ""
    port: int = 8883
    transport: str = "tcp"
    username: str = ""
    password: str = ""
    subscribe_topic: str = "devices/+/in"
    publish_topic: str = "devices/{client_id}/out"
    clean_session: bool = True
    qos: int = 2
    tls_enabled: bool = True
    tls_ca_pem: str = ""
    tls_ca_certs: str = ""
    tls_certfile: str = ""
    tls_keyfile: str = ""

    required_credentials = ("host",)


class MQTTChannel(BaseChannel):
    """MQTT channel using paho-mqtt in a background thread."""

    channel_type = "mqtt"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: MQTTConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: ChannelConstraints | None = None,
    ) -> None:
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            debounce_seconds=debounce_seconds,
            constraints=constraints,
            config=config,
        )
        self._config = config
        self._client: Any = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connection_session: str | None = None

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            send_rate_limit=(30, 60.0),
            show_thinking=False,
            show_tool_hints=True,
        )

    async def start(self) -> None:
        """Connect to the MQTT broker and subscribe."""
        if not self._config.host:
            raise RuntimeError("MQTTChannel: host is required")
        if not self._config.subscribe_topic or not self._config.publish_topic:
            raise RuntimeError("MQTTChannel: subscribe_topic and publish_topic are required")

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise ImportError("paho-mqtt is required for MQTTChannel. Install with: pip install paho-mqtt") from exc

        self._loop = asyncio.get_running_loop()
        client_id = f"harness-mqtt-{uuid.uuid4().hex[:12]}"
        self._connection_session = client_id

        self._client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined]
            transport=self._config.transport,  # type: ignore[arg-type]
            clean_session=self._config.clean_session,
        )

        if self._config.username:
            self._client.username_pw_set(self._config.username, self._config.password)

        if self._config.tls_enabled:
            ssl_context = ssl.create_default_context()
            if self._config.tls_ca_pem:
                ssl_context.load_verify_locations(cadata=self._config.tls_ca_pem)
            elif self._config.tls_ca_certs:
                ssl_context.load_verify_locations(cafile=self._config.tls_ca_certs)
            if self._config.tls_certfile:
                ssl_context.load_cert_chain(
                    certfile=self._config.tls_certfile or None,  # type: ignore[arg-type]
                    keyfile=self._config.tls_keyfile or None,
                )
            self._client.tls_set_context(ssl_context)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)

        try:
            self._client.connect(self._config.host, self._config.port, keepalive=60)
        except (OSError, ValueError):
            logger.exception("MQTT connect failed: %s:%s", self._config.host, self._config.port)
            raise

        self._client.loop_start()
        logger.info(
            "MQTTChannel started (host=%s port=%s tls=%s)",
            self._config.host,
            self._config.port,
            self._config.tls_enabled,
        )

    async def stop(self) -> None:
        """Disconnect from the MQTT broker."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected = False
        self._connection_session = None
        logger.info("MQTTChannel stopped")

    def _on_connect(
        self,
        client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        if reason_code == 0:
            self._connected = True
            client.subscribe(self._config.subscribe_topic, qos=self._config.qos)
            logger.info("MQTT connected, subscribed to %s", self._config.subscribe_topic)
        else:
            logger.error("MQTT connect failed, code=%s", reason_code)

    def _on_disconnect(
        self,
        _client: Any,
        _userdata: Any,
        _flags: Any,
        reason: Any,
        _properties: Any = None,
    ) -> None:
        self._connected = False
        if reason != 0:
            logger.warning("MQTT disconnected unexpectedly, code=%s", reason)

    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        """Paho callback (sync thread) — dispatch to asyncio via enqueue."""
        try:
            payload = msg.payload.decode("utf-8").strip()
            data: dict[str, Any] = {}
            try:
                data = json.loads(payload)
                content = str(data.get("text", ""))
            except json.JSONDecodeError:
                content = payload

            if not content:
                logger.debug("MQTT empty message on %s", msg.topic)
                return

            client_id = data.get("redirect_client_id")
            if not client_id:
                parts = msg.topic.split("/")
                if len(parts) >= 2:
                    client_id = parts[1]
            client_id = str(client_id or "unknown-client")

            native = {
                "topic": msg.topic,
                "client_id": client_id,
                "text": content,
                "raw_payload": payload,
            }

            if self._loop and self._enqueue_callback:
                self._loop.call_soon_threadsafe(self.enqueue, native)
            else:
                self.enqueue(native)
        except Exception:  # pylint: disable=broad-except
            # Paho invokes this callback on its network thread; isolate malformed messages.
            logger.exception("MQTT message handler error")

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        if not self._client or not self._connected or not text.strip():
            return
        client_id = subject.metadata.get("client_id") or subject.subject_id
        topic = self._config.publish_topic.format(client_id=client_id)
        self._client.publish(topic, text, qos=self._config.qos)
        logger.debug("MQTT published to %s (%d chars)", topic, len(text))

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        for part in parts:
            if isinstance(part, TextContent):
                await self._send_text(subject, part.text)
            else:
                await self._send_media(subject, part)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        label = self._get_media_label(media)
        url = self._get_media_url(media)
        has_inline = bool(getattr(media, "data", None) or getattr(media, "local_path", None))
        if url:
            await self._send_text(subject, f"[{label}: {url}]")
        elif has_inline:
            await self._send_text(subject, f"[{label} (local file, not deliverable on MQTT)]")

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse MQTT native dict into InboundMessage."""
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        data = raw_payload if isinstance(raw_payload, dict) else {}
        client_id = str(data.get("client_id") or "unknown-client")
        text = str(data.get("text") or "")
        topic = str(data.get("topic") or "")
        metadata = {
            "client_id": client_id,
            "topic": topic,
            "raw_payload": data.get("raw_payload", ""),
        }

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=client_id,
                chat_type="direct",
                metadata=metadata,
            ),
            channel_session_id=self._connection_session or f"{self.channel_id}-unconnected",
            content=[TextContent(text=text)] if text else [TextContent(text="")],
            metadata=metadata,
        )
