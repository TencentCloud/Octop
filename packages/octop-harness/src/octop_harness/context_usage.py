"""Estimate and persist context-window usage from the last model request."""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from octop_harness.usage import normalize_usage_metadata

logger = logging.getLogger(__name__)

# Stored on AIMessage.additional_kwargs; kept stable for Octop / dashboard.
CONTEXT_USAGE_KEY = "context_usage"

SEGMENT_KEYS: tuple[str, ...] = (
    "system_prompt",
    "tool_definitions",
    "rules",
    "skills",
    "mcp",
    "subagent_definitions",
    "conversation",
)

_TEAM_TOOL_NAMES = frozenset({"agent_list", "ask_agent", "task"})
DEFAULT_MAX_TOKENS = 128_000

ContextUsageSource = Literal["model_request", "empty"]

# Segments a decision pass can shrink. Conversation and the base prompt stay.
_FILTERED_SEGMENT_KEYS = (
    "tool_definitions",
    "skills",
    "mcp",
    "subagent_definitions",
)

# Set by decision middleware around the model call it narrowed.
pending_decision_saved: ContextVar[int] = ContextVar("octop_pending_decision_saved", default=0)


# Han / kana / Hangul cost far more tokens per character than Latin text: BPE
# vocabularies spend roughly one token per 1-2 CJK characters against ~4 Latin
# characters. A flat len/4 under-counts a Chinese prompt by more than half.
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f\uac00-\ud7af]")
_LATIN_CHARS_PER_TOKEN = 4.0
_CJK_CHARS_PER_TOKEN = 1.6
# Structured JSON (tool schemas, tool-call arguments) tokenizes denser than
# prose — braces, quotes, colons and snake_case keys each split off.
_JSON_CHARS_PER_TOKEN = 3.0
# Role marker plus separators the chat template adds around every message.
_MESSAGE_FRAMING_TOKENS = 4
# An inlined image is billed as a tile grid, not as its placeholder text.
# Deliberately mid-range: exact cost is provider- and resolution-specific.
_IMAGE_BLOCK_TOKENS = 1_600
_MEDIA_BLOCK_TOKENS = 400


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    latin = len(text) - cjk
    est = cjk / _CJK_CHARS_PER_TOKEN + latin / _LATIN_CHARS_PER_TOKEN
    return max(1, round(est))


def estimate_json_tokens(text: str) -> int:
    """Token estimate for serialized JSON, which packs denser than prose."""
    if not text:
        return 0
    return max(1, round(len(text) / _JSON_CHARS_PER_TOKEN))


def content_tokens(content: Any) -> int:
    """Token estimate for one message's content, block type by block type.

    :func:`message_content_text` renders blocks for *reading*, so it replaces
    long tool results and media with short placeholders. Counting that text
    reports a few tokens for payloads worth thousands, which is most of why
    the segment breakdown used to fall short of the provider total.
    """
    if isinstance(content, str):
        return estimate_tokens(content)
    if not isinstance(content, list):
        return estimate_tokens(str(content or ""))
    total = 0
    for block in content:
        if isinstance(block, str):
            total += estimate_tokens(block)
            continue
        if not isinstance(block, dict):
            total += estimate_tokens(str(block))
            continue
        btype = str(block.get("type") or "").lower()
        if btype in ("thinking", "reasoning"):
            # Providers that support extended thinking strip these from the
            # history they re-send, so they do not occupy the next prompt.
            continue
        if btype == "text":
            total += estimate_tokens(str(block.get("text") or ""))
        elif btype == "tool_use":
            total += estimate_json_tokens(json.dumps(block.get("input") or {}, ensure_ascii=False))
        elif btype == "tool_result":
            total += estimate_tokens(str(block.get("output") or ""))
        elif btype in ("image", "image_url", "input_image"):
            total += _IMAGE_BLOCK_TOKENS
        elif btype in ("file", "audio", "video"):
            total += _MEDIA_BLOCK_TOKENS
        else:
            total += estimate_json_tokens(json.dumps(block, ensure_ascii=False, default=str))
    return total


