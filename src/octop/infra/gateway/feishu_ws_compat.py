"""Close Feishu connections when channels are stopped or replaced.

harness-gateway 0.9.7 calls stop(), which lark-oapi 1.7.3 does not provide.
Cancel the SDK receiver, close the socket, then release worker tasks and its loop.
Credential probes validate the token without opening another event receiver.
Remove the teardown patch when harness-gateway handles this lifecycle itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from harness_gateway.channel import ChannelCredentialsError, MessageProcessor

logger = logging.getLogger(__name__)

_PATCH_MARKER = "_octop_feishu_ws_stop_fix"
_STOP_TIMEOUT_SECONDS = 5.0


async def probe_feishu_credentials(config: dict[str, Any], processor: MessageProcessor) -> None:
    """Reuse token validation without registering a WebSocket event receiver."""
    from harness_gateway.channels.feishu import FeishuChannel, FeishuConfig

    channel_config = FeishuConfig.from_dict(config)
    missing = channel_config.missing_credentials()
    if missing:
        raise ChannelCredentialsError("feishu", missing)
    channel = FeishuChannel(processor, config=channel_config)
    try:
        await channel._refresh_token()
    finally:
        await channel._close_http()


def ensure_feishu_ws_stop_fix() -> bool:
    """Install the teardown patch once, unless the SDK provides stop()."""
    import lark_oapi as lark
    from harness_gateway.channels.feishu import FeishuChannel

    if getattr(FeishuChannel, _PATCH_MARKER, False) or hasattr(lark.ws.Client, "stop"):
        return False

    FeishuChannel._run_ws_thread = _fixed_run_ws_thread  # type: ignore[method-assign]
    FeishuChannel._stop_ws_client = _fixed_stop_ws_client  # type: ignore[method-assign]
    setattr(FeishuChannel, _PATCH_MARKER, True)
    return True


async def _run_ws_client(channel: Any) -> None:
    from lark_oapi.ws.exception import ClientException

    client = channel._ws_client
    receive = client._receive_message_loop

    async def receive_messages() -> None:
        channel._ws_receive_task = asyncio.current_task()
        await receive()

    client._receive_message_loop = receive_messages
    try:
        await client._connect()
    except ClientException:
        raise
    except Exception:
        await client._disconnect()
        if not client._auto_reconnect:
            raise
        await client._reconnect()
    await client._ping_loop()


async def _close_ws_client(client: Any, receive_task: asyncio.Task[Any] | None) -> None:
    if receive_task is not None:
        receive_task.cancel()
        await asyncio.gather(receive_task, return_exceptions=True)

    connection = client._conn
    try:
        async with asyncio.timeout(_STOP_TIMEOUT_SECONDS):
            await client._disconnect()
    except Exception:
        # A failed close handshake must not leave the socket alive after loop.close().
        if connection is not None:
            connection.transport.abort()
        logger.warning("Feishu WebSocket disconnect failed", exc_info=True)
    finally:
        # Legacy transports need their reader/close tasks alive during the handshake.
        tasks = asyncio.all_tasks() - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _fixed_run_ws_thread(self: Any) -> None:
    import lark_oapi.ws.client as ws_client_module

    client = self._ws_client
    try:
        with asyncio.Runner() as runner:
            loop = runner.get_loop()
            if client is None:
                return
            self._ws_receive_task = None
            task = loop.create_task(_run_ws_client(self))
            self._ws_task = task
            self._ws_loop = loop
            # stop() can run before the worker has published its loop.
            if not self._running:
                task.cancel()
            else:
                ws_client_module.loop = loop
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Feishu WebSocket thread failed")
            finally:
                client._auto_reconnect = False
                runner.run(_close_ws_client(client, self._ws_receive_task))
    finally:
        self._ws_client = None
        self._ws_loop = None
        self._ws_task = None
        self._ws_receive_task = None
        self._ws_thread = None
        self._ws_session_id = None


async def _fixed_stop_ws_client(self: Any) -> None:
    self._running = False
    client = self._ws_client
    if client is not None:
        client._auto_reconnect = False
    loop = getattr(self, "_ws_loop", None)
    task = getattr(self, "_ws_task", None)
    if loop is not None and task is not None:
        with contextlib.suppress(RuntimeError):  # worker may already have closed the loop
            loop.call_soon_threadsafe(task.cancel)

    thread = getattr(self, "_ws_thread", None)
    if thread is not None:
        await asyncio.get_running_loop().run_in_executor(
            None, thread.join, _STOP_TIMEOUT_SECONDS + 1.0
        )
        if thread.is_alive():
            # Keep references until the worker handles cancellation and finishes cleanup.
            logger.warning("Feishu WebSocket worker is still stopping")
