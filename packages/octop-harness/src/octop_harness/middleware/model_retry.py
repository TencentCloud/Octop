"""Preserve upstream retry policy and identify legacy synthetic error replies."""

from __future__ import annotations

from langchain.agents.middleware import ModelRetryMiddleware as BaseModelRetryMiddleware
from langchain_core.messages import AIMessage


class ModelRetryMiddleware(BaseModelRetryMiddleware):
    """Retain provenance when an external caller explicitly requests ``continue``.

    Both sync and async retry exhaustion share this upstream formatting hook.
    HarnessAgent itself uses ``on_failure="error"`` and never emits this reply.
    """

    @staticmethod
    def _format_failure_message(exc: Exception, attempts_made: int) -> AIMessage:
        message = BaseModelRetryMiddleware._format_failure_message(exc, attempts_made)
        message.response_metadata["octop_runtime_error"] = True
        return message
