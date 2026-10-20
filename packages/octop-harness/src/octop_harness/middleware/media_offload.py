"""``MediaOffloadMiddleware`` — keep large media out of long-running threads.

Why
---
LangChain v1 multimodal messages embed binary payloads inline as base64
in their ``content_blocks`` — e.g. an inbound user image lands in
``HumanMessage.content`` as ``{type: "image", base64, mime_type}``, and
``deepagents.read_file`` produces the same shape from a backend file.

Once such a block is in the conversation history, **every subsequent
turn re-sends those bytes to the model**:

* a 1.5 MiB PNG → ~520 K tokens, sent every turn the message survives;
* prompt cache invalidates from that point onward (cache is prefix-keyed);
* token budget rapidly exhausts on multi-turn chats with images.

deepagents' built-in eviction (``human_message_token_limit_before_evict``,
``tool_token_limit_before_evict``) **doesn't help here** — both call
``_extract_text_from_message`` which deliberately ignores non-text
blocks, on the grounds that "binary payloads shouldn't inflate the size
measurement". So images and audio are excluded from eviction triggers
*and* from the offloaded-to-disk text. They just sit there.

What this middleware does
-------------------------
Run on every ``before_model``:

1. Walk every message's ``content_blocks``. Find blocks shaped like
   ``{type: "image"|"audio", base64: "<b64>", mime_type: "<m>"}`` whose
   payload is at least ``min_bytes`` of decoded data.
2. **First time** we see a given block (no ``_offload_sha`` marker yet):
   - hash the bytes;
   - write them to ``{offload_prefix}/<sha>.<ext>`` via the backend's
     ``upload_files`` (binary-safe; we never base64-round-trip text);
   - tag the *block* with ``_offload_sha`` and ``_offload_path`` markers
     and store the marked block back on the message;
   - **leave the base64 in place** so the model sees the original bytes
     this turn (otherwise it would never get to "see" the image at all).
3. **Subsequent turns**: any block already tagged is replaced with a
   text block of the form
   ``[image: <sha>.<ext> @ /<path>; size=<n>B; mime=<m>; use read_file
   to view]``. The model now spends a few dozen tokens instead of
   hundreds of thousands, and can pull the bytes back via ``read_file``
   on demand.

Determinism / dedupe
--------------------
SHA-256 of the raw bytes is the cache key. The same image attached to
two turns lands at the same path, gets the same placeholder text, and
benefits from prompt-cache reuse.

Size threshold
--------------
The default ``min_bytes`` is 4 KiB: small icons, emoji-sized PNGs, and
short audio cues stay inline because round-tripping them through a
``read_file`` call costs more (in tokens and in agent-loop steps) than
just resending the bytes. Tune via ``media_offload_min_bytes``.

What we do NOT touch
--------------------
* ``image_url`` blocks (OpenAI-native form). Those usually come from
  a provider conversion at API-call time, not from in-state messages —
  if one shows up, it's almost certainly intentional and we leave it
  alone.
* ``source: {url: ...}`` / ``source: {base64, ...}`` (Anthropic-native
  form). Same reasoning: this is a provider transport shape, not the
  v1 standard block.
* ``file://`` URL blocks (used by ``send_file_to_user`` for the outbound
  channel path). Those carry no bytes inline.
* Anything below ``min_bytes`` decoded.

The middleware is fail-soft: any exception while offloading a single
block is logged at WARNING and the original block is preserved
unchanged. A failed offload **never** breaks a turn.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage

from octop_harness.backends.utils import BACKEND_CALL_ERRORS, DEFENSIVE_OP_ERRORS

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Media offload directory (single source of truth)
# ---------------------------------------------------------------------------

DEFAULT_MEDIA_OFFLOAD_DIR = ".media-cache"
DEFAULT_MEDIA_OFFLOAD_PREFIX = DEFAULT_MEDIA_OFFLOAD_DIR

# 4 KiB raw — below this, the placeholder text (~80B) plus a future
# ``read_file`` round-trip costs more than just sending the original.
DEFAULT_MIN_BYTES = 4 * 1024
DEFAULT_OFFLOAD_PREFIX = DEFAULT_MEDIA_OFFLOAD_PREFIX

# Markers stamped onto already-offloaded blocks so we know not to
# materialize them a second time. Prefixed with underscore by
# convention to mark "internal use, do not surface in tool docs".
_OFFLOAD_SHA_KEY = "_offload_sha"
_OFFLOAD_PATH_KEY = "_offload_path"
_OFFLOAD_SIZE_KEY = "_offload_size"
_OFFLOAD_MIME_KEY = "_offload_mime"
_OFFLOAD_BTYPE_KEY = "_offload_btype"


class MediaOffloadMiddleware(AgentMiddleware[Any, Any]):
    """Offload large inline media to the backend after the first turn.

    Args:
        workspace: Scoped workspace facade (all uploads go through it).
        min_bytes: Skip blocks whose decoded payload is smaller than
            this. Defaults to 4 KiB — see module docstring.
        media_offload_dir: Workspace-relative offload directory fragment,
            or an absolute/`~` storage path. Defaults to ``.media-cache``.
    """

    @property
    def name(self) -> str:
        return "MediaOffloadMiddleware"

    def __init__(
        self,
        workspace: BackendWorkspace,
        *,
        min_bytes: int = DEFAULT_MIN_BYTES,
        media_offload_dir: str | None = None,
    ) -> None:
        super().__init__()
        if min_bytes <= 0:
            raise ValueError("min_bytes must be positive")
        self._workspace = workspace
        self._min_bytes = min_bytes
        self._offload_dir = workspace.resolve_path(media_offload_dir, default=DEFAULT_MEDIA_OFFLOAD_DIR)

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        try:
            messages = _extract_messages(state)
            if not messages:
                return None
            new_messages, changed = self._process(messages)
            return {"messages": new_messages} if changed else None
        except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive
            logger.warning("MediaOffloadMiddleware before_model failed", exc_info=True)
            return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _process(
        self,
        messages: list[BaseMessage],
    ) -> tuple[list[BaseMessage], bool]:
        """Walk every message; return (new_messages, anything_changed)."""
        any_changed = False
        out: list[BaseMessage] = list(messages)
        for i, msg in enumerate(messages):
            content = getattr(msg, "content", None)
            if not isinstance(content, list):
                continue
            new_content, changed = self._process_blocks(content)
            if changed:
                out[i] = msg.model_copy(update={"content": new_content})
                any_changed = True
        return out, any_changed

    def _process_blocks(
        self,
        blocks: list[Any],
    ) -> tuple[list[Any], bool]:
        new_blocks: list[Any] = []
        any_changed = False
        for block in blocks:
            replacement, changed = self._maybe_offload(block)
            new_blocks.append(replacement)
            if changed:
                any_changed = True
        return new_blocks, any_changed

    def _maybe_offload(self, block: Any) -> tuple[Any, bool]:  # noqa: PLR0911 - dispatch by block shape
        """Decide what to do with a single block.

        Returns ``(new_block, changed)``. ``new_block`` is either the
        original (untouched), the same block stamped with offload
        markers, or a placeholder text block for already-offloaded
        media. ``changed`` is True iff the block object differs from
        the input.
        """
        if not isinstance(block, dict):
            return block, False

        # Already offloaded once → emit the lightweight placeholder.
        if block.get(_OFFLOAD_SHA_KEY):
            return _placeholder_text_block(block), True

        # Recognise both v1 standard blocks (``{type: image|audio,
        # base64, mime_type}``) and OpenAI-native ``image_url`` blocks
        # whose URL is a ``data:`` URI. The latter is what bridges /
        # legacy code that hand-crafts OpenAI requests typically emits;
        # we accept it as a tolerated input shape so a single thread
        # can be cleaned up regardless of who built the message.
        extracted = _extract_inline_payload(block)
        if extracted is None:
            return block, False
        b64, mime, btype = extracted

        try:
            raw = base64.b64decode(b64, validate=False)
        except (ValueError, TypeError):
            logger.warning("MediaOffloadMiddleware: invalid base64; leaving block untouched")
            return block, False

        if len(raw) < self._min_bytes:
            return block, False

        try:
            sha = hashlib.sha256(raw).hexdigest()
            ext = _ext_for_mime(mime, default=".bin")
            storage_path = f"{self._offload_dir}/{sha}{ext}"
            self._workspace.upload_bytes(storage_path, raw)
        except BACKEND_CALL_ERRORS:
            logger.warning(
                "MediaOffloadMiddleware: failed to offload %d-byte %s; leaving block inline",
                len(raw),
                btype,
                exc_info=True,
            )
            return block, False

        # Tag the block in place: model still sees the original bytes
        # this turn, but next turn we'll find the marker and replace
        # with a placeholder. The marker lives at the top level
        # regardless of the block's transport shape — it's our internal
        # state, not part of any provider schema.
        tagged = {
            **block,
            _OFFLOAD_SHA_KEY: sha,
            _OFFLOAD_PATH_KEY: storage_path,
            _OFFLOAD_SIZE_KEY: len(raw),
            _OFFLOAD_MIME_KEY: mime,
            # Remember which block ``type`` we replaced so the
            # placeholder can label itself accurately even when the
            # original was an ``image_url`` block.
            _OFFLOAD_BTYPE_KEY: btype,
        }
        return tagged, True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_messages(state: Any) -> list[BaseMessage]:
    if state is None:
        return []
    if isinstance(state, dict):
        return list(state.get("messages", []) or [])
    return list(getattr(state, "messages", []) or [])


def _extract_inline_payload(
    block: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Pull ``(base64, mime_type, btype)`` out of an offloadable block.

    Returns ``None`` when the block is not a recognised inline-bytes
    shape (e.g. text block, ``file://`` URL block, ``https://`` image,
    Anthropic ``source: {url}``, video, anything we don't handle).

    Recognised shapes:

    * **v1 standard** —
      ``{type: "image"|"audio", base64: "...", mime_type: "..."}``
    * **OpenAI-native ``image_url`` data URI** —
      ``{type: "image_url", image_url: {url: "data:image/png;base64,..."}}``
      (The ``image_url`` payload may be a ``str`` instead of a dict on
      some legacy code paths; we accept both.)
    """
    btype = block.get("type")

    # v1 standard block: base64 lives at top level.
    if btype in ("image", "audio"):
        b64 = block.get("base64")
        mime = block.get("mime_type") or "application/octet-stream"
        if isinstance(b64, str) and b64:
            return b64, mime, btype
        return None

    # OpenAI-native image_url: dig out a data: URI from inside.
    if btype == "image_url":
        payload = block.get("image_url")
        url: str | None
        if isinstance(payload, dict):
            url = payload.get("url") if isinstance(payload.get("url"), str) else None
        elif isinstance(payload, str):
            url = payload
        else:
            url = None
        if not url or not url.startswith("data:"):
            return None
        # data:<media_type>[;params];base64,<payload>
        # We deliberately only handle the base64 form. Plain ``data:`` URIs
        # (no ``;base64,``) are exotic enough that ignoring them is safer
        # than guessing.
        head, _, b64 = url.partition(";base64,")
        if not b64:
            return None
        # ``head`` is "data:image/png" or "data:image/png;charset=utf-8".
        media_type = head[len("data:") :].split(";", 1)[0].strip()
        mime = media_type or "application/octet-stream"
        # Re-emit as a synthetic image type — the placeholder text and
        # the offload path care about the media kind, not the transport
        # shape it arrived in.
        return b64, mime, "image"

    return None