def message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                btype = str(block.get("type") or "").lower()
                if btype in ("thinking", "reasoning"):
                    continue
                if btype == "text":
                    parts.append(str(block.get("text") or ""))
                elif btype == "tool_use":
                    parts.append(json.dumps(block.get("input") or {}, ensure_ascii=False))
                elif btype == "tool_result":
                    output = str(block.get("output") or "")
                    if len(output) > 500:
                        parts.append(f"[tool_result truncated: {len(output)} chars]")
                    else:
                        parts.append(output)
                elif btype in ("file", "image", "image_url", "input_image", "audio", "video"):
                    parts.append(f"[{btype} block omitted]")
                else:
                    raw = json.dumps(block, ensure_ascii=False)
                    if len(raw) > 500:
                        parts.append(f"[{btype or 'block'} truncated: {len(raw)} chars]")
                    else:
                        parts.append(raw)
        return "\n".join(p for p in parts if p)
    return str(content or "")


def conversation_tokens_from_messages(messages: list[Any]) -> int:
    total = 0
    for msg in messages:
        if isinstance(msg, dict):
            role = str(msg.get("role") or msg.get("type") or "")
            if role == "system":
                continue
            total += content_tokens(msg.get("content")) + _MESSAGE_FRAMING_TOKENS
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total += estimate_json_tokens(json.dumps(tool_calls, ensure_ascii=False, default=str))
            continue
        role = str(getattr(msg, "type", "") or "")
        if role == "system":
            continue
        total += content_tokens(getattr(msg, "content", "")) + _MESSAGE_FRAMING_TOKENS
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            total += estimate_json_tokens(json.dumps(tool_calls, ensure_ascii=False, default=str))
    return total


_TOOL_SCHEMA_TOKEN_CACHE: dict[tuple[str, bool], int] = {}


def tool_schema_tokens(tool: Any) -> int:
    name = _tool_name(tool)
    extras = getattr(tool, "extras", None)
    deferred = isinstance(extras, dict) and extras.get("defer_loading") is True
    cache_key = (name, deferred)
    if name and cache_key in _TOOL_SCHEMA_TOKEN_CACHE:
        return _TOOL_SCHEMA_TOKEN_CACHE[cache_key]
    try:
        if deferred:
            # Provider-native search keeps the parameter schema out of the
            # initial context. OpenAI may retain the function name and
            # description, while Anthropic can omit the deferred definition
            # entirely; counting this small descriptor is conservative.
            schema = {
                "name": name,
                "description": str(getattr(tool, "description", "") or ""),
            }
        else:
            from langchain_core.utils.function_calling import convert_to_openai_tool

            schema = convert_to_openai_tool(tool)
        tokens = estimate_json_tokens(json.dumps(schema, ensure_ascii=False))
    except Exception:  # schema conversion is best-effort; pylint: disable=broad-except
        tokens = estimate_tokens(name) + 50
    if name:
        _TOOL_SCHEMA_TOKEN_CACHE[cache_key] = tokens
    return tokens


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if isinstance(tool, dict):
        function = tool.get("function")
        if isinstance(function, dict):
            fname = function.get("name")
            if isinstance(fname, str):
                return fname
        raw = tool.get("name")
        if isinstance(raw, str):
            return raw
    return ""


def tool_bucket_tokens(
    tools: list[Any],
    *,
    mcp_tool_names: frozenset[str] | None = None,
) -> tuple[int, int, int]:
    """Return ``(tool_definitions, mcp, subagent_definitions)`` token estimates."""
    mcp_names = mcp_tool_names or frozenset()
    tool_def = 0
    mcp_total = 0
    subagent = 0
    for tool in tools:
        name = _tool_name(tool)
        tokens = tool_schema_tokens(tool)
        if name in mcp_names:
            mcp_total += tokens
        elif name in _TEAM_TOOL_NAMES:
            subagent += tokens
        else:
            tool_def += tokens
    return tool_def, mcp_total, subagent


