"""Channel manager: orchestrates multiple channels with session-aware batching."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from octop_gateway.channel import BaseChannel, MessageProcessor
from octop_gateway.media import FileSystemMediaBackend, MediaBackend
from octop_gateway.models import ChannelSubject, ContentPart, InboundMessage

if TYPE_CHECKING:
    from octop_gateway.channels.dingtalk import DingTalkConfig
    from octop_gateway.channels.discord import DiscordConfig
    from octop_gateway.channels.feishu import FeishuConfig
    from octop_gateway.channels.mqtt import MQTTConfig
    from octop_gateway.channels.qq import QQConfig
    from octop_gateway.channels.telegram import TelegramConfig
    from octop_gateway.channels.wecom import WeComConfig
    from octop_gateway.channels.weixin.channel import WeixinConfig
    from octop_gateway.channels.xiaoyi import XiaoyiConfig
    from octop_gateway.channels.yuanbao import YuanbaoConfig

logger = logging.getLogger(__name__)

# Optional hook invoked before the per-session lock is acquired. Used by Octop
# to signal ``/stop`` / ``/cancel`` without waiting for the in-flight turn.
PreLockHandler = Callable[[str, InboundMessage], Awaitable[None]]
MessagePredicate = Callable[[InboundMessage], bool]
T = TypeVar("T")


def _config_class_for(channel_cls: type[BaseChannel]) -> type | None:
    """Resolve the ``config`` dataclass type from a channel's ``__init__`` hint.

    Returns ``None`` when the channel does not declare a typed ``config``
    parameter (so the caller passes the raw dict through unchanged).
    """
    import inspect
    import typing

    try:
        hints = typing.get_type_hints(channel_cls.__init__)
    except (AttributeError, NameError, TypeError, ValueError):
        hints = {}
    resolved = hints.get("config")
    if resolved is None:
        param = inspect.signature(channel_cls.__init__).parameters.get("config")
        if param is None or param.annotation is inspect.Parameter.empty:
            return None
        resolved = param.annotation

    args = getattr(resolved, "__args__", None)
    if args:  # Optional[Cfg] / Cfg | None → first non-None member
        for arg in args:
            if arg is not type(None):
                resolved = arg
                break

    return resolved if isinstance(resolved, type) else None


class ChannelManager:
    """Orchestrates multiple IM channels with:

    - Per-channel message queues
    - Configurable worker pool per channel
    - Session-aware sequential processing (same session → no interleaving)
    - Cross-session parallelism
    - Proactive push API

    Usage (config-based, recommended):
        manager = ChannelManager(processor=my_processor)
        await manager.start()
        channel_id = await manager.add_channel(
            channel_type="feishu",
            config={"app_id": "...", "app_secret": "..."},
            tenant_id="tenant1",
        )

    Usage (legacy, passing channel instances directly):
        manager = ChannelManager({"feishu": feishu_channel})
        await manager.start()
    """

    def __init__(
        self,
        channels: dict[str, BaseChannel] | None = None,
        workers_per_channel: int = 4,
        queue_maxsize: int = 1000,
        media_backend: MediaBackend | None = None,
        constraints: dict[str, Any] | None = None,
        processor: MessageProcessor | None = None,
        on_pre_lock: PreLockHandler | None = None,
        control_message_predicate: MessagePredicate | None = None,
        interrupt_message_predicate: MessagePredicate | None = None,
    ) -> None:
        self._channels: dict[str, BaseChannel] = channels or {}
        self._workers_per_channel = workers_per_channel
        self._queue_maxsize = queue_maxsize
        self._media_backend = media_backend
        self._global_constraints = constraints or {}
        self._default_processor = processor
        self._on_pre_lock = on_pre_lock
        self._control_message_predicate = control_message_predicate
        self._interrupt_message_predicate = interrupt_message_predicate

        # Per-channel queues and workers
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._interrupt_tasks: set[asyncio.Task[None]] = set()

        # Session locking: prevent same-session messages from being processed
        # concurrently across workers
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._running = False

        # Store event loop reference for thread-safe enqueue
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_pre_lock_handler(self, handler: PreLockHandler | None) -> None:
        """Install or clear the pre-session-lock inbound hook."""
        self._on_pre_lock = handler

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def start(self) -> None:
        """Start all channels and their consumer worker loops."""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        # Fall back to a filesystem backend rooted at "/" when the caller did
        # not supply one — this mirrors the behaviour channels would otherwise
        # need to implement themselves and avoids hard failures on first media.
        if not self._media_backend:
            self._media_backend = FileSystemMediaBackend("/")

        # Propagate media backend to all channels
        for channel in self._channels.values():
            channel.set_media_backend(self._media_backend)

        # Apply global constraint overrides to all channels
        if self._global_constraints:
            self._apply_constraints(self._global_constraints)

        # Initialize queues and set enqueue callbacks
        for channel_id, channel in self._channels.items():
            queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._queue_maxsize)
            self._queues[channel_id] = queue
            channel.set_enqueue_callback(
                lambda payload, cid=channel_id: self.enqueue(cid, payload)  # type: ignore[misc]
            )

        # Start all channels
        for channel_id, channel in self._channels.items():
            try:
                await channel.start()
                logger.info("Channel started: %s", channel_id)
            except Exception:  # pylint: disable=broad-except
                # Channel adapters are independent failure domains during startup.
                logger.exception("Failed to start channel: %s", channel_id)

        # Spawn workers
        for channel_id in self._channels:
            for i in range(self._workers_per_channel):
                task = asyncio.create_task(
                    self._worker_loop(channel_id),
                    name=f"gateway-worker-{channel_id}-{i}",
                )
                self._workers.append(task)

        logger.info(
            "ChannelManager started: %d channels, %d workers each",
            len(self._channels),
            self._workers_per_channel,
        )

    async def stop(self) -> None:
        """Stop all channels and cancel worker tasks."""
        if not self._running:
            return

        self._running = False

        # Cancel workers
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        for task in list(self._interrupt_tasks):
            task.cancel()
        if self._interrupt_tasks:
            await asyncio.gather(*self._interrupt_tasks, return_exceptions=True)
        self._interrupt_tasks.clear()

        # Stop channels
        for channel_id, channel in self._channels.items():
            try:
                await channel.stop()
                logger.info("Channel stopped: %s", channel_id)
            except Exception:  # pylint: disable=broad-except
                # Best-effort shutdown must continue across independent adapters.
                logger.exception("Failed to stop channel: %s", channel_id)

        self._queues.clear()
        self._session_locks.clear()
        logger.info("ChannelManager stopped")

    # =========================================================================
    # Constraints
    # =========================================================================

    def set_constraints(self, **kwargs: Any) -> None:
        """Update constraints on ALL channels at runtime.

        Applies given keyword arguments to each channel's constraints object.
        Only known ChannelConstraints fields are applied; unknown keys are ignored.

        Usage:
            manager.set_constraints(show_thinking=True, show_tool_hints=False)

        Args:
            **kwargs: ChannelConstraints fields to update (e.g. show_thinking, show_tool_hints).
        """
        self._global_constraints.update(kwargs)
        self._apply_constraints(kwargs)

    def _apply_constraints(self, overrides: dict[str, Any]) -> None:
        """Apply constraint overrides to all registered channels."""
        for channel in self._channels.values():
            for key, value in overrides.items():
                if hasattr(channel.constraints, key):
                    setattr(channel.constraints, key, value)

    # =========================================================================
    # Enqueue
    # =========================================================================

    def enqueue(self, channel_id: str, payload: Any) -> None:
        """Enqueue a raw payload for processing by the channel's workers.

        Thread-safe: uses call_soon_threadsafe so it can be called from
        non-asyncio threads (e.g. lark-oapi WebSocket thread, wecom-sdk thread).
        """
        queue = self._queues.get(channel_id)
        if queue is None:
            logger.warning("No queue for channel %s, dropping payload", channel_id)
            return

        # Use stored loop for thread-safe enqueue
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._put_to_queue, queue, channel_id, payload)
        else:
            # Fallback: direct put (same thread)
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.error("Queue full for channel %s, dropping payload", channel_id)

    def _put_to_queue(self, queue: asyncio.Queue, channel_id: str, payload: Any) -> None:  # type: ignore[type-arg]
        """Thread-safe helper: put payload into queue from the event loop thread."""
        queued_payload = payload
        channel = self._channels.get(channel_id)
        if channel is not None and self._interrupt_message_predicate is not None:
            try:
                message = channel.parse_inbound(payload)
            except Exception:  # pylint: disable=broad-except
                # Preserve the existing worker error path for malformed payloads.
                message = None
            if message is not None and self._interrupt_message_predicate(message):
                task = asyncio.create_task(
                    self._run_interrupt(channel_id, channel, message),
                    name=f"gateway-interrupt-{channel_id}",
                )
                self._interrupt_tasks.add(task)
                task.add_done_callback(self._interrupt_tasks.discard)
                return
            if message is not None:
                queued_payload = message
        try:
            queue.put_nowait(queued_payload)
        except asyncio.QueueFull:
            logger.error("Queue full for channel %s, dropping payload", channel_id)

    async def _run_interrupt(
        self,
        channel_id: str,
        channel: BaseChannel,
        message: InboundMessage,
    ) -> None:
        """Process an urgent control message without waiting for the session lock."""
        try:
            await channel.handle_inbound(message)
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            # An urgent control message must not terminate the interrupt worker.
            logger.exception("Interrupt worker error: channel=%s", channel_id)

    # =========================================================================
    # Proactive push API
    # =========================================================================

    async def push_text(
        self,
        channel_id: str,
        subject: ChannelSubject,
        text: str,
    ) -> None:
        """Push a text message proactively via a specific channel."""
        channel = self._channels.get(channel_id)
        if not channel:
            raise ValueError(f"Channel not found: {channel_id}")
        await channel.push_text(subject, text)

    async def push_content(
        self,
        channel_id: str,
        subject: ChannelSubject,
        parts: list[ContentPart],
    ) -> None:
        """Push rich content proactively via a specific channel."""
        channel = self._channels.get(channel_id)
        if not channel:
            raise ValueError(f"Channel not found: {channel_id}")
        await channel.push_message(subject, parts)

    async def run_in_session(
        self,
        channel_id: str,
        session_key: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Run a proactive operation under the inbound session lock.

        Hosts use this when an out-of-band action, such as a scheduled turn,
        must not interleave with inbound processing for the same channel
        session.
        """
        if channel_id not in self._channels:
            raise ValueError(f"Channel not found: {channel_id}")
        key = session_key.strip()
        if not key:
            raise ValueError("session_key must not be empty")
        async with self._session_lock(channel_id, key):
            return await operation()

    # =========================================================================
    # Channel management
    # =========================================================================

    def get_channel(self, channel_id: str) -> BaseChannel | None:
        """Get a channel by its ID."""
        return self._channels.get(channel_id)

    async def add_channel(
        self,
        channel_type_or_instance: str | BaseChannel | None = None,
        config: dict[str, Any] | Any | None = None,
        *,
        channel_type: str | None = None,
        tenant_id: str | None = None,
        processor: MessageProcessor | None = None,
        channel_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a channel dynamically.

        Preferred usage (config-based):
            channel_id = await manager.add_channel(
                channel_type="feishu",
                config={"app_id": "...", "app_secret": "..."},
                tenant_id="tenant1",
            )

        Or passing the Config dataclass directly — with tenant_id embedded
        (since all Config classes inherit ChannelConfig)::

            channel_id = await manager.add_channel(
                channel_type="feishu",
                config=FeishuConfig(app_id="cli_xxx", app_secret="yyy", tenant_id="acme"),
            )

        Legacy usage (passing a channel instance):
            channel_id = await manager.add_channel(feishu_channel_instance)

        Args:
            channel_type_or_instance: Either a channel type string (e.g. "feishu")
                or an existing BaseChannel instance (legacy).
            config: Channel configuration dict or Config dataclass instance.

                **Feishu** (``channel_type="feishu"``, :class:`~octop_gateway.channels.feishu.FeishuConfig`)::

                    config = {
                        "app_id":             "cli_xxxx",   # required — Feishu App ID
                        "app_secret":         "secret",     # required — Feishu App Secret
                        "verification_token": "",           # optional — HTTP callback token
                        "encrypt_key":        "",           # optional — event encryption key
                    }

                **WeCom** (``channel_type="wecom"``, :class:`~octop_gateway.channels.wecom.WeComConfig`)::

                    config = {
                        "bot_id": "xxxx",   # required — AI Bot ID from WeCom admin console
                        "secret": "yyyy",   # required — bot secret for authentication
                        "ws_url": "",       # optional — custom WebSocket URL
                    }

                **QQ** (``channel_type="qq"``, :class:`~octop_gateway.channels.qq.QQConfig`)::

                    config = {
                        "app_id":  "1234567",   # required — QQ Bot application ID
                        "token":   "xxxx",      # required — bot token for authentication
                        "secret":  "yyyy",      # required — app secret for signature verification
                        "sandbox": False,       # optional — use sandbox endpoint
                        "intents": None,        # optional — event subscription bitmask
                    }

                **DingTalk** (``channel_type="dingtalk"``, :class:`~octop_gateway.channels.dingtalk.DingTalkConfig`)::

                    config = {
                        "app_key":    "dingxxx",  # required — Client ID
                        "app_secret": "yyyy",     # required — Client Secret
                        "robot_code": "",         # optional — robot code; defaults to app_key
                    }

                **WeChat/Weixin** (``channel_type="weixin"``,
                :class:`~octop_gateway.channels.weixin.channel.WeixinConfig`)::

                    config = WeixinConfig(accounts=[
                        WeixinAccountConfig(account_id="xxx", token="yyy"),
                    ])
                    # Or as a dict (only top-level string fields; use WeixinConfig object for accounts):
                    config = {"media_dir": "~/.harness/media"}

                **Yuanbao** (``channel_type="yuanbao"``, :class:`~octop_gateway.channels.yuanbao.YuanbaoConfig`)::

                    config = {
                        "app_key":    "xxxx",  # required — Yuanbao bot App Key
                        "app_secret": "yyyy",  # required — Yuanbao bot App Secret
                        "api_domain": "https://bot.yuanbao.tencent.com",
                        "ws_url":     "wss://bot-wss.yuanbao.tencent.com/wss/connection",
                        "route_env":  "",      # optional — internal routing environment
                    }

                    Rich media uses the manager's ``MediaBackend`` to load
                    ``ContentPart.data`` / ``local_path`` / ``url`` bytes, then
                    the Yuanbao channel uploads them to Yuanbao COS before send.

            channel_type: Channel type string (alternative keyword form).
            tenant_id: Optional tenant identifier for multi-tenant deployments.
                Overrides ``config.tenant_id`` when both are provided.
            processor: Message processor override (falls back to manager default).
            channel_id: Optional explicit channel ID (UUID generated if omitted).
                Overrides ``config.channel_id`` when both are provided.
            **kwargs: Extra keyword args forwarded to the channel constructor
                (e.g. ``debounce_seconds``, ``constraints``).

        Returns:
            The channel_id (UUID string) used as the cache key.

        Raises:
            ValueError: If a channel with the same ID already exists, or if
                channel type is unknown or no processor is available.
        """
        # --- Resolve effective channel_type string ---
        if isinstance(channel_type_or_instance, str):
            channel_type = channel_type_or_instance
        elif isinstance(channel_type_or_instance, BaseChannel):
            # Legacy: channel instance passed directly
            return await self._register_channel(channel_type_or_instance)

        if channel_type is None:
            raise ValueError(
                "channel_type is required. Pass it as the first positional argument "
                "or as channel_type= keyword argument."
            )

        # --- Resolve processor ---
        effective_processor = processor or self._default_processor
        if effective_processor is None:
            raise ValueError(
                "No processor available. Either pass processor= to add_channel() "
                "or set a default processor via ChannelManager(processor=...)."
            )

        # --- Build + instantiate (shared with probe_channel) ---
        from octop_gateway.channel import ChannelConfig as _ChannelConfig
        from octop_gateway.channel import ChannelCredentialsError
        from octop_gateway.channels import BUILTIN_CHANNELS

        if channel_type not in BUILTIN_CHANNELS:
            raise ValueError(f"Unknown channel_type '{channel_type}'. Available: {sorted(BUILTIN_CHANNELS.keys())}")

        channel_config = self._build_config(BUILTIN_CHANNELS[channel_type], config or {})
        if isinstance(channel_config, _ChannelConfig):
            missing = channel_config.missing_credentials()
            if missing:
                raise ChannelCredentialsError(channel_type, missing)

        channel = self._instantiate_channel(
            channel_type,
            channel_config,
            processor=effective_processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            **kwargs,
        )
        return await self._register_channel(channel)

    def _instantiate_channel(
        self,
        channel_type: str,
        config: Any,
        *,
        processor: MessageProcessor,
        channel_id: str | None,
        tenant_id: str | None,
        **kwargs: Any,
    ) -> BaseChannel:
        """Build a channel Config (if a dict was given) and construct the channel.

        Single construction path used by both :meth:`add_channel` and
        :meth:`probe_channel`; does not register on the manager.
        """
        from octop_gateway.channel import ChannelConfig as _ChannelConfig
        from octop_gateway.channels import BUILTIN_CHANNELS

        if channel_type not in BUILTIN_CHANNELS:
            raise ValueError(f"Unknown channel_type '{channel_type}'. Available: {sorted(BUILTIN_CHANNELS.keys())}")

        channel_cls = BUILTIN_CHANNELS[channel_type]
        channel_config = self._build_config(channel_cls, config)

        if isinstance(channel_config, _ChannelConfig):
            effective_channel_id = channel_id or channel_config.channel_id or uuid.uuid4().hex
            effective_tenant_id = tenant_id or channel_config.tenant_id
        else:
            effective_channel_id = channel_id or uuid.uuid4().hex
            effective_tenant_id = tenant_id

        return channel_cls(
            processor,
            config=channel_config,
            channel_id=effective_channel_id,
            tenant_id=effective_tenant_id,
            **kwargs,
        )

    def _build_config(self, channel_cls: type[BaseChannel], config: Any) -> Any:
        """Convert a dict config into the channel's Config dataclass via ``from_dict``."""
        if not isinstance(config, dict):
            return config
        config_cls = _config_class_for(channel_cls)
        if config_cls is None:
            return config
        try:
            return config_cls.from_dict(config)  # type: ignore[attr-defined]
        except Exception as exc:  # pylint: disable=broad-except
            # Adapter-defined config factories may use different validation libraries.
            raise ValueError(f"Failed to build config for {channel_cls.__name__}: {exc}") from exc

    async def probe_channel(
        self,
        channel_type: str,
        config: dict[str, Any],
        *,
        tenant_id: str | None = None,
        channel_id: str | None = None,
        processor: MessageProcessor | None = None,
    ) -> None:
        """Start/stop an ephemeral channel instance to verify credentials.

        Raises:
            ChannelCredentialsError: when required credentials are missing
                (checked before any network connection is attempted).
            ValueError: when the channel type is unknown or config is malformed.
        """
        from octop_gateway.channel import ChannelConfig as _ChannelConfig
        from octop_gateway.channel import ChannelCredentialsError
        from octop_gateway.channels import BUILTIN_CHANNELS

        effective_processor = processor or self._default_processor
        if effective_processor is None:
            raise ValueError(
                "No processor available. Either pass processor= to probe_channel() "
                "or set a default processor via ChannelManager(processor=...)."
            )

        if channel_type not in BUILTIN_CHANNELS:
            raise ValueError(f"Unknown channel_type '{channel_type}'. Available: {sorted(BUILTIN_CHANNELS.keys())}")

        probe_config = dict(config)
        if channel_type == "yuanbao" and not probe_config.get("probe_mode"):
            # Yuanbao appears to allow only one effective bot WebSocket session.
            # Opening a second full connection for a UI probe can kick the live
            # channel offline, so probe credentials via sign-token only.
            probe_config["probe_mode"] = "sign_token"

        channel_config = self._build_config(BUILTIN_CHANNELS[channel_type], probe_config)
        if isinstance(channel_config, _ChannelConfig):
            missing = channel_config.missing_credentials()
            if missing:
                raise ChannelCredentialsError(channel_type, missing)

        channel = self._instantiate_channel(
            channel_type,
            channel_config,
            processor=effective_processor,
            channel_id=channel_id or "__probe__",
            tenant_id=tenant_id,
        )
        if self._media_backend:
            channel.set_media_backend(self._media_backend)
        try:
            await channel.start()
        finally:
            await channel.stop()

    async def _register_channel(self, channel: BaseChannel) -> str:
        """Register a channel instance, start it, and spawn workers. Returns channel_id."""
        channel_id = channel.channel_id
        if channel_id in self._channels:
            raise ValueError(f"Channel already exists: {channel_id}")

        self._channels[channel_id] = channel
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._queues[channel_id] = queue
        channel.set_enqueue_callback(lambda payload, cid=channel_id: self.enqueue(cid, payload))  # type: ignore[misc]

        # Propagate media backend to new channel
        if self._media_backend:
            channel.set_media_backend(self._media_backend)

        # Apply existing global constraints to the new channel
        if self._global_constraints:
            for key, value in self._global_constraints.items():
                if hasattr(channel.constraints, key):
                    setattr(channel.constraints, key, value)

        if self._running:
            try:
                await channel.start()
            except BaseException:
                # A failed login must not leave a registered, workerless channel.
                self._channels.pop(channel_id, None)
                self._queues.pop(channel_id, None)
                try:
                    await channel.stop()
                except Exception:  # pylint: disable=broad-except
                    # Preserve the original startup error if adapter cleanup also fails.
                    logger.warning("Channel cleanup failed after startup failure: %s", channel_id)
                raise
            for i in range(self._workers_per_channel):
                task = asyncio.create_task(
                    self._worker_loop(channel_id),
                    name=f"gateway-worker-{channel_id}-{i}",
                )
                self._workers.append(task)

        logger.info(
            "Channel registered: id=%s type=%s tenant=%s",
            channel_id,
            channel.channel_type,
            channel.tenant_id,
        )
        return channel_id

    async def remove_channel(self, channel_id: str) -> None:
        """Dynamically remove a channel (stops it and cancels its workers)."""
        channel = self._channels.pop(channel_id, None)
        if not channel:
            return

        self._queues.pop(channel_id, None)

        # Cancel workers for this channel
        remaining: list[asyncio.Task[None]] = []
        for task in self._workers:
            if task.get_name().startswith(f"gateway-worker-{channel_id}-"):
                task.cancel()
            else:
                remaining.append(task)
        self._workers = remaining

        await channel.stop()

    @property
    def channel_ids(self) -> list[str]:
        """Return list of registered channel IDs."""
        return list(self._channels.keys())

    # =========================================================================
    # Worker loop
    # =========================================================================

    async def _worker_loop(self, channel_id: str) -> None:
        """Worker loop: drain queue, batch same-session, process sequentially."""
        queue = self._queues.get(channel_id)
        channel = self._channels.get(channel_id)
        if not queue or not channel:
            return

        while self._running:
            try:
                # Wait for next payload
                payload = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                # Parse to get session key for locking
                message = payload if isinstance(payload, InboundMessage) else channel.parse_inbound(payload)
                session_key = channel.get_debounce_key(message)

                # Drain additional same-session items from queue
                batch = [message]
                is_control = self._control_message_predicate is not None and self._control_message_predicate(message)
                if not is_control and channel.should_batch_inbound(message):
                    batch.extend(self._drain_same_session(queue, channel, session_key))

                # Merge batch if multiple
                merged = channel.merge_inbound(batch) if len(batch) > 1 else batch[0]

                # Allow hosts (Octop) to act before the session lock — e.g. signal
                # cancel for /stop so the in-flight turn can release the lock.
                if self._on_pre_lock is not None:
                    try:
                        await self._on_pre_lock(channel_id, merged)
                    except Exception:  # pylint: disable=broad-except
                        # Host hooks are isolated from the channel worker.
                        logger.exception("pre-lock handler error: channel=%s", channel_id)

                # Acquire session lock to prevent interleaving
                # Native IDs are only unique inside one registered channel.
                # Prefix the shared lock registry to avoid cross-account or
                # cross-platform collisions.
                async with self._session_lock(channel_id, session_key):
                    # Use handle_inbound which includes delta accumulation,
                    # rate limiting, timeout guard, and typing keepalive
                    await channel.handle_inbound(merged)

            except asyncio.CancelledError:
                break
            except Exception:  # pylint: disable=broad-except
                # One malformed payload or adapter failure must not stop the worker.
                logger.exception("Worker error: channel=%s", channel_id)

    def _session_lock(self, channel_id: str, session_key: str) -> asyncio.Lock:
        """Return the shared lock for one registered-channel session."""
        lock_key = f"{channel_id}:{session_key}"
        return self._session_locks.setdefault(lock_key, asyncio.Lock())

    def _drain_same_session(
        self,
        queue: asyncio.Queue[Any],
        channel: BaseChannel,
        session_key: str,
    ) -> list[InboundMessage]:
        """Non-blocking drain of same-session items from queue."""
        drained: list[InboundMessage] = []
        max_drain = 20  # Prevent unbounded draining

        for _ in range(max_drain):
            try:
                payload = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                msg = payload if isinstance(payload, InboundMessage) else channel.parse_inbound(payload)
                if self._control_message_predicate is not None and self._control_message_predicate(msg):
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        logger.warning("Queue full when re-enqueuing control message, dropping")
                    break
                if channel.get_debounce_key(msg) == session_key:
                    drained.append(msg)
                else:
                    # Different session, put it back
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        logger.warning("Queue full when re-enqueuing, dropping")
                    break
            except Exception:  # pylint: disable=broad-except
                # Parsing is adapter-defined; stop draining and preserve queued payloads.
                logger.exception("Failed to parse payload during drain")
                break

        return drained

    # =========================================================================
    # User Registry
    # =========================================================================

    def list_subjects(self, channel_id: str) -> list[Any]:
        """List known users for a specific channel."""
        channel = self._channels.get(channel_id)
        if channel is None:
            return []
        return channel.list_subjects()

    def list_all_users(self) -> dict[str, list[Any]]:
        """List known users across all channels."""
        return {cid: ch.list_subjects() for cid, ch in self._channels.items()}

    async def push_to_all(self, channel_id: str, text: str) -> None:
        """Push a text message to all known subjects of a channel."""
        channel = self._channels.get(channel_id)
        if channel is None:
            raise ValueError(f"Channel not found: {channel_id}")
        for subject in channel.list_subjects():
            try:
                await channel.push_text(subject, text)
            except Exception:  # pylint: disable=broad-except
                # Continue fan-out when one platform subject rejects a push.
                logger.warning("Failed to push to subject %s on %s", subject.subject_id, channel_id)

    # =========================================================================
    # Convenience channel methods
    # =========================================================================

    async def add_feishu_channel(
        self,
        config: FeishuConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a Feishu (Lark) channel.

        Shorthand for ``add_channel(channel_type="feishu", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.feishu.FeishuConfig` instance.
                Set ``config.tenant_id`` to enable multi-tenant session isolation.
            processor: Optional processor override; falls back to the manager default.
            **kwargs: Extra kwargs forwarded to the channel constructor
                (e.g. ``debounce_seconds``, ``constraints``).

        Returns:
            The ``channel_id`` (UUID hex) used as the registration key.

        Example::

            from octop_gateway.channels.feishu import FeishuConfig

            ch_id = await manager.add_feishu_channel(
                FeishuConfig(app_id="cli_xxx", app_secret="yyy", tenant_id="acme")
            )
        """
        return await self.add_channel("feishu", config, processor=processor, **kwargs)

    async def add_wecom_channel(
        self,
        config: WeComConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a WeCom (Enterprise WeChat) channel.

        Shorthand for ``add_channel(channel_type="wecom", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.wecom.WeComConfig` instance.
            processor: Optional processor override.
            **kwargs: Extra kwargs forwarded to the channel constructor.

        Returns:
            The ``channel_id`` (UUID hex).

        Example::

            from octop_gateway.channels.wecom import WeComConfig

            ch_id = await manager.add_wecom_channel(
                WeComConfig(bot_id="xxx", secret="yyy")
            )
        """
        return await self.add_channel("wecom", config, processor=processor, **kwargs)

    async def add_qq_channel(
        self,
        config: QQConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a QQ Bot channel.

        Shorthand for ``add_channel(channel_type="qq", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.qq.QQConfig` instance.
            processor: Optional processor override.
            **kwargs: Extra kwargs forwarded to the channel constructor.

        Returns:
            The ``channel_id`` (UUID hex).

        Example::

            from octop_gateway.channels.qq import QQConfig

            ch_id = await manager.add_qq_channel(
                QQConfig(app_id="1234567", token="xxx", secret="yyy")
            )
        """
        return await self.add_channel("qq", config, processor=processor, **kwargs)

    async def add_dingtalk_channel(
        self,
        config: DingTalkConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a DingTalk channel.

        Shorthand for ``add_channel(channel_type="dingtalk", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.dingtalk.DingTalkConfig` instance.
            processor: Optional processor override.
            **kwargs: Extra kwargs forwarded to the channel constructor.

        Returns:
            The ``channel_id`` (UUID hex).

        Example::

            from octop_gateway.channels.dingtalk import DingTalkConfig

            ch_id = await manager.add_dingtalk_channel(
                DingTalkConfig(app_key="dingxxx", app_secret="yyy")
            )
        """
        return await self.add_channel("dingtalk", config, processor=processor, **kwargs)

    async def add_weixin_channel(
        self,
        config: WeixinConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a WeChat (iLink) channel.

        Shorthand for ``add_channel(channel_type="weixin", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.weixin.channel.WeixinConfig` instance.
            processor: Optional processor override.
            **kwargs: Extra kwargs forwarded to the channel constructor.

        Returns:
            The ``channel_id`` (UUID hex).

        Example::

            from octop_gateway.channels.weixin import WeixinConfig, WeixinAccountConfig

            ch_id = await manager.add_weixin_channel(
                WeixinConfig(accounts=[WeixinAccountConfig(account_id="xxx", token="yyy")])
            )
        """
        return await self.add_channel("weixin", config, processor=processor, **kwargs)

    async def add_yuanbao_channel(
        self,
        config: YuanbaoConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a Tencent Yuanbao channel.

        Shorthand for ``add_channel(channel_type="yuanbao", config=config, ...)``.

        Args:
            config: :class:`~octop_gateway.channels.yuanbao.YuanbaoConfig` instance.
            processor: Optional processor override.
            **kwargs: Extra kwargs forwarded to the channel constructor.

        Returns:
            The ``channel_id`` (UUID hex).

        Example::

            from octop_gateway.channels.yuanbao import YuanbaoConfig

            ch_id = await manager.add_yuanbao_channel(
                YuanbaoConfig(app_key="xxx", app_secret="yyy")
            )

        Yuanbao rich media is still routed through this manager/channel path:
        the channel reads bytes via the active ``MediaBackend`` and performs
        Yuanbao COS upload privately before delivering TIM media elements.
        """
        return await self.add_channel("yuanbao", config, processor=processor, **kwargs)

    async def add_xiaoyi_channel(
        self,
        config: XiaoyiConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a XiaoYi (Huawei OpenClaw) channel."""
        return await self.add_channel("xiaoyi", config, processor=processor, **kwargs)

    async def add_mqtt_channel(
        self,
        config: MQTTConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add an MQTT channel for IoT / robot messaging."""
        return await self.add_channel("mqtt", config, processor=processor, **kwargs)

    async def add_telegram_channel(
        self,
        config: TelegramConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a Telegram Bot channel."""
        return await self.add_channel("telegram", config, processor=processor, **kwargs)

    async def add_discord_channel(
        self,
        config: DiscordConfig,
        *,
        processor: MessageProcessor | None = None,
        **kwargs: Any,
    ) -> str:
        """Add a Discord Bot channel (Gateway WebSocket)."""
        return await self.add_channel("discord", config, processor=processor, **kwargs)
