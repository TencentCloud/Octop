"""REPL session state for toolbar and slash side-effects."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MODEL_SET_RE = re.compile(
    r"(?:→|->)\s*([^\s\n\.]+)|模型覆盖[：:]\s*([^\s\n]+)|Model override:\s*([^\s\n]+)",
    re.IGNORECASE,
)
_MODEL_CLEARED_RE = re.compile(r"已清除模型覆盖|Model override cleared", re.IGNORECASE)


@dataclass
class ReplSession:
    agent_id: str
    session_key: str
    model: str | None = None
    conversation_mode: str | None = None
    thread_id: str | None = None
    pin_thread: bool = False
    last_elapsed: float = 0.0

    def __post_init__(self) -> None:
        if self.thread_id:
            self.pin_thread = True

    @property
    def model_label(self) -> str:
        return self.model or "default"

    def thread_id_for_send(self) -> str | None:
        """Only pin ``thread_id`` on the wire when user passed ``--thread-id``."""
        return self.thread_id if self.pin_thread else None

    def on_new_chat(self, thread_id: str | None = None) -> None:
        self.pin_thread = False
        self.thread_id = thread_id

    def on_rebind_thread(self, thread_id: str | None) -> None:
        self.pin_thread = False
        self.thread_id = thread_id

    def apply_slash_text(self, text: str) -> None:
        """Update model from gateway slash reply lines (/model, /models)."""
        if not text.strip():
            return
        if _MODEL_CLEARED_RE.search(text):
            self.model = None
            return
        for line in text.splitlines():
            m = _MODEL_SET_RE.search(line)
            if not m:
                continue
            picked = next((g for g in m.groups() if g), None)
            if picked:
                self.model = picked.strip().rstrip(".。，,")
                return