def scale_segments(raw: dict[str, int], target: int) -> dict[str, int]:
    if target <= 0:
        return dict.fromkeys(SEGMENT_KEYS, 0)
    total = sum(max(0, int(raw.get(k, 0))) for k in SEGMENT_KEYS)
    if total <= 0:
        return dict.fromkeys(SEGMENT_KEYS, 0)
    scaled = {k: round(max(0, int(raw.get(k, 0))) * target / total) for k in SEGMENT_KEYS}
    drift = target - sum(scaled.values())
    if drift:
        largest = max(SEGMENT_KEYS, key=lambda key: scaled[key])
        scaled[largest] = max(0, scaled[largest] + drift)
    return scaled


def catalog_saved_tokens(before: Any, after: Any) -> int:
    """Tokens the decision filter kept out of one model request.

    Uses the same segment estimator as the context panel, so the number matches
    the tool, skill, MCP, and subagent rows.
    """
    if before is after:
        return 0
    raw_before = breakdown_from_model_request(before)
    raw_after = breakdown_from_model_request(after)
    return sum(max(0, int(raw_before.get(key, 0)) - int(raw_after.get(key, 0))) for key in _FILTERED_SEGMENT_KEYS)


def breakdown_from_model_request(
    request: Any,
    *,
    mcp_tool_names: frozenset[str] | None = None,
) -> dict[str, int]:
    """Estimate raw segment tokens from a LangChain ``ModelRequest``."""
    system_message = getattr(request, "system_message", None)
    system_text = ""
    if system_message is not None:
        system_text = message_content_text(getattr(system_message, "content", ""))
    elif getattr(request, "system_prompt", None):
        system_text = str(request.system_prompt)

    system_parts = partition_system_prompt_segments(system_text)
    tools = list(getattr(request, "tools", None) or [])
    tool_def, mcp_total, subagent = tool_bucket_tokens(tools, mcp_tool_names=mcp_tool_names)
    messages = list(getattr(request, "messages", None) or [])

    return {
        "system_prompt": system_parts["system_prompt"],
        "tool_definitions": tool_def,
        "rules": system_parts["rules"],
        "skills": system_parts["skills"],
        "mcp": mcp_total,
        "subagent_definitions": subagent,
        "conversation": conversation_tokens_from_messages(messages),
    }


_SKILLS_MARKER = "## Skills System"
_AGENT_MEMORY_OPEN = "<agent_memory>"
_AGENT_MEMORY_CLOSE = "</agent_memory>"


def partition_system_prompt_segments(system_text: str) -> dict[str, int]:
    """Split DeepAgents-injected system text into system / rules / skills tokens.

    Recognizes:
    - ``## Skills System`` … (SkillsMiddleware)
    - ``<agent_memory>…</agent_memory>`` (MemoryMiddleware / AGENTS.md)
    """
    if not system_text:
        return {"system_prompt": 0, "rules": 0, "skills": 0}

    rest = system_text
    skills_text = ""
    rules_text = ""

    skills_idx = rest.find(_SKILLS_MARKER)
    if skills_idx >= 0:
        skills_text = rest[skills_idx:]
        rest = rest[:skills_idx]

    mem_start = rest.find(_AGENT_MEMORY_OPEN)
    mem_end = rest.find(_AGENT_MEMORY_CLOSE)
    if mem_start >= 0 and mem_end > mem_start:
        close_at = mem_end + len(_AGENT_MEMORY_CLOSE)
        rules_text = rest[mem_start:close_at]
        rest = rest[:mem_start] + rest[close_at:]

    return {
        "system_prompt": estimate_tokens(rest.strip()),
        "rules": estimate_tokens(rules_text),
        "skills": estimate_tokens(skills_text),
    }


