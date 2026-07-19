"""Stable error codes and the typed exception that crosses API boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from octop.i18n import error_message as i18n_error_message
from octop.infra.utils.locale import Locale, normalize_locale


class ErrorCode(StrEnum):
    AUTH_FAILED = "AUTH_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    SETUP_REQUIRED = "SETUP_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    USER_DISABLED = "USER_DISABLED"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_FAILED = "AGENT_FAILED"
    AGENT_BUSY = "AGENT_BUSY"
    AGENT_NAME_TAKEN = "AGENT_NAME_TAKEN"
    PROVIDER_NAME_TAKEN = "PROVIDER_NAME_TAKEN"
    PROVIDER_NOT_VISIBLE = "PROVIDER_NOT_VISIBLE"
    PROVIDER_REFERENCED = "PROVIDER_REFERENCED"
    STORAGE_BACKEND_NAME_TAKEN = "STORAGE_BACKEND_NAME_TAKEN"
    STORAGE_BACKEND_REFERENCED = "STORAGE_BACKEND_REFERENCED"
    CHANNEL_KIND_UNSUPPORTED = "CHANNEL_KIND_UNSUPPORTED"
    CHANNEL_INVALID_CREDENTIALS = "CHANNEL_INVALID_CREDENTIALS"
    CHANNEL_NAME_TAKEN = "CHANNEL_NAME_TAKEN"
    CONNECTOR_NOT_FOUND = "CONNECTOR_NOT_FOUND"
    CONNECTOR_INVALID_CREDENTIALS = "CONNECTOR_INVALID_CREDENTIALS"
    CONNECTOR_KIND_UNSUPPORTED = "CONNECTOR_KIND_UNSUPPORTED"
    CONNECTOR_NOT_BOUND = "CONNECTOR_NOT_BOUND"
    CONNECTOR_ALREADY_BOUND = "CONNECTOR_ALREADY_BOUND"
    CRON_TRIGGER_INVALID = "CRON_TRIGGER_INVALID"
    SLASH_UNKNOWN = "SLASH_UNKNOWN"
    SLASH_BAD_ARGS = "SLASH_BAD_ARGS"
    VOICE_BROWSER_ONLY = "VOICE_BROWSER_ONLY"
    VOICE_KIND_UNSUPPORTED = "VOICE_KIND_UNSUPPORTED"
    VOICE_CAPABILITY_MISMATCH = "VOICE_CAPABILITY_MISMATCH"
    VOICE_PROVIDER_DISABLED = "VOICE_PROVIDER_DISABLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TLS_NOT_ELIGIBLE = "TLS_NOT_ELIGIBLE"
    TLS_ISSUE_IN_PROGRESS = "TLS_ISSUE_IN_PROGRESS"
    TLS_DOMAIN_MISMATCH = "TLS_DOMAIN_MISMATCH"
    WORKSPACE_OP_UNSUPPORTED = "WORKSPACE_OP_UNSUPPORTED"
    SKILL_IMPORT_UNSUPPORTED_URL = "SKILL_IMPORT_UNSUPPORTED_URL"
    SKILL_IMPORT_FAILED = "SKILL_IMPORT_FAILED"
    SKILL_ALREADY_EXISTS = "SKILL_ALREADY_EXISTS"
    DESKTOP_SESSION_LIMIT = "DESKTOP_SESSION_LIMIT"
    DESKTOP_CAPTURE_FAILED = "DESKTOP_CAPTURE_FAILED"


_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.AUTH_FAILED: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.SETUP_REQUIRED: 409,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.USER_DISABLED: 403,
    ErrorCode.LOGIN_LOCKED: 429,
    ErrorCode.USERNAME_TAKEN: 409,
    ErrorCode.AGENT_NOT_FOUND: 404,
    ErrorCode.AGENT_FAILED: 500,
    ErrorCode.AGENT_BUSY: 409,
    ErrorCode.AGENT_NAME_TAKEN: 409,
    ErrorCode.PROVIDER_NAME_TAKEN: 409,
    ErrorCode.PROVIDER_NOT_VISIBLE: 400,
    ErrorCode.PROVIDER_REFERENCED: 409,
    ErrorCode.STORAGE_BACKEND_NAME_TAKEN: 409,
    ErrorCode.STORAGE_BACKEND_REFERENCED: 409,
    ErrorCode.CHANNEL_KIND_UNSUPPORTED: 400,
    ErrorCode.CHANNEL_INVALID_CREDENTIALS: 400,
    ErrorCode.CHANNEL_NAME_TAKEN: 409,
    ErrorCode.CONNECTOR_NOT_FOUND: 404,
    ErrorCode.CONNECTOR_INVALID_CREDENTIALS: 400,
    ErrorCode.CONNECTOR_KIND_UNSUPPORTED: 400,
    ErrorCode.CONNECTOR_NOT_BOUND: 400,
    ErrorCode.CONNECTOR_ALREADY_BOUND: 409,
    ErrorCode.CRON_TRIGGER_INVALID: 400,
    ErrorCode.SLASH_UNKNOWN: 400,
    ErrorCode.SLASH_BAD_ARGS: 400,
    ErrorCode.VOICE_BROWSER_ONLY: 422,
    ErrorCode.VOICE_KIND_UNSUPPORTED: 400,
    ErrorCode.VOICE_CAPABILITY_MISMATCH: 400,
    ErrorCode.VOICE_PROVIDER_DISABLED: 400,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.TLS_NOT_ELIGIBLE: 403,
    ErrorCode.TLS_ISSUE_IN_PROGRESS: 409,
    ErrorCode.TLS_DOMAIN_MISMATCH: 400,
    ErrorCode.WORKSPACE_OP_UNSUPPORTED: 400,
    ErrorCode.SKILL_IMPORT_UNSUPPORTED_URL: 400,
    ErrorCode.SKILL_IMPORT_FAILED: 502,
    ErrorCode.SKILL_ALREADY_EXISTS: 409,
    ErrorCode.DESKTOP_SESSION_LIMIT: 429,
    ErrorCode.DESKTOP_CAPTURE_FAILED: 503,
}


@dataclass
class OctopError(Exception):
    code: ErrorCode
    message: str
    status: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status == 0:
            self.status = _DEFAULT_STATUS[self.code]
        super().__init__(self.message)

    def localized_message(self, locale: str | Locale, **kwargs: object) -> str:
        loc = normalize_locale(str(locale))
        try:
            return i18n_error_message(self.code.value, loc, **{**self.details, **kwargs})
        except KeyError:
            return self.message

    @classmethod
    def localized(
        cls,
        code: ErrorCode,
        locale: str | Locale = "en",
        *,
        message: str | None = None,
        status: int = 0,
        details: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> OctopError:
        msg = (
            message
            if message is not None
            else i18n_error_message(code.value, normalize_locale(str(locale)), **kwargs)
        )
        return cls(code, msg, status=status, details=details or {})

    def to_envelope(self, *, locale: str | Locale | None = None) -> dict[str, Any]:
        message = self.localized_message(locale) if locale is not None else self.message
        return {
            "error": {
                "code": self.code.value,
                "message": message,
                "details": self.details,
            }
        }
