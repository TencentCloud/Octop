"""Model-visible operational errors for media generation tools."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import ToolException

MediaErrorCategory = Literal[
    "authentication",
    "authorization",
    "configuration",
    "provider",
    "quota",
    "rate_limit",
    "safety",
    "validation",
]


class MediaGenerationError(ToolException):
    """A safe operational failure that should be returned to the model.

    Unexpected programming errors intentionally do not use this class so they
    still fail the agent stream and remain visible to runtime monitoring.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_error",
        category: MediaErrorCategory = "provider",
        retryable: bool = False,
        safe_to_resubmit: bool = False,
        remediation: str = "contact_support",
        model_instruction: str = "Do not retry this tool call. Explain the failure to the user.",
        provider_code: str | None = None,
        provider_task_id: str | None = None,
        http_status: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.retryable = retryable
        self.safe_to_resubmit = safe_to_resubmit
        self.remediation = remediation
        self.model_instruction = model_instruction
        self.provider_code = provider_code
        self.provider_task_id = provider_task_id
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds

    def to_tool_result(
        self,
        *,
        result_type: str,
        tool_name: str,
        provider: str,
        model: str,
    ) -> dict[str, object]:
        """Return a stable, model- and UI-readable failure envelope."""
        error: dict[str, object] = {
            "code": self.code,
            "category": self.category,
            "message": str(self),
            "retryable": self.retryable,
            "safe_to_resubmit": self.safe_to_resubmit,
        }
        if self.provider_code:
            error["provider_code"] = self.provider_code
        if self.http_status is not None:
            error["http_status"] = self.http_status
        if self.retry_after_seconds is not None:
            error["retry_after_seconds"] = self.retry_after_seconds

        execution: dict[str, object] = {
            "provider": provider,
            "model": model,
            "fallback_used": False,
        }
        if self.provider_task_id:
            execution["provider_task_id"] = self.provider_task_id

        return {
            "schema_version": 1,
            "type": result_type,
            "tool": tool_name,
            "status": "failed",
            "is_error": True,
            "message": str(self),
            "provider": provider,
            "model": model,
            "error": error,
            "remediation": {
                "action": self.remediation,
                "model_instruction": self.model_instruction,
            },
            "execution": execution,
            "images" if result_type == "image_gen_tool_result" else "videos": [],
        }


__all__ = ["MediaErrorCategory", "MediaGenerationError"]