def extract_usage_from_message(msg: Any) -> dict[str, int] | None:
    metadata = getattr(msg, "usage_metadata", None)
    response_metadata = getattr(msg, "response_metadata", None)
    wire_usage: dict[str, Any] = {}
    if isinstance(response_metadata, dict):
        usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(usage, dict):
            wire_usage = usage
    source = {
        **wire_usage,
        **(metadata if isinstance(metadata, dict) else {}),
    }
    if source:
        normalized = normalize_usage_metadata(source)
        if normalized["input_tokens"] or normalized["output_tokens"]:
            return normalized
    return None


@dataclass
class ContextUsage:
    max_tokens: int = DEFAULT_MAX_TOKENS
    used_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    uncached_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    segments: dict[str, int] = field(default_factory=dict)
    source: ContextUsageSource = "empty"
    decision_saved: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ContextUsage:
        if not isinstance(data, dict):
            return empty_context_usage()
        segments_raw = data.get("segments") or {}
        segments = {k: int(segments_raw.get(k, 0) or 0) for k in SEGMENT_KEYS if int(segments_raw.get(k, 0) or 0) > 0}
        used_tokens = int(data.get("used_tokens") or 0)
        input_tokens = int(data.get("input_tokens") or 0)
        output_tokens = int(data.get("output_tokens") or 0)
        source = data.get("source") or "empty"
        if source not in ("model_request", "empty"):
            source = "empty"
        # Older stamps omitted ``source``; missing must not discard real occupancy.
        if source == "empty" and (used_tokens > 0 or input_tokens > 0 or segments):
            source = "model_request"
        return cls(
            max_tokens=int(data.get("max_tokens") or DEFAULT_MAX_TOKENS),
            used_tokens=used_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            uncached_input_tokens=int(data.get("uncached_input_tokens") or 0),
            cache_read_tokens=int(data.get("cache_read_tokens") or 0),
            cache_write_tokens=int(data.get("cache_write_tokens") or 0),
            reasoning_tokens=int(data.get("reasoning_tokens") or 0),
            segments=segments,
            source=source,  # type: ignore[arg-type]
            decision_saved=max(0, int(data.get("decision_saved") or 0)),
        )

    def with_max_tokens(self, max_tokens: int) -> ContextUsage:
        """Re-bind the display/cap without permanently losing uncapped usage.

        Snapshots may have been stamped under a too-small default cap (128k).
        Prefer ``input_tokens`` (provider-reported) when raising the cap so the
        ring reflects real occupancy against the true context window.
        """
        cap = max_tokens if max_tokens > 0 else DEFAULT_MAX_TOKENS
        raw_used = self.input_tokens if self.input_tokens > 0 else self.used_tokens
        return ContextUsage(
            max_tokens=cap,
            used_tokens=min(raw_used, cap),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            uncached_input_tokens=self.uncached_input_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens,
            segments=dict(self.segments),
            source=self.source,
            decision_saved=self.decision_saved,
        )


def empty_context_usage(*, max_tokens: int = DEFAULT_MAX_TOKENS) -> ContextUsage:
    return ContextUsage(max_tokens=max_tokens if max_tokens > 0 else DEFAULT_MAX_TOKENS)


