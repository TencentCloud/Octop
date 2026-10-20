"""Harness Agent backend for octop-gateway.

Single class that wraps HarnessAgent.stream() to produce MessageEvent streams.

Usage:
    from backends.octop_harness import AgentBackend

    backend = AgentBackend(system_prompt="你是AI助手。")
    processor = backend.processor  # pass to channel constructor

Environment variables (loaded from .env):
    OPENAI_API_KEY      - API key
    OPENAI_BASE_URL     - API base (default: https://api.openai.com/v1)
    OPENAI_MODEL_NAME   - Model name (default: gpt-4o-mini)
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from enum import StrEnum
from pathlib import Path
from typing import Any

# Local development paths
for _p in ("/workspace/octop-harness/src", "/workspace/octop-memory/src"):
    if Path(_p).exists():
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

from octop_gateway import InboundMessage, MessageEvent  # noqa: E402
from octop_gateway.media import FileSystemMediaBackend, MediaBackend  # noqa: E402
from octop_gateway.models import (  # noqa: E402
    AudioContent,
    ContentPart,
    FileContent,
    ImageContent,
    MessageEventType,
    VideoContent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Media block schema understood by AgentBackend
# ---------------------------------------------------------------------------
#
# Tools (e.g. ``send_file_to_user``) may emit attachment blocks of the form::
#
#     {
#         "type": "image" | "audio" | "video" | "file",
#         "source": {
#             "type": "url" | "base64",
#             "url": "file:///abs/path/to/x.png" | "https://..." | "data:...",
#             "data": "<base64>",                  # only when source.type == "base64"
#             "media_type": "image/png",
#         },
#         "filename": "x.png",                      # optional
#     }
#
# These blocks live inside the messages of a ``tool_result`` stream event:
#
#     {"type": "tool_result", "node": "tools",
#      "messages": [{"role": "tool", "content": [<block>, ...]}]}
#
# AgentBackend translates each block into a :class:`ContentPart` and yields
# it as ``MessageEvent.MESSAGE`` so the channel's ``send_media`` handles
# delivery via :meth:`BaseChannel.load_media_bytes`.
# ---------------------------------------------------------------------------

_MEDIA_BLOCK_TYPES = {"image", "video", "audio", "file"}


class AgentEventType(StrEnum):
    """Stream event types emitted by HarnessAgent.stream().

    Each chunk yielded by the stream carries a ``"type"`` field matching one
    of these values.
    """

    TOKEN = "token"  # LLM text token (fields: content, node)
    REASONING = "reasoning"  # LLM thinking/reasoning token (fields: content, node)
    TOOL_CALL_CHUNK = "tool_call_chunk"  # Streamed tool-call fragment (fields: id, name, args, index, node)
    TOOL_RESULT = "tool_result"  # Tool execution result (fields: node, messages)
    STATE_UPDATE = "state_update"  # Node state change (fields: node, data)
    STATE_SNAPSHOT = "state_snapshot"  # Full state after step (field: data) — not mapped to IM
    CUSTOM = "custom"  # Custom event via get_stream_writer() (field: data) — not mapped to IM


class AgentBackend:
    """Wraps HarnessAgent into a MessageProcessor for octop-gateway.

    The processor calls agent.stream(request) which yields structured events:
        - ``token`` — text content from LLM (field: content, node)
        - ``reasoning`` — thinking/reasoning from LLM (field: content, node)
        - ``tool_call_chunk`` — streamed tool call fragment (field: id, name, args, index, node)
        - ``tool_result`` — tool execution result (field: node, messages)
        - ``state_update`` — node state change (field: node, data)
        - ``state_snapshot`` — full state after step (field: data)
        - ``custom`` — custom event from get_stream_writer() (field: data)

    Events are mapped to MessageEvent types for delivery through IM channels.

    Args:
        system_prompt: System prompt for the agent.
        agent_name: Workspace name for the agent.
        model: Model name override (reads OPENAI_MODEL_NAME if unset).
        media_backend: Backend used to materialize agent-produced files
            (e.g. local files referenced via ``file://`` URLs in tool results).
            Defaults to a FileSystemMediaBackend rooted at the same path the
            example ChannelManager uses.
    """

    def __init__(
        self,
        system_prompt: str = "你是一个友好的AI助手，回答简洁有用。",  # noqa: RUF001
        agent_name: str = "gateway-bot",
        model: str | None = None,
        media_backend: MediaBackend | None = None,
    ):
        from octop_harness import HarnessAgent
        from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

        root_dir = os.environ.get("HARNESS_AGENT_ROOT", str(Path.home() / ".octop-harness" / agent_name))
        Path(root_dir).mkdir(parents=True, exist_ok=True)

        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model_name = model or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")

        # MediaBackend used to resolve InboundMessage local_path values AND
        # to materialize outbound media blocks emitted by agent tools. If not
        # supplied, defaults to the same root used by the ChannelManager
        # examples so file lookups work transparently.
        self._media_backend = media_backend or FileSystemMediaBackend("/")

        self._agent = HarnessAgent(
            HarnessAgentConfig(
                name=agent_name,
                system_prompt=system_prompt,
                default_model=f"default/{model_name}",
                providers=[
                    ProviderConfig(
                        id="default",
                        base_url=base_url,
                        api_key=api_key,
                        name="default",
                        models=[ModelConfig(id=model_name, input=["text", "image"])],
                    )
                ],
            )
        )

    @property
    def agent(self):
        """The underlying HarnessAgent instance."""
        return self._agent

    async def processor(self, msg: InboundMessage) -> AsyncIterator[MessageEvent]:
        """MessageProcessor: stream agent response as MessageEvents.

        Maps octop-harness stream events to MessageEvent types:
            token         → delta (accumulated, flushed on node change)
            reasoning     → thinking_delta
            tool_call_chunk → tool_start (on first chunk with name)
            tool_result   → tool_end + (optional) media MESSAGE events
            state_update  → flush on node change
        """
        # Echo the incoming InboundMessage so operators can see exactly what
        # the bridge handed to the agent (channel, identity, parts, text).
        logger.info(
            "processor received msg: channel_id=%s channel_type=%s tenant=%s sender=%s session=%s text=%r parts=%d",
            msg.channel_id,
            msg.channel_type,
            msg.tenant_id,
            msg.channel_subject,
            msg.channel_session_id,
            msg.text,
            len(msg.content),
        )

        yield MessageEvent.typing()

        try:
            request = await self._build_request(msg)
        except Exception as e:  # pylint: disable=broad-except
            # Harness request construction crosses host and plugin extension boundaries.
            logger.exception("Failed to build request")
            yield MessageEvent.error_event(f"Agent error: {e}")
            yield MessageEvent.completed()
            return

        try:
            current_node: str | None = None
            # LangChain ``ToolCallChunk.name`` is non-None on the first chunk
            # of a call and None / empty afterwards — but in practice some
            # providers split the *name itself* across chunks ("send_file_t"
            # then "o_user"). We buffer name fragments per call ``index``
            # (the merge key LangChain itself uses; ``id`` is None on every
            # chunk after the first) and only emit ``tool_start`` once the
            # name is complete (heuristic: when the first ``args`` fragment
            # arrives — provider-side, args never start before the name has
            # stabilised).
            tool_name_buf: dict[str, str] = {}
            tool_started: set[str] = set()
            active_tool_id: str | None = None

            async for chunk in self._agent.stream(request):
                # Debug: dump every raw stream chunk from octop-harness
                # (token / reasoning / tool_call_chunk / tool_result / ...).
                # Use print() rather than logger so it is visible without
                # configuring logging in the host bot script.
                event_type = chunk.get("type", "")

                if event_type == AgentEventType.TOKEN:
                    node = chunk.get("node", "")
                    # Flush accumulated content when node changes
                    if current_node is not None and node != current_node:
                        yield MessageEvent.flush()
                    current_node = node
                    content = chunk.get("content", "")
                    if content:
                        yield MessageEvent.delta(content)

                elif event_type == AgentEventType.REASONING:
                    content = chunk.get("content", "")
                    if content:
                        yield MessageEvent.thinking_delta(content)

                elif event_type == AgentEventType.TOOL_CALL_CHUNK:
                    # LangChain merges ``ToolCallChunk`` by ``index``: only the
                    # first chunk of a call carries ``id`` and ``name``;
                    # subsequent chunks set both to ``None`` and just extend
                    # ``args`` (see ``langchain_core.messages.tool.ToolCallChunk``
                    # docstring: "Chunks are only merged if their values of
                    # ``index`` are equal and not ``None``"). Keying state by
                    # ``id`` would split the buffer between "call_xxx" (first
                    # chunk) and "_idx_0" (subsequent chunks), so ``tool_result``
                    # would later look up an empty entry and fall back to the
                    # literal string "tool". Use ``index`` as the stable key.
                    print(f"[agent.stream chunk] {chunk!r}", flush=True)
                    tc_key = f"_idx_{chunk.get('index', 0)}"
                    active_tool_id = tc_key
                    name_frag = chunk.get("name") or ""
                    args_frag = chunk.get("args") or ""
                    if name_frag:
                        tool_name_buf[tc_key] = tool_name_buf.get(tc_key, "") + name_frag
                    # Defer tool_start until args start arriving — by then
                    # the name buffer is complete. This avoids emitting a
                    # truncated tool name like "send_file_t" when the
                    # provider splits it across chunks.
                    if args_frag and tc_key not in tool_started and tool_name_buf.get(tc_key):
                        tool_started.add(tc_key)
                        yield MessageEvent.tool_start(tool_name_buf[tc_key])

                elif event_type == AgentEventType.TOOL_RESULT:
                    node = chunk.get("node", "")
                    # Resolve the final tool name from the buffered fragments.
                    final_name = tool_name_buf.get(active_tool_id or "", "") or "tool"
                    if active_tool_id:
                        # No-arg tools never trigger the args-based emit
                        # above, so synthesise tool_start here just before
                        # tool_end.
                        if active_tool_id not in tool_started:
                            tool_started.add(active_tool_id)
                            yield MessageEvent.tool_start(final_name)
                        yield MessageEvent.tool_end(final_name)
                        # Clean up per-id state so a long session does not
                        # accumulate dead entries.
                        tool_name_buf.pop(active_tool_id, None)
                        tool_started.discard(active_tool_id)
                        active_tool_id = None
                    # Surface any media attachments produced by the tool
                    # (e.g. send_file_to_user → image block) as MESSAGE events.
                    async for media_event in self._media_events_from_tool_result(chunk):
                        yield media_event
                    # Node produced tool results — flush on next token node change
                    current_node = node

                elif event_type == AgentEventType.STATE_UPDATE:
                    node = chunk.get("node", "")
                    # State update from a different node triggers flush
                    if current_node is not None and node != current_node:
                        yield MessageEvent.flush()
                    current_node = node

                # STATE_SNAPSHOT and CUSTOM are ignored (no IM mapping)

        except Exception as e:  # pylint: disable=broad-except
            # Agent implementations may surface provider- or plugin-specific failures.
            logger.exception("agent.stream failed")
            yield MessageEvent.error_event(f"Agent error: {e}")

        yield MessageEvent.completed()

    # ------------------------------------------------------------------
    # Internal: outbound block → ContentPart
    # ------------------------------------------------------------------

    async def _media_events_from_tool_result(self, chunk: dict[str, Any]) -> AsyncIterator[MessageEvent]:
        """Walk a ``tool_result`` chunk's messages and yield MESSAGE events
        for any attachment blocks found.

        ``ToolMessage.content`` may take several shapes depending on how
        LangChain wrapped the tool's return value:

          * ``list[dict]`` — explicit multimodal content (e.g. when the
            tool was declared with ``response_format="content_and_artifact"``
            or returned a list of blocks).
          * ``str`` — a JSON-serialised representation of the original
            return value. This is the **default** behaviour: when a
            ``@tool``-decorated function returns a ``dict``, LangChain
            stringifies it into the ``content`` field. We re-parse it
            and accept either a single block dict or a list of blocks.
          * Anything else — skipped.

        Block format (see module docstring) is matched loosely so future
        additions like ``thumbnail`` / ``alt_text`` survive without code
        changes here.
        """
        messages = chunk.get("messages") or []
        if not isinstance(messages, list):
            return

        for message in messages:
            for block in self._iter_media_blocks(self._extract_message_content(message)):
                try:
                    part = await self._block_to_content_part(block)
                except FileNotFoundError as exc:
                    logger.warning("tool_result media block: file missing: %s", exc)
                    continue
                except Exception:  # pylint: disable=broad-except
                    # MediaBackend implementations may raise backend-specific errors.
                    logger.exception("tool_result media block: failed to resolve")
                    continue
                if part is None:
                    continue
                yield MessageEvent(type=MessageEventType.MESSAGE, content=[part])

    @staticmethod
    def _extract_message_content(message: Any) -> Any:
        """Pull ``content`` out of a tool message (dict or LangChain object)."""
        if isinstance(message, dict):
            return message.get("content")
        return getattr(message, "content", None)

    @staticmethod
    def _iter_media_blocks(content: Any) -> list[dict[str, Any]]:
        """Yield candidate media blocks out of a ToolMessage content payload.

        Accepts ``list[dict]`` directly and ``str`` after a JSON parse.
        Returns only blocks whose ``type`` matches a known media kind so
        callers can iterate without re-checking.
        """
        candidates: list[Any]
        if isinstance(content, list):
            candidates = content
        elif isinstance(content, str):
            stripped = content.strip()
            if not stripped or stripped[0] not in "{[":
                return []
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                return []
            if isinstance(parsed, dict):
                candidates = [parsed]
            elif isinstance(parsed, list):
                candidates = parsed
            else:
                return []
        else:
            return []

        out: list[dict[str, Any]] = []
        for block in candidates:
            if isinstance(block, dict) and block.get("type") in _MEDIA_BLOCK_TYPES:
                out.append(block)
        return out

    async def _block_to_content_part(self, block: dict[str, Any]) -> ContentPart | None:
        """Convert a media block to a ContentPart.

        Source handling:
          - ``base64`` source → bind the payload to ``ContentPart.data``
            directly (no extra encode/decode trip; channels read it via
            ``load_media_bytes``).
          - ``file://`` URL → materialize into MediaBackend, set
            ``local_path``. If the source already lives under a
            ``FileSystemMediaBackend`` root, its existing relative path is
            reused without copying.
          - ``http(s)://`` / ``data:`` URL → set ``url`` directly.
        """
        btype = block.get("type")
        if btype not in _MEDIA_BLOCK_TYPES:
            return None

        source = block.get("source") or {}
        src_type = source.get("type") or ""
        raw_url = source.get("url", "") or ""
        mime = source.get("media_type") or ""
        filename = block.get("filename") or ""

        local_path: str | None = None
        url_field = ""
        data_field: str | None = None

        if src_type == "base64":
            payload = source.get("data", "") or ""
            if not payload:
                return None
            data_field = payload
        elif raw_url.startswith("file://"):
            local_path = await self._materialize_to_backend(raw_url, filename, mime)
            if local_path is None:
                return None
        elif raw_url:
            url_field = raw_url
        else:
            return None

        if btype == "image":
            return ImageContent(
                url=url_field,
                local_path=local_path,
                data=data_field,
                mime_type=mime or None,
            )
        if btype == "video":
            return VideoContent(
                url=url_field,
                local_path=local_path,
                data=data_field,
                mime_type=mime or None,
            )
        if btype == "audio":
            return AudioContent(
                url=url_field,
                local_path=local_path,
                data=data_field,
                mime_type=mime or None,
            )
        if btype == "file":
            return FileContent(
                url=url_field,
                local_path=local_path,
                data=data_field,
                filename=filename,
                mime_type=mime or None,
            )
        return None

    async def _materialize_to_backend(
        self,
        file_url: str,
        filename: str,
        mime: str,
    ) -> str | None:
        """Resolve ``file://`` URL into a MediaBackend key.

        If the file already sits under a ``FileSystemMediaBackend`` root, the
        existing relative path is returned without copying. Otherwise the
        bytes are read and saved under a deterministic agent-output key.
        Returns None if the source path does not exist.
        """
        backend = self._media_backend
        if backend is None:
            raise RuntimeError("AgentBackend has no MediaBackend configured")

        parsed = urllib.parse.urlparse(file_url)
        src_path = Path(urllib.request.url2pathname(parsed.path))
        if not src_path.is_file():
            raise FileNotFoundError(file_url)

        # Fast path: already inside a filesystem backend root → reuse key.
        if isinstance(backend, FileSystemMediaBackend):
            try:
                rel = src_path.resolve().relative_to(backend.root_path.resolve())
                return rel.as_posix()
            except ValueError:
                pass  # outside the root, fall through to copy

        # Slow path: copy bytes into the backend under a deterministic key.
        ext = Path(filename or src_path.name).suffix
        if not ext and mime:
            ext = mimetypes.guess_extension(mime.split(";", 1)[0].strip()) or ""
        stem = Path(filename or src_path.name).stem or "attachment"
        key = f"agent_outbound/{int(time.time())}_{stem}{ext}"
        await backend.save(src_path.read_bytes(), key)
        return key

    # ------------------------------------------------------------------
    # Internal: inbound message → request payload
    # ------------------------------------------------------------------

    async def _build_request(self, msg: InboundMessage) -> dict[str, Any]:
        """Build a ChatRequest-compatible dict from InboundMessage."""
        content = await self._build_content(msg)

        # Log what we're sending to the LLM. We emit LangChain v1 standard
        # multimodal blocks (``{type: image, base64, mime_type}`` /
        # ``{type: image, url}``); the provider-specific transport shape
        # is produced by langchain-* at API-call time.
        if isinstance(content, list):
            img_blocks = [b for b in content if b.get("type") == "image"]
            for b in img_blocks:
                if b.get("base64"):
                    logger.info(
                        "Sending image to LLM: base64 (%d chars, mime=%s)",
                        len(b["base64"]),
                        b.get("mime_type", "?"),
                    )
                elif b.get("url"):
                    logger.info("Sending image to LLM: url=%s", b["url"][:80])

        # String → pass directly; list → wrap in HumanMessage
        if isinstance(content, list):
            from langchain_core.messages import HumanMessage

            messages = [HumanMessage(content=content)]
        else:
            messages = content

        return {
            "messages": messages,
            "thread_id": msg.channel_subject.subject_id,
            "user": msg.channel_subject.subject_id,
            "source": f"gateway/{msg.channel_type or msg.channel_id}",
        }

    async def _build_content(self, msg: InboundMessage) -> str | list[dict[str, Any]]:
        """Convert InboundMessage to LLM input (text or multimodal blocks).

        Emits **LangChain v1 standard data blocks** rather than provider-
        specific transport shapes. For images, that's
        ``{type: "image", base64, mime_type}`` (when we have the bytes
        locally) or ``{type: "image", url}`` (for remote URLs).

        Why standard blocks and not OpenAI's ``image_url``:

        * They round-trip through every provider's converter
          (``langchain_openai`` → ``image_url``, ``langchain_anthropic``
          → ``source: {type: base64, ...}``, etc.) so the same payload
          works on Anthropic / Bedrock / Gemini, not just OpenAI.
        * octop-harness's ``MediaOffloadMiddleware`` recognises this
          shape and offloads large images out of the conversation
          history after the first turn, keeping long threads cheap.
          (It also supports OpenAI ``image_url`` blocks as a tolerated
          legacy form, but standard blocks are the canonical input.)

        Resolves ``local_path`` (a MediaBackend key, not a filesystem
        path) through the configured backend so the LLM gets the actual
        bytes inline.
        """
        text = msg.text or ""
        images: list[dict[str, Any]] = []

        for part in msg.content:
            if not isinstance(part, ImageContent):
                continue
            data = await self._read_backend_key(part.local_path) if part.local_path else None
            if data is not None:
                mime = part.mime_type or mimetypes.guess_type(part.local_path or "")[0] or "image/png"
                b64 = base64.b64encode(data).decode()
                images.append({"type": "image", "base64": b64, "mime_type": mime})
            elif part.url:
                images.append({"type": "image", "url": part.url})

        if not images:
            return text or "[空消息]"

        blocks: list[dict[str, Any]] = [{"type": "text", "text": text or "用户发送了图片："}]  # noqa: RUF001
        blocks.extend(images)
        return blocks

    async def _read_backend_key(self, key: str) -> bytes | None:
        """Read a MediaBackend key, returning None when the key is missing."""
        if not key or self._media_backend is None:
            return None
        try:
            return await self._media_backend.read(key)
        except FileNotFoundError:
            return None


# ---------------------------------------------------------------------------
# Backward-compatible factory (used by feishu_bot, all_channels, etc.)
# ---------------------------------------------------------------------------


def create_processor(
    system_prompt: str = "你是一个友好的AI助手，回答简洁有用。",  # noqa: RUF001
    agent_name: str = "gateway-bot",
    model: str | None = None,
    streaming: bool = True,
    media_backend: MediaBackend | None = None,
):
    """Create a processor function (backward-compatible).

    Args:
        streaming: Ignored — AgentBackend always streams token-by-token.
        media_backend: MediaBackend to share with the host ChannelManager.
            **Highly recommended**: pass the same instance to both this
            function and ``ChannelManager(media_backend=...)`` so files
            materialised by tools (``send_file_to_user`` etc.) land at
            keys the channels can read through ``load_media_bytes``.
            If omitted, a default ``FileSystemMediaBackend`` is created
            and the operator must pass that same default to the
            ChannelManager — otherwise outbound media will fail with
            "no MediaBackend is configured".
    """
    backend = AgentBackend(
        system_prompt=system_prompt,
        agent_name=agent_name,
        model=model,
        media_backend=media_backend,
    )
    return backend.processor
