"""Live channel credential probes (WeChat iLink + Feishu).

Exercises the same ``ChannelManager.probe_channel`` path the dashboard uses
via ``Gateway.probe_config`` / ``POST …/channels/test`` — so a green result
means the real app credentials reach the real upstream.

Credentials come from the repo-root ``.env`` (loaded by ``tests/live/conftest.py``)
or from CI GitHub Secrets mapped in ``.github/workflows/ci.yml``. Missing vars
auto-skip that case so CI stays green when a channel is not configured.

Run locally::

    uv run pytest tests/live/test_channel_probe.py -m live -v
"""

from __future__ import annotations

import aiohttp
import pytest
from harness_gateway.channels.weixin.api import WeixinAPIClient
from harness_gateway.channels.weixin.types import WeixinAPIError
from harness_gateway.manager import ChannelManager
from tests.support.secrets import optional_env, require_env

pytestmark = pytest.mark.live

_DEFAULT_WEIXIN_BASE_URL = "https://ilinkai.weixin.qq.com"


async def _noop_processor(_msg: object) -> None:
    return None


@pytest.mark.asyncio
async def test_feishu_probe_accepts_app_credentials() -> None:
    """Feishu ``start()`` refreshes tenant_access_token — validates app id/secret."""
    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")

    manager = ChannelManager(processor=_noop_processor)
    await manager.probe_channel(
        "feishu",
        {"app_id": app_id, "app_secret": app_secret},
        tenant_id="live-probe",
        channel_id="live-feishu-probe",
    )


@pytest.mark.asyncio
async def test_weixin_ilink_token_accepted() -> None:
    """WeChat iLink getUpdates with a short poll validates bot token + UIN."""
    bot_uin = require_env("WEIXIN_BOT_UIN")
    token = require_env("WEIXIN_TOKEN")
    base_url = optional_env("WEIXIN_BASE_URL", _DEFAULT_WEIXIN_BASE_URL) or _DEFAULT_WEIXIN_BASE_URL

    # Product probe only starts the long-poll loop; hit getUpdates once so a
    # bad token fails the live test instead of silently succeeding.
    async with aiohttp.ClientSession() as session:
        client = WeixinAPIClient(base_url, token, session, timeout_s=20.0)
        try:
            await client.get_updates(sync_cursor="", timeout_ms=1000)
        except WeixinAPIError as exc:
            pytest.fail(
                f"weixin getUpdates rejected credentials "
                f"(bot_uin={bot_uin!r} base_url={base_url!r}): "
                f"ret={exc.ret} errcode={exc.errcode} errmsg={exc.errmsg}"
            )
        except (TimeoutError, aiohttp.ClientError) as exc:
            # GitHub-hosted runners often cannot finish iLink long-poll within
            # the client timeout; that is reachability, not a bad token.
            pytest.skip(f"weixin getUpdates unreachable ({base_url}): {exc}")

    manager = ChannelManager(processor=_noop_processor)
    try:
        await manager.probe_channel(
            "weixin",
            {
                "bot_uin": bot_uin,
                "token": token,
                "base_url": base_url,
                "account_id": bot_uin,
            },
            tenant_id="live-probe",
            channel_id="live-weixin-probe",
        )
    except (TimeoutError, aiohttp.ClientError) as exc:
        pytest.skip(f"weixin probe_channel unreachable ({base_url}): {exc}")
