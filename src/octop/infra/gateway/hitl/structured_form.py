"""Validation helpers for the generic structured HITL form protocol."""

from __future__ import annotations

import json
import re
from typing import Any

STRUCTURED_FORM_TOOL_NAME = "request_structured_form"
STRUCTURED_FORM_PROTOCOL = "octop.structured_form.v1"
STRUCTURED_FORM_SCHEMA_VERSION = 1
MAX_STRUCTURED_FORM_BYTES = 32_768
MAX_STRUCTURED_FORM_FIELDS = 64
MAX_STRUCTURED_FORM_OPTIONS = 64
MAX_STRUCTURED_FORM_OPTION_LENGTH = 120
MAX_STRUCTURED_FORM_TEXT_LENGTH = 4_096
MAX_STRUCTURED_FORM_PATTERN_LENGTH = 256
MAX_STRUCTURED_FORM_LABEL_LENGTH = 120
MAX_STRUCTURED_FORM_DESCRIPTION_LENGTH = 300
_DEFAULT_MIN_LENGTH = 0
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Field types understood by this protocol version.
_FIELD_TYPES = ("boolean", "enum", "integer", "string")

_COMMON_FIELD_KEYS = frozenset(
    {"key", "label", "type", "required", "nullable", "description", "group", "default"}
)
_TYPE_FIELD_KEYS: dict[str, frozenset[str]] = {
    "integer": frozenset({"min", "max", "step"}),
    "string": frozenset({"min_length", "max_length", "pattern", "multiline"}),
    "boolean": frozenset(),
    "enum": frozenset({"options"}),
}
_FIELD_ALLOWED = frozenset().union(_COMMON_FIELD_KEYS, *_TYPE_FIELD_KEYS.values())


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _field_error(key: str, message: str) -> str:
    """Prefix an error with its field key so the renderer can highlight it."""
    return f"structured form field '{key}': {message}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_negative_int(value: Any) -> bool:
    return _is_int(value) and value >= 0


def _compile_pattern(field: dict[str, Any], key: str) -> tuple[str | None, re.Pattern[str] | None]:
    pattern = field.get("pattern")
    if pattern is None:
        return None, None
    if not isinstance(pattern, str):
        return _field_error(key, "pattern must be a string"), None
    if len(pattern) > MAX_STRUCTURED_FORM_PATTERN_LENGTH:
        return _field_error(key, "pattern is too long"), None
    try:
        return None, re.compile(pattern)
    except re.error:
        return _field_error(key, "pattern is not a valid regular expression"), None


def _validate_string_payload(
    key: str,
    value: Any,
    min_length: int,
    max_length: int | None,
    compiled: re.Pattern[str] | None,
    label: str,
) -> str | None:
    if not isinstance(value, str):
        return _field_error(key, f"{label} must be a string")
    if len(value) < min_length:
        return _field_error(key, f"{label} must be at least {min_length} characters")
    if max_length is not None and len(value) > max_length:
        return _field_error(key, f"{label} must be at most {max_length} characters")
    if max_length is None and len(value) > MAX_STRUCTURED_FORM_TEXT_LENGTH:
        return _field_error(key, f"{label} must be at most {MAX_STRUCTURED_FORM_TEXT_LENGTH} characters")
    if compiled is not None and compiled.search(value) is None:
        return _field_error(key, f"{label} does not match the required pattern")
    return None


def _validate_integer_field(field: dict[str, Any], key: str) -> str | None:
    minimum = field.get("min", 0)
    maximum = field.get("max")
    if not _is_non_negative_int(minimum):
        return _field_error(key, "min must be a non-negative integer")
    if maximum is not None and (not _is_int(maximum) or maximum < minimum):
        return _field_error(key, "max must be an integer greater than or equal to min")
    if field.get("step", 1) != 1:
        return _field_error(key, "step must be 1")
    default = field.get("default")
    if default is None:
        return None
    if not _is_int(default):
        return _field_error(key, "default must be an integer")
    if default < minimum or (maximum is not None and default > maximum):
        return _field_error(key, "default is outside the allowed range")
    return None