def build_context_usage(
    request: Any,
    *,
    response_messages: list[Any] | None = None,
    mcp_tool_names: frozenset[str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ContextUsage:
    """Build a usage snapshot from a model request and optional response messages."""
    raw = breakdown_from_model_request(request, mcp_tool_names=mcp_tool_names)
    input_tokens = sum(raw.values())
    output_tokens = 0
    uncached_input_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    reasoning_tokens = 0

    for msg in reversed(response_messages or []):
        usage = extract_usage_from_message(msg)
        if usage:
            if usage["input_tokens"] > 0:
                input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            uncached_input_tokens = usage["uncached_input_tokens"]
            cache_read_tokens = usage["cache_read_tokens"]
            cache_write_tokens = usage["cache_write_tokens"]
            reasoning_tokens = usage["reasoning_tokens"]
            break

    # Provider usage is authoritative for occupancy.  Segment counts are
    # deliberately left as estimates instead of being stretched to match it;
    # otherwise a tokenizer mismatch looks like false precision in the UI.
    segments = raw if input_tokens > 0 else dict.fromkeys(SEGMENT_KEYS, 0)
    # Drop zero segments for a compact persisted payload / API response.
    compact = {k: v for k, v in segments.items() if v > 0}
    cap = max_tokens if max_tokens > 0 else DEFAULT_MAX_TOKENS
    decision_saved = max(0, int(pending_decision_saved.get() or 0))
    return ContextUsage(
        max_tokens=cap,
        used_tokens=min(input_tokens, cap),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        uncached_input_tokens=uncached_input_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
        segments=compact,
        source="model_request" if input_tokens > 0 else "empty",
        decision_saved=decision_saved,
    )


def shrink_context_usage(usage: ContextUsage, removed_tokens: int) -> ContextUsage:
    """Fold offloaded history out of a snapshot taken before compaction.

    Compaction rewrites the next prompt without making a model call, so no
    fresh provider usage arrives until the following turn. Keeping the
    pre-compaction total would leave a host ring pinned at its old value for
    the whole idle period, so subtract the estimated size of what was
    offloaded instead. Both the stored ``conversation`` segment and
    *removed_tokens* come from :func:`estimate_tokens`, so the subtraction
    stays inside one unit; the next real request replaces the snapshot
    outright.

    Per-call billing fields describe the model call that produced the old
    snapshot and no longer match this prompt, so they are cleared.
    """
    delta = max(0, removed_tokens)
    if delta <= 0:
        return usage
    segments = dict(usage.segments)
    conversation = segments.get("conversation", 0)
    if conversation > 0:
        applied = min(delta, conversation)
        remaining = conversation - applied
        if remaining > 0:
            segments["conversation"] = remaining
        else:
            segments.pop("conversation", None)
    else:
        applied = delta
    input_tokens = max(0, usage.input_tokens - applied)
    cap = usage.max_tokens if usage.max_tokens > 0 else DEFAULT_MAX_TOKENS
    return ContextUsage(
        max_tokens=cap,
        used_tokens=min(input_tokens, cap),
        input_tokens=input_tokens,
        output_tokens=0,
        uncached_input_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        segments=segments,
        source=usage.source,
        decision_saved=usage.decision_saved,
    )


def context_usage_from_messages(messages: list[Any]) -> ContextUsage | None:
    """Find the newest ``context_usage`` payload on messages (scan from the end)."""
    for msg in reversed(messages):
        kwargs = getattr(msg, "additional_kwargs", None)
        if not isinstance(kwargs, dict):
            if isinstance(msg, dict):
                kwargs = msg.get("additional_kwargs") or {}
            else:
                continue
        payload = kwargs.get(CONTEXT_USAGE_KEY)
        if isinstance(payload, dict):
            return ContextUsage.from_dict(payload)
    return None


__all__ = [
    "CONTEXT_USAGE_KEY",
    "DEFAULT_MAX_TOKENS",
    "SEGMENT_KEYS",
    "ContextUsage",
    "breakdown_from_model_request",
    "build_context_usage",
    "catalog_saved_tokens",
    "content_tokens",
    "context_usage_from_messages",
    "conversation_tokens_from_messages",
    "empty_context_usage",
    "estimate_json_tokens",
    "estimate_tokens",
    "extract_usage_from_message",
    "message_content_text",
    "partition_system_prompt_segments",
    "pending_decision_saved",
    "scale_segments",
    "shrink_context_usage",
    "tool_bucket_tokens",
    "tool_schema_tokens",
]
