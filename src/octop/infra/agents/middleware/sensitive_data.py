r"""Mask mainland-China phone numbers and resident ID card numbers in agent traffic.

Why this exists
---------------
octop-harness auto-mounts ``PIIMiddleware`` with an API-key detector
(``octop_harness.middleware.pii.detect_pii``) whenever the ``pii`` policy
section is enabled. That detector deliberately covers provider API keys
only — its module docstring leaves phone numbers and government IDs as
future work — and langchain's generic ``mask`` strategy keeps just the last
4 characters (``****5678``), which cannot produce the familiar Chinese PII
display formats ``138****5678`` / ``110101********1234``.

This middleware complements the harness detector with the two formats asked
for in issue #1352:

- Mainland mobile phone numbers: ``1[3-9]`` + 9 digits (11 total), masked
  keeping the first 3 and last 4 digits (``138****5678``).
- 18-digit resident ID card numbers: 17 digits + a digit or ``X``/``x``
  check character, masked keeping the first 6 and last 4 characters
  (``110101********1234``).

Both patterns are boundary-guarded with ``(?<!\d)`` / ``(?!\d)`` so an
11-digit slice inside a longer digit run (an order number, an ID card body,
…) is never masked on its own.

The middleware reuses the existing ``pii`` policy section (``enabled`` /
``strategy`` / ``surfaces``) so admins keep a single switch, and mirrors
langchain ``PIIMiddleware``'s state-level hook surface:
``before_model`` scrubs the latest user input plus tool results after the
last AI message, ``after_model`` scrubs the latest AI message. Strategies
match the existing dropdown: ``mask`` / ``redact`` / ``block`` / ``hash``.

Streaming-surface scrubbing (delta transformer) intentionally stays out of
this first version — the same trade-off langchain documents as "state-level
hooks are the canonical enforcer" — and can follow once the pattern set
settles (see the custom-regex discussion on the issue).
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any, Literal

from langchain.agents.middleware import AgentMiddleware, AgentState, PIIDetectionError, hook_config
from langchain.agents.middleware.types import ContextT, ResponseT
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

if TYPE_CHECKING:
    from langchain.agents.middleware import PIIMatch
    from langgraph.runtime import Runtime

# Each entry is ``(label, compiled_pattern)`` — the same shape as
# ``octop_harness.middleware.pii._PATTERNS``. The ID-card pattern runs first
# so the longer, more specific span wins when spans could collide.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 18-digit resident ID card: 17 digits + digit or X/x check character.
    # Boundaries reject ID bodies embedded in longer digit runs.
    ("cn_id_card", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
    # Mainland mobile phone: 1 + [3-9] + 9 digits, not inside a digit run.
    ("cn_mobile_phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
)

# How many leading/trailing characters each label keeps under ``mask``.
_MASK_KEEP: dict[str, tuple[int, int]] = {
    "cn_mobile_phone": (3, 4),  # 138****5678
    "cn_id_card": (6, 4),  # 110101********1234
}

Strategy = Literal["block", "redact", "mask", "hash"]


def detect_sensitive_data(text: str) -> list[PIIMatch]:
    """Return phone/ID spans inside ``text`` in ``PIIMatch`` shape.

    Mirrors ``octop_harness.middleware.pii.detect_pii``: spans come back
    left-to-right and overlapping matches are de-duplicated by start
    position (first label wins).
    """
    seen_starts: set[int] = set()
    matches: list[PIIMatch] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if m.start() in seen_starts:
                continue
            seen_starts.add(m.start())
            matches.append({"type": label, "value": m.group(0), "start": m.start(), "end": m.end()})
    matches.sort(key=lambda m: m["start"])
    return matches


def _mask_value(label: str, value: str) -> str:
    """Return ``value`` masked per label, e.g. ``138****5678``."""
    head, tail = _MASK_KEEP.get(label, (0, 4))
    if len(value) <= head + tail:
        return "*" * len(value)
    return f"{value[:head]}{'*' * (len(value) - head - tail)}{value[-tail:]}"


def _replacement(label: str, value: str, strategy: Strategy) -> str:
    if strategy == "mask":
        return _mask_value(label, value)
    if strategy == "redact":
        return f"[REDACTED_{label.upper()}]"
    if strategy == "hash":
        digest = hashlib.sha256(value.encode()).hexdigest()[:8]
        return f"<{label}_hash:{digest}>"
    # ``block`` is handled by the caller (raises PIIDetectionError).
    raise ValueError(f"Unknown strategy: {strategy}")  # pragma: no cover


def _apply_strategy(content: str, matches: list[PIIMatch], strategy: Strategy) -> str:
    if strategy == "block":
        raise PIIDetectionError(matches[0]["type"], matches)
    for match in sorted(matches, key=lambda m: m["start"], reverse=True):
        replacement = _replacement(match["type"], match["value"], strategy)
        content = content[: match["start"]] + replacement + content[match["end"] :]
    return content


class SensitiveDataMaskMiddleware(AgentMiddleware[AgentState[ResponseT], ContextT, ResponseT]):
    """Mask Chinese phone/ID numbers on the surfaces the ``pii`` policy selects."""

    def __init__(
        self,
        *,
        strategy: Strategy = "mask",
        apply_to_input: bool = True,
        apply_to_output: bool = False,
        apply_to_tool_results: bool = False,
    ) -> None:
        super().__init__()
        self.strategy = strategy
        self.apply_to_input = apply_to_input
        self.apply_to_output = apply_to_output
        self.apply_to_tool_results = apply_to_tool_results

    @property
    def name(self) -> str:
        return f"{self.__class__.__name__}[cn_id_card,cn_mobile_phone]"

    def _process_content(
        self, content: str | list[str | dict[str, Any]]
    ) -> tuple[str | list[str | dict[str, Any]], bool]:
        """Apply the strategy, preserving the shape of message ``content``.

        Same contract as langchain ``PIIMiddleware._process_content``: only
        string leaves are rewritten (plain strings and the ``text`` field of
        content blocks); non-text blocks pass through untouched.
        """
        if isinstance(content, str):
            matches = detect_sensitive_data(content)
            if not matches:
                return content, False
            return _apply_strategy(content, matches, self.strategy), True

        new_blocks: list[str | dict[str, Any]] = []
        changed = False
        for block in content:
            new_block: str | dict[str, Any] = block
            text = block if isinstance(block, str) else block.get("text")
            if isinstance(text, str) and (matches := detect_sensitive_data(text)):
                rewritten = _apply_strategy(text, matches, self.strategy)
                new_block = rewritten if isinstance(block, str) else {**block, "text": rewritten}
                changed = True
            new_blocks.append(new_block)
        return (new_blocks, True) if changed else (content, False)

    def _scrub_state(self, state: AgentState[Any]) -> list[Any] | None:
        """Shared ``before_model`` body: last user input + trailing tool results."""
        messages = state["messages"]
        if not messages:
            return None

        new_messages = list(messages)
        any_modified = False

        if self.apply_to_input:
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    if messages[i].content:
                        new_content, changed = self._process_content(messages[i].content)
                        if changed:
                            new_messages[i] = messages[i].model_copy(
                                update={"content": new_content}
                            )
                            any_modified = True
                    break

        if self.apply_to_tool_results:
            last_ai_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], AIMessage):
                    last_ai_idx = i
                    break
            if last_ai_idx is not None:
                for i in range(last_ai_idx + 1, len(messages)):
                    if not isinstance(messages[i], ToolMessage) or not messages[i].content:
                        continue
                    new_content, changed = self._process_content(messages[i].content)
                    if changed:
                        new_messages[i] = messages[i].model_copy(update={"content": new_content})
                        any_modified = True

        if not any_modified:
            return None
        return new_messages

    @hook_config(can_jump_to=["end"])
    def before_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        if not self.apply_to_input and not self.apply_to_tool_results:
            return None
        new_messages = self._scrub_state(state)
        if new_messages is None:
            return None
        return {"messages": new_messages}

    @hook_config(can_jump_to=["end"])
    async def abefore_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        if not self.apply_to_output:
            return None
        messages = state["messages"]
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                if not messages[i].content:
                    return None
                new_content, changed = self._process_content(messages[i].content)
                if not changed:
                    return None
                new_messages = list(messages)
                new_messages[i] = messages[i].model_copy(update={"content": new_content})
                return {"messages": new_messages}
        return None

    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        return self.after_model(state, runtime)


__all__ = ["SensitiveDataMaskMiddleware", "detect_sensitive_data"]