def _validate_string_field(field: dict[str, Any], key: str) -> str | None:
    min_length = field.get("min_length", _DEFAULT_MIN_LENGTH)
    max_length = field.get("max_length")
    if not _is_int(min_length) or not 0 <= min_length <= MAX_STRUCTURED_FORM_TEXT_LENGTH:
        return _field_error(key, f"min_length must be an integer between 0 and {MAX_STRUCTURED_FORM_TEXT_LENGTH}")
    if max_length is not None:
        if not _is_int(max_length) or not min_length <= max_length <= MAX_STRUCTURED_FORM_TEXT_LENGTH:
            return _field_error(key, f"max_length must be an integer between min_length and {MAX_STRUCTURED_FORM_TEXT_LENGTH}")
    if not isinstance(field.get("multiline", False), bool):
        return _field_error(key, "multiline must be a boolean")
    pattern_error, compiled = _compile_pattern(field, key)
    if pattern_error:
        return pattern_error
    default = field.get("default")
    if default is None:
        return None
    return _validate_string_payload(key, default, min_length, max_length, compiled, "default")


def _validate_boolean_field(field: dict[str, Any], key: str) -> str | None:
    # null carries no boolean meaning, so a toggle can never be nullable.
    if field.get("nullable") is True:
        return _field_error(key, "boolean fields do not support nullable=true")
    default = field.get("default")
    if default is None:
        return None
    if not isinstance(default, bool):
        return _field_error(key, "default must be a boolean")
    return None


def _validate_enum_field(field: dict[str, Any], key: str) -> str | None:
    options = field.get("options")
    if not isinstance(options, list) or not 1 <= len(options) <= MAX_STRUCTURED_FORM_OPTIONS:
        return _field_error(key, f"options must contain between 1 and {MAX_STRUCTURED_FORM_OPTIONS} entries")
    seen: set[str] = set()
    for option in options:
        if not isinstance(option, str) or not option.strip():
            return _field_error(key, "options must be non-empty strings")
        if len(option) > MAX_STRUCTURED_FORM_OPTION_LENGTH:
            return _field_error(key, f"options must be at most {MAX_STRUCTURED_FORM_OPTION_LENGTH} characters")
        if option in seen:
            return _field_error(key, "options must be unique")
        seen.add(option)
    default = field.get("default")
    if default is None:
        return None
    if not isinstance(default, str) or default not in seen:
        return _field_error(key, "default must be one of options")
    return None


_FIELD_VALIDATORS = {
    "integer": _validate_integer_field,
    "string": _validate_string_field,
    "boolean": _validate_boolean_field,
    "enum": _validate_enum_field,
}


def _validate_common_field(field: dict[str, Any], key: str) -> str | None:
    label = field.get("label")
    if not isinstance(label, str) or not label.strip():
        return _field_error(key, "label is required")
    if len(label) > MAX_STRUCTURED_FORM_LABEL_LENGTH:
        return _field_error(key, f"label must be at most {MAX_STRUCTURED_FORM_LABEL_LENGTH} characters")
    required = field.get("required", False)
    nullable = field.get("nullable", True)
    if not isinstance(required, bool) or not isinstance(nullable, bool):
        return _field_error(key, "required and nullable must be booleans")
    if required and field.get("nullable") is True:
        return _field_error(key, "required fields cannot be nullable")
    description = field.get("description")
    if description is not None:
        if not isinstance(description, str):
            return _field_error(key, "description must be a string")
        if len(description) > MAX_STRUCTURED_FORM_DESCRIPTION_LENGTH:
            return _field_error(key, f"description must be at most {MAX_STRUCTURED_FORM_DESCRIPTION_LENGTH} characters")
    if field.get("group") is not None and not isinstance(field["group"], str):
        return _field_error(key, "group must be a string")
    return None


def _validate_field(field: dict[str, Any], key: str) -> str | None:
    field_type = field.get("type")
    if field_type not in _FIELD_TYPES:
        return _field_error(key, f"type must be one of: {', '.join(sorted(_FIELD_TYPES))}")
    stray = set(field) - _COMMON_FIELD_KEYS - _TYPE_FIELD_KEYS.get(field_type, frozenset())
    if stray:
        return _field_error(key, f"{', '.join(sorted(stray))} is not supported for {field_type} fields")
    common_error = _validate_common_field(field, key)
    if common_error:
        return common_error
    return _FIELD_VALIDATORS[field_type](field, key)


