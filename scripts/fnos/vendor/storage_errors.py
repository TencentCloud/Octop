"""Vendored from octop-harness until PyPI ships ``backends.storage_errors``.

Native FPK CI copies this file into site-packages so ``octop.launch`` can import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_BOTO_RE = re.compile(
    r"An error occurred \((?P<code>[^)]+)\) when calling the (?P<op>\S+) operation:\s*(?P<msg>.*)",
    re.IGNORECASE | re.DOTALL,
)
_IO_WRAP_RE = re.compile(
    r"^(?:(?:write|read|delete|check) failed:\s*)?"
    r"(?:Error (?:writing|checking|reading|listing) (?P<q>['\"]).+?(?P=q):\s*)?",
    re.IGNORECASE | re.DOTALL,
)
_PROBE_PATH_RE = re.compile(
    r"/?\.?(?:harness|octop)-probe-[0-9a-f]+\.txt",
    re.IGNORECASE,
)
_CODE_IN_PARENS_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9]{2,})\)")

_CODE_KEYS: dict[str, str] = {
    "NoSuchBucket": "probe_no_such_bucket",
    "NoSuchBucketError": "probe_no_such_bucket",
    "NoSuchKey": "probe_no_such_key",
    "AccessDenied": "probe_access_denied",
    "AccessForbidden": "probe_access_denied",
    "AccessDeniedError": "probe_access_denied",
    "Forbidden": "probe_access_denied",
    "InvalidAccessKeyId": "probe_invalid_credentials",
    "InvalidAccessKey": "probe_invalid_credentials",
    "InvalidSecurity": "probe_invalid_credentials",
    "SignatureDoesNotMatch": "probe_signature_mismatch",
    "AuthorizationHeaderMalformed": "probe_signature_mismatch",
    "AuthFailure": "probe_invalid_credentials",
    "InvalidBucketName": "probe_invalid_bucket",
    "PermanentRedirect": "probe_invalid_endpoint",
    "TemporaryRedirect": "probe_invalid_endpoint",
    "IllegalLocationConstraintException": "probe_invalid_endpoint",
    "InvalidEndpoint": "probe_invalid_endpoint",
    "RequestTimeout": "probe_timeout",
    "RequestTimeoutException": "probe_timeout",
    "SlowDown": "probe_timeout",
    "NotImplemented": "probe_s3_incompatible",
}

_FRIENDLY: dict[str, str] = {
    "probe_no_such_bucket": "The specified bucket does not exist. Check the bucket name.",
    "probe_no_such_key": "The object was not found.",
    "probe_access_denied": "Access denied. Check the access key and bucket permissions.",
    "probe_invalid_credentials": "Invalid credentials. Check the access key and secret key.",
    "probe_invalid_bucket": "The bucket name is invalid.",
    "probe_invalid_endpoint": "Endpoint or region does not match this bucket.",
    "probe_timeout": "The storage request timed out. Check the endpoint and network.",
    "probe_connection_failed": "Could not connect to the storage service. Check the endpoint and network.",
    "probe_database_missing": "The specified database does not exist.",
    "probe_content_mismatch": "Read-back content did not match what was written.",
    "probe_write_failed": "Could not write a test file.",
    "probe_read_failed": "Could not read the test file back.",
    "probe_delete_failed": "Could not delete the test file.",
    "probe_config_incomplete": "Configuration is incomplete.",
    "probe_s3_incompatible": (
        "This S3-compatible store rejected the request. Check the endpoint, "
        "or try path-style addressing in advanced settings."
    ),
    "probe_signature_mismatch": (
        "The store rejected the request signature. Check the endpoint, "
        "or try path-style addressing in advanced settings."
    ),
}

_PHRASE_KEYS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"specified bucket does not exist|nosuchbucket|no such bucket", re.I),
        "probe_no_such_bucket",
    ),
    (re.compile(r"invalid bucket name", re.I), "probe_invalid_bucket"),
    (re.compile(r"access denied|not authorized|forbidden", re.I), "probe_access_denied"),
    (
        re.compile(
            r"invalid access key|the aws access key id you provided does not exist",
            re.I,
        ),
        "probe_invalid_credentials",
    ),
    (
        re.compile(
            r"signaturedoesnotmatch|signature does not match|signature we calculated",
            re.I,
        ),
        "probe_signature_mismatch",
    ),
    (
        re.compile(r"password authentication failed|auth(?:entication)? failed", re.I),
        "probe_invalid_credentials",
    ),
    (re.compile(r'database ["\'].+["\'] does not exist', re.I), "probe_database_missing"),
    (
        re.compile(
            r"endpointconnectionerror|could not connect|connection refused|name or service not known|"
            r"nodename nor servname|failed to (?:establish|resolve)|getaddrinfo failed",
            re.I,
        ),
        "probe_connection_failed",
    ),
    (re.compile(r"timed? ?out|timeout", re.I), "probe_timeout"),
    (
        re.compile(r"permanentredirect|illegal location|invalid endpoint", re.I),
        "probe_invalid_endpoint",
    ),
    (
        re.compile(r"functionality that is not implemented|not implemented", re.I),
        "probe_s3_incompatible",
    ),
)

_OP_KEYS = {
    "write": "probe_write_failed",
    "read": "probe_read_failed",
    "delete": "probe_delete_failed",
}


@dataclass(frozen=True)
class ClassifiedStorageError:
    message: str
    message_key: str | None = None
    code: str | None = None

    def as_probe_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "message": self.message}
        if self.message_key:
            out["message_key"] = self.message_key
        return out


def extract_storage_error_code(exc: BaseException | str) -> str | None:
    """Best-effort error code from boto3 / COS / OSS / OBS / a string."""
    if isinstance(exc, BaseException):
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = response.get("Error", {}).get("Code")
            if code:
                return str(code)
        for attr in ("get_error_code", "get_code"):
            fn = getattr(exc, attr, None)
            if callable(fn):
                try:
                    code = fn()
                except Exception:  # noqa: BLE001 — SDK helpers vary
                    code = None
                if code:
                    return str(code)
        for attr in ("code", "error_code"):
            value = getattr(exc, attr, None)
            if isinstance(value, str) and value.isalnum() and value[0].isalpha():
                return value
    match = _BOTO_RE.search(str(exc))
    if match:
        return match.group("code")
    match = _CODE_IN_PARENS_RE.search(str(exc))
    if match:
        return match.group(1)
    return None


def format_storage_error(exc: BaseException | str) -> str:
    """Short reason without I/O wrappers, probe filenames, or SDK boilerplate."""
    return classify_storage_error(exc).message


def wrap_io_error(action: str, path: str, exc: BaseException | str) -> str:
    """Protocol-facing I/O error that keeps the path but humanizes the SDK text."""
    return f"Error {action} {path!r}: {format_storage_error(exc)}"


def classify_storage_error(
    raw: BaseException | str | None,
    *,
    op: str | None = None,
) -> ClassifiedStorageError:
    """Map a raw SDK / protocol error onto a probe ``message_key`` + short text."""
    if raw is None:
        key = _OP_KEYS.get(op or "", "probe_write_failed")
        return ClassifiedStorageError(message=_FRIENDLY[key], message_key=key)

    code = extract_storage_error_code(raw)
    key = _CODE_KEYS.get(code or "")
    detail = _clean_error_text(raw)
    if key is None:
        key = _key_from_phrases(f"{code or ''} {detail}")
    if key:
        return ClassifiedStorageError(message=_FRIENDLY[key], message_key=key, code=code)

    op_key = _OP_KEYS.get(op or "")
    if op_key:
        return ClassifiedStorageError(
            message=detail or _FRIENDLY[op_key],
            message_key=op_key,
            code=code,
        )
    return ClassifiedStorageError(message=detail or str(raw), code=code)


def classify_probe_exception(exc: BaseException) -> ClassifiedStorageError:
    """Classify a probe-level exception (connect / import / config)."""
    text = str(exc).strip()
    if "incomplete" in text.lower() or "is required" in text.lower():
        return ClassifiedStorageError(
            message=_FRIENDLY["probe_config_incomplete"] if "incomplete" in text.lower() else text,
            message_key="probe_config_incomplete" if "incomplete" in text.lower() else None,
        )
    classified = classify_storage_error(exc)
    if classified.message_key:
        return classified
    return ClassifiedStorageError(message=text)


def _key_from_phrases(text: str) -> str | None:
    for pattern, key in _PHRASE_KEYS:
        if pattern.search(text):
            return key
    return None


def _clean_error_text(raw: BaseException | str) -> str:
    text = str(raw).strip()
    boto = _BOTO_RE.search(text)
    if boto:
        text = (boto.group("msg") or "").strip() or boto.group("code")
    text = _IO_WRAP_RE.sub("", text).strip()
    text = _PROBE_PATH_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" :-")
    return text
