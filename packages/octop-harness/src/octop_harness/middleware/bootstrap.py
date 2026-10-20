"""``BootstrapMiddleware`` — one-time onboarding via BOOTSTRAP.md."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.backends.workspace import USER_FILENAME

if TYPE_CHECKING:
    from octop_harness.backends.workspace import BackendWorkspace

logger = logging.getLogger(__name__)

BOOTSTRAP_FILENAME = "BOOTSTRAP.md"
BOOTSTRAPPED_MARKER = ".bootstrapped"

DEFAULT_BOOTSTRAP_PATH = BOOTSTRAP_FILENAME
DEFAULT_BOOTSTRAPPED_PATH = BOOTSTRAPPED_MARKER
DEFAULT_USER_PATH = USER_FILENAME

_WRITE_TOOLS = frozenset({"write_file", "edit_file", "append_file"})


def bootstrap_marker_exists(
    workspace: BackendWorkspace,
    *,
    bootstrap_marker: str | Path | None = None,
) -> bool:
    """True when the bootstrap completion marker exists on the backend."""
    marker_path = workspace.resolve_path(bootstrap_marker, default=BOOTSTRAPPED_MARKER)
    return workspace.exists(marker_path)


class BootstrapMiddleware(AgentMiddleware[Any, Any]):
    """Append BOOTSTRAP.md after the compiled ``system_message`` until onboarding completes.

    The compiled prompt (working-directory directive, media-tool policy, …)
    is kept. Onboarding text comes last so first-turn guidance wins over
    slash-skill rules. Persona / memory files are the host's job to omit
    during onboarding. Injection is request-scoped only
    (``wrap_model_call``). Do not write ``SystemMessage`` into checkpoint
    ``messages`` — LangGraph's ``add_messages`` appends unmatched ids to
    the tail, and residuals break strict backends after this middleware is
    removed.

    Completion (any one at end of turn): write tool on ``.bootstrapped`` or
    a non-empty final AI reply. USER.md is user-maintained. ``max_bootstrap_turns``
    is kept for API compatibility but no longer gates completion.
    """

    def __init__(
        self,
        workspace: BackendWorkspace,
        *,
        bootstrap_file: str | Path | None = None,
        bootstrap_marker: str | Path | None = None,
        max_bootstrap_turns: int = 1,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._workspace = workspace
        self._bootstrap_path = workspace.resolve_path(bootstrap_file, default=BOOTSTRAP_FILENAME)
        self._marker_path = workspace.resolve_path(bootstrap_marker, default=BOOTSTRAPPED_MARKER)
        self._max_bootstrap_turns = max_bootstrap_turns
        self._on_complete = on_complete
        self._announced_bootstrap = False
        self._marker_known: bool | None = None

    @property
    def is_bootstrapped(self) -> bool:
        """Whether the completion marker already exists on the backend.

        The answer is remembered for this middleware instance. A missing marker
        is a remote GET (COS 404); model calls must not repeat it.
        """
        if self._marker_known is not None:
            return self._marker_known
        self._marker_known = bootstrap_marker_exists(self._workspace, bootstrap_marker=self._marker_path)
        return self._marker_known

    # ── model-call hook: inject BOOTSTRAP.md as system prompt ───────────────

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._with_bootstrap_system(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._with_bootstrap_system(request))

    def _with_bootstrap_system(self, request: ModelRequest) -> ModelRequest:
        if self.is_bootstrapped:
            return request

        raw = self._workspace.read_text(self._bootstrap_path)
        if raw is None:
            logger.warning("Bootstrap file not found at %s — skipping injection.", self._bootstrap_path)
            return request
        content = raw.strip()
        if not content:
            logger.info("Bootstrap file is empty — skipping injection.")
            return request

        if not self._announced_bootstrap:
            self._announced_bootstrap = True
            logger.debug(
                "Bootstrap active — appending %d chars from %s onto the compiled system prompt",
                len(content),
                self._bootstrap_path,
            )
        messages: list[AnyMessage] = [m for m in request.messages if not isinstance(m, SystemMessage)]
        return request.override(
            system_message=append_to_system_message(request.system_message, content),
            messages=messages,
        )

    # ── turn hook: mark onboarding complete ─────────────────────────────────

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Write ``.bootstrapped`` when any completion signal is present."""
        if self.is_bootstrapped:
            return None
        if self._should_complete(state):
            self._complete()
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)

    def _should_complete(self, state: Any) -> bool:
        return self._wrote_to(state, self._marker_path) or self._has_final_reply(state)

    def _complete(self) -> None:
        if self.is_bootstrapped:
            return
        self._workspace.write_text(self._marker_path, "", force=True)
        self._marker_known = True
        logger.info("Bootstrap complete — wrote %s on backend", self._marker_path)
        if self._on_complete is None:
            return
        try:
            self._on_complete()
        except DEFENSIVE_OP_ERRORS:
            logger.exception("Bootstrap on_complete callback raised an exception")

    # ── completion signals from turn state ──────────────────────────────────

    def _wrote_to(self, state: Any, target: str) -> bool:
        """True when a write tool in this turn targeted *target*."""
        for msg in state.get("messages", []):
            if not isinstance(msg, AIMessage):
                continue
            for call in msg.tool_calls or []:
                if str(call.get("name") or "") not in _WRITE_TOOLS:
                    continue
                args = call.get("args") or {}
                path = str(args.get("file_path") or args.get("path") or "")
                if self._path_matches(path, target):
                    return True
        return False

    @staticmethod
    def _has_final_reply(state: Any) -> bool:
        """True when any AI message is a non-empty final reply (no tool calls)."""
        return any(
            isinstance(msg, AIMessage) and not msg.tool_calls and msg.content for msg in state.get("messages", [])
        )

    def _path_matches(self, tool_path: str, target: str) -> bool:
        if not tool_path:
            return False
        target = target.rstrip("/")
        normalized = tool_path.rstrip("/")
        if normalized == target:
            return True
        try:
            if self._workspace.resolve_path(tool_path).rstrip("/") == target:
                return True
        except PermissionError:
            pass
        name = target.rsplit("/", 1)[-1]
        return normalized == name or normalized.endswith(f"/{name}")


__all__ = [
    "BOOTSTRAPPED_MARKER",
    "BOOTSTRAP_FILENAME",
    "DEFAULT_BOOTSTRAPPED_PATH",
    "DEFAULT_BOOTSTRAP_PATH",
    "DEFAULT_USER_PATH",
    "BootstrapMiddleware",
    "bootstrap_marker_exists",
]