def _ext_for_mime(mime: str, *, default: str) -> str:
    """Best-effort MIME → file extension. Falls back to ``default``."""
    primary = mime.split(";", 1)[0].strip().lower()
    # Hand-pick the common ones to avoid mimetypes' quirks
    # (e.g. it returns ``.jpe`` for ``image/jpeg`` on some platforms).
    overrides = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/flac": ".flac",
    }
    if primary in overrides:
        return overrides[primary]
    return mimetypes.guess_extension(primary) or default


def _placeholder_text_block(tagged: dict[str, Any]) -> dict[str, Any]:
    """Produce the lightweight text block shown to the model after offload.

    The wording deliberately tells the model how to retrieve the bytes
    (``read_file``) so it can re-examine the media if asked. We include
    the SHA so any operator inspecting a transcript can correlate the
    placeholder with the cached file.
    """
    # Prefer the offload-time block type (which we recorded explicitly)
    # over ``tagged["type"]``: for OpenAI ``image_url`` blocks the latter
    # would say "image_url offloaded" which is technically accurate but
    # confusing to operators reading transcripts.
    btype = tagged.get(_OFFLOAD_BTYPE_KEY) or tagged.get("type", "media")
    sha = tagged.get(_OFFLOAD_SHA_KEY, "?")
    path = tagged.get(_OFFLOAD_PATH_KEY, "?")
    size = tagged.get(_OFFLOAD_SIZE_KEY, 0)
    mime = tagged.get(_OFFLOAD_MIME_KEY, "?")
    short_sha = sha[:12] if isinstance(sha, str) else "?"
    text = f"[{btype} offloaded: sha={short_sha} path={path} size={size}B mime={mime}; use read_file to retrieve bytes]"
    return {"type": "text", "text": text}


__all__ = [
    "DEFAULT_MEDIA_OFFLOAD_DIR",
    "DEFAULT_MEDIA_OFFLOAD_PREFIX",
    "DEFAULT_MIN_BYTES",
    "DEFAULT_OFFLOAD_PREFIX",
    "MediaOffloadMiddleware",
]
