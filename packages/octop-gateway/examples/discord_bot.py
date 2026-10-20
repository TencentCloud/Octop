"""Echo bot: set DISCORD_BOT_TOKEN; all accessible guild channels are allowed by default."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from octop_gateway import ChannelManager, DiscordConfig, FileSystemMediaBackend, InboundMessage, MessageEvent


async def echo(message: InboundMessage) -> AsyncIterator[MessageEvent]:
    yield MessageEvent.text(message.text)
    yield MessageEvent.completed()


async def main() -> None:
    config = DiscordConfig.from_dict(
        {
            "bot_token": os.environ["DISCORD_BOT_TOKEN"],
            "allow_all_channels": os.getenv("DISCORD_ALLOW_ALL_CHANNELS", "true").lower() == "true",
            "allowed_channel_ids": os.getenv("DISCORD_ALLOWED_CHANNEL_IDS", ""),
            "allowed_user_ids": os.getenv("DISCORD_ALLOWED_USER_IDS", ""),
            "http_proxy": os.getenv("DISCORD_HTTP_PROXY", ""),
            "http_proxy_auth": os.getenv("DISCORD_HTTP_PROXY_AUTH", ""),
        }
    )
    manager = ChannelManager(processor=echo, media_backend=FileSystemMediaBackend("./discord-media"))
    await manager.start()
    try:
        await manager.add_discord_channel(config)
        await asyncio.Event().wait()
    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
