"""Example: MQTT bot (EMQX Cloud TLS)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from octop_gateway.channels.mqtt import MQTTConfig
from octop_gateway.manager import ChannelManager

load_dotenv()
logging.basicConfig(level=logging.INFO)

_DEFAULT_CA = """-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----"""


def _load_ca_pem() -> str:
    ca_file = os.getenv("MQTT_TLS_CA_FILE", "").strip()
    if ca_file and Path(ca_file).is_file():
        return Path(ca_file).read_text(encoding="utf-8")
    return _DEFAULT_CA


async def main() -> None:
    async def processor(msg):
        from octop_gateway.models import MessageEvent, TextContent

        user_text = msg.content[0].text if msg.content else ""  # type: ignore[union-attr]
        yield MessageEvent.message([TextContent(text=f"Echo: {user_text}")])
        yield MessageEvent.completed()

    manager = ChannelManager(processor=processor)
    await manager.start()
    await manager.add_mqtt_channel(
        MQTTConfig(
            host=os.getenv("MQTT_HOST", "c14633a9.ala.cn-shenzhen.emqxsl.cn"),
            port=int(os.getenv("MQTT_PORT", "8883")),
            username=os.getenv("MQTT_USERNAME", ""),
            password=os.getenv("MQTT_PASSWORD", ""),
            subscribe_topic=os.getenv("MQTT_SUBSCRIBE_TOPIC", "devices/+/in"),
            publish_topic=os.getenv("MQTT_PUBLISH_TOPIC", "devices/{client_id}/out"),
            tls_enabled=os.getenv("MQTT_TLS_ENABLED", "true").lower() == "true",
            tls_ca_pem=_load_ca_pem(),
            show_thinking=os.getenv("MQTT_SHOW_THINKING", "false").lower() == "true",
            show_tool_hints=os.getenv("MQTT_SHOW_TOOL_HINTS", "true").lower() == "true",
        )
    )
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
