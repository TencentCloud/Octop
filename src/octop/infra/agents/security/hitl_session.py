"""Per-thread HITL bypass chosen during chat (Codex-style allow-all / allow-tool).

Does not change the global SecurityPolicy. ``ask_user_question`` is never skipped.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from octop.infra.db.repos.threads import ThreadRepo

HitlSessionMode = Literal["ask", "allow_all", "allow_tools"]

_ASK_USER_TOOL_NAME = "ask_user_question"
_MAX_TOOLS = 64
_MAX_TOOL_NAME = 128
_CURRENT_HITL_THREAD: ContextVar[str | None] = ContextVar(
    "octop_hitl_thread",
    default=None,
)


def _normalize_tools(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name == _ASK_USER_TOOL_NAME or len(name) > _MAX_TOOL_NAME or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= _MAX_TOOLS:
            break
    return tuple(out)


@dataclass(frozen=True)
class HitlSessionPolicy:
    """Sticky approval bypass for one conversation thread."""

    mode: HitlSessionMode = "ask"
    tools: tuple[str, ...] = ()

    def allows(self, tool_name: str) -> bool:
        if not tool_name or tool_name == _ASK_USER_TOOL_NAME:
            return False
        if self.mode == "allow_all":
            return True
        if self.mode == "allow_tools":
            return tool_name in self.tools
        return False

    def with_tools(self, names: Iterable[str]) -> HitlSessionPolicy:
        extra = _normalize_tools(list(names))
        if self.mode == "allow_all":
            return self
        merged = _normalize_tools([*self.tools, *extra])
        if not merged:
            return HitlSessionPolicy()
        return HitlSessionPolicy(mode="allow_tools", tools=merged)

    def without_tools(self, names: Iterable[str]) -> HitlSessionPolicy:
        if self.mode != "allow_tools":
            return self
        drop = set(_normalize_tools(list(names)))
        kept = tuple(item for item in self.tools if item not in drop)
        if not kept:
            return HitlSessionPolicy()
        return HitlSessionPolicy(mode="allow_tools", tools=kept)

    def to_dict(self) -> dict[str, Any]:
        if self.mode == "allow_all":
            return {"mode": "allow_all"}
        if self.mode == "allow_tools" and self.tools:
            return {"mode": "allow_tools", "tools": list(self.tools)}
        return {"mode": "ask"}

    def to_json(self) -> str | None:
        data = self.to_dict()
        if data.get("mode") == "ask":
            return None
        return json.dumps(data, ensure_ascii=False)


def parse_hitl_session_policy(raw: object) -> HitlSessionPolicy:
    """Accept JSON text, a dict, or ``None``; invalid input becomes ask-every-time."""
    if raw is None:
        return HitlSessionPolicy()
    if isinstance(raw, HitlSessionPolicy):
        return raw
    parsed: object = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return HitlSessionPolicy()
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return HitlSessionPolicy()
    if not isinstance(parsed, dict):
        return HitlSessionPolicy()
    mode = parsed.get("mode")
    if mode == "allow_all":
        return HitlSessionPolicy(mode="allow_all")
    if mode == "allow_tools":
        tools = _normalize_tools(parsed.get("tools"))
        if not tools:
            return HitlSessionPolicy()
        return HitlSessionPolicy(mode="allow_tools", tools=tools)
    return HitlSessionPolicy()


def thread_id_from_request(request: dict[str, Any]) -> str | None:
    """Read ``thread_id`` from a harness request dict."""
    raw = request.get("thread_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    cfg = request.get("configurable")
    if isinstance(cfg, dict):
        nested = cfg.get("thread_id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


@contextmanager
def hitl_thread_scope(thread_id: str | None) -> Iterator[None]:
    """Bind *thread_id* for interrupt ``when`` predicates."""
    incoming = (thread_id or "").strip() or None
    token: Token[str | None] = _CURRENT_HITL_THREAD.set(incoming)
    try:
        yield
    finally:
        _CURRENT_HITL_THREAD.reset(token)


def current_hitl_thread_id() -> str | None:
    """Thread id bound by :func:`hitl_thread_scope`, or ``None`` if unset."""
    return _CURRENT_HITL_THREAD.get()


class HitlSessionPolicyStore:
    """In-memory cache of thread bypass policy, persisted on ``threads.hitl_policy``."""

    def __init__(self, threads_repo: ThreadRepo | None = None) -> None:
        self._repo = threads_repo
        self._cache: dict[str, HitlSessionPolicy] = {}

    def replace_repo(self, threads_repo: ThreadRepo | None) -> None:
        self._repo = threads_repo
        self._cache.clear()

    def get(self, thread_id: str) -> HitlSessionPolicy:
        tid = (thread_id or "").strip()
        if not tid:
            return HitlSessionPolicy()
        cached = self._cache.get(tid)
        if cached is not None:
            return cached
        policy = self._load(tid)
        self._cache[tid] = policy
        return policy

    def set(self, thread_id: str, policy: HitlSessionPolicy | object) -> HitlSessionPolicy:
        tid = (thread_id or "").strip()
        resolved = parse_hitl_session_policy(policy)
        if not tid:
            return resolved
        self._cache[tid] = resolved
        repo = self._repo
        if repo is not None:
            repo.update_composer(tid, hitl_policy=resolved.to_json())
        return resolved

    def allows(self, thread_id: str, tool_name: str) -> bool:
        return self.get(thread_id).allows(tool_name)

    def allows_current(self, tool_name: str) -> bool:
        tid = current_hitl_thread_id()
        if not tid:
            return False
        return self.allows(tid, tool_name)

    def _load(self, thread_id: str) -> HitlSessionPolicy:
        repo = self._repo
        if repo is None:
            return HitlSessionPolicy()
        row = repo.get(thread_id)
        if row is None:
            return HitlSessionPolicy()
        return parse_hitl_session_policy(row.hitl_policy)


def apply_session_bypass(
    interrupt_on: dict[str, Any] | None,
    store: HitlSessionPolicyStore | None,
) -> dict[str, Any] | None:
    """Wrap HITL ``when`` predicates so a thread bypass can skip the interrupt."""
    if not interrupt_on or store is None:
        return interrupt_on
    out: dict[str, Any] = {}
    for name, cfg in interrupt_on.items():
        if name == _ASK_USER_TOOL_NAME:
            out[name] = cfg
            continue
        entry = dict(cfg) if isinstance(cfg, dict) else {}
        original_when = entry.get("when")

        def _when(
            req: Any,
            *,
            _tool: str = name,
            _orig: Any = original_when,
        ) -> bool:
            if store.allows_current(_tool):
                return False
            if _orig is None:
                return True
            return bool(_orig(req))

        entry["when"] = _when
        out[name] = entry
    return out


__all__ = [
    "HitlSessionMode",
    "HitlSessionPolicy",
    "HitlSessionPolicyStore",
    "apply_session_bypass",
    "current_hitl_thread_id",
    "hitl_thread_scope",
    "parse_hitl_session_policy",
    "thread_id_from_request",
]