def validate_structured_form_request(args: Any) -> str | None:
    """Return a user-facing error when a form request is outside the contract."""
    if not isinstance(args, dict):
        return "structured form args must be an object"
    if _json_size(args) > MAX_STRUCTURED_FORM_BYTES:
        return "structured form request is too large"
    allowed = {
        "form_protocol",
        "form_id",
        "schema_version",
        "title",
        "description",
        "context",
        "submit_label",
        "timeout_seconds",
        "fields",
    }
    if set(args) - allowed:
        return "structured form request contains unsupported fields"
    if args.get("form_protocol") != STRUCTURED_FORM_PROTOCOL:
        return "unsupported structured form protocol"
    if args.get("schema_version") != STRUCTURED_FORM_SCHEMA_VERSION:
        return "unsupported structured form schema version"
    form_id = args.get("form_id")
    if not isinstance(form_id, str) or not re.fullmatch(r"^[a-z][a-z0-9_.-]*$", form_id):
        return "structured form form_id is invalid"
    if not isinstance(args.get("title"), str) or not args["title"].strip():
        return "structured form title is required"
    if (
        "description" in args
        and args["description"] is not None
        and not isinstance(args["description"], str)
    ):
        return "structured form description must be a string"
    if "context" in args and (not isinstance(args["context"], dict) or len(args["context"]) > 16):
        return "structured form context is invalid"
    if "submit_label" in args and not isinstance(args["submit_label"], str):
        return "structured form submit_label must be a string"
    timeout = args.get("timeout_seconds")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 30 or timeout > 3600
    ):
        return "structured form timeout_seconds must be an integer between 30 and 3600"
    fields = args.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_STRUCTURED_FORM_FIELDS:
        return "structured form must contain between 1 and 64 fields"
    keys: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            return "structured form field must be an object"
        if set(field) - _FIELD_ALLOWED:
            return "structured form field contains unsupported fields"
        key = field.get("key")
        if not isinstance(key, str) or not _FIELD_KEY_RE.fullmatch(key):
            return "structured form field key is invalid"
        if key in keys:
            return "structured form field keys must be unique"
        keys.add(key)
        error = _validate_field(field, key)
        if error:
            return error
    return None


def _value_error(field: dict[str, Any], key: str, value: Any) -> str | None:
    field_type = field.get("type")
    if field_type == "integer":
        if not _is_int(value):
            return _field_error(key, "value must be an integer")
        minimum = field.get("min", 0)
        maximum = field.get("max")
        if value < minimum or (maximum is not None and value > maximum):
            return _field_error(key, "value is outside the allowed range")
        return None
    if field_type == "string":
        pattern_error, compiled = _compile_pattern(field, key)
        if pattern_error:
            return pattern_error
        return _validate_string_payload(
            key,
            value,
            field.get("min_length", _DEFAULT_MIN_LENGTH),
            field.get("max_length"),
            compiled,
            "value",
        )
    if field_type == "boolean":
        if not isinstance(value, bool):
            return _field_error(key, "value must be a boolean")
        return None
    if field_type == "enum":
        options = field.get("options") or []
        if not isinstance(value, str) or value not in options:
            return _field_error(key, f"value must be one of: {', '.join(options)}")
        return None
    return _field_error(key, "field type is invalid")


def validate_structured_form_response(args: Any, message: Any) -> str | None:
    """Validate one ``respond`` message against the pending form request."""
    request_error = validate_structured_form_request(args)
    if request_error:
        return request_error
    if not isinstance(message, str):
        return "structured form response must be a JSON object"
    try:
        response = json.loads(message)
    except ValueError:
        return "structured form response must be valid JSON"
    if not isinstance(response, dict):
        return "structured form response must be a JSON object"
    if _json_size(response) > MAX_STRUCTURED_FORM_BYTES:
        return "structured form response is too large"
    allowed = {"form_protocol", "form_id", "schema_version", "submission_id", "context", "values"}
    if set(response) not in (allowed, allowed - {"context"}):
        return "structured form response has an invalid shape"
    if response["form_protocol"] != STRUCTURED_FORM_PROTOCOL:
        return "structured form response protocol does not match"
    if response["schema_version"] != STRUCTURED_FORM_SCHEMA_VERSION:
        return "structured form response schema version does not match"
    if response.get("form_id") != args.get("form_id"):
        return "structured form response form_id does not match"
    if "context" in response and (
        not isinstance(response["context"], dict) or len(response["context"]) > 16
    ):
        return "structured form response context is invalid"
    if not isinstance(response["submission_id"], str) or not response["submission_id"].strip():
        return "structured form submission_id is required"
    values = response["values"]
    if not isinstance(values, dict):
        return "structured form values must be an object"
    fields = args["fields"]
    keys = {field["key"] for field in fields}
    if set(values) - keys:
        return "structured form response values do not match the request"
    for field in fields:
        key = field["key"]
        required = field.get("required", False)
        nullable = field.get("nullable", True)
        if key not in values:
            if required:
                return _field_error(key, "value is required")
            continue
        value = values[key]
        if value is None:
            if required:
                return _field_error(key, "value is required")
            if not nullable:
                return _field_error(key, "value cannot be null")
            continue
        error = _value_error(field, key, value)
        if error:
            return error
    return None
