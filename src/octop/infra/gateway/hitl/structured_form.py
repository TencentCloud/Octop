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
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def validate_structured_form_request(args: Any) -> str | None:
    """Return a user-facing error when a form request is outside the MVP contract."""
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
    if "description" in args and args["description"] is not None and not isinstance(args["description"], str):
        return "structured form description must be a string"
    if "context" in args and (
        not isinstance(args["context"], dict) or len(args["context"]) > 16
    ):
        return "structured form context is invalid"
    if "submit_label" in args and not isinstance(args["submit_label"], str):
        return "structured form submit_label must be a string"
    fields = args.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_STRUCTURED_FORM_FIELDS:
        return "structured form must contain between 1 and 64 fields"
    keys: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            return "structured form field must be an object"
        field_allowed = {"key", "label", "type", "required", "nullable", "min", "max", "step", "group"}
        if set(field) - field_allowed:
            return "structured form field contains unsupported fields"
        key = field.get("key")
        if not isinstance(key, str) or not _FIELD_KEY_RE.fullmatch(key):
            return "structured form field key is invalid"
        if key in keys:
            return "structured form field keys must be unique"
        keys.add(key)
        if not isinstance(field.get("label"), str) or not field["label"].strip():
            return "structured form field label is required"
        if field.get("type") != "integer":
            return "structured form supports integer fields only"
        required = field.get("required", True)
        nullable = field.get("nullable", False)
        if not isinstance(required, bool) or not isinstance(nullable, bool):
            return "structured form required and nullable must be booleans"
        if required and nullable:
            return "required structured form fields cannot be nullable"
        minimum = field.get("min", 0)
        maximum = field.get("max")
        step = field.get("step", 1)
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
            return "structured form min must be a non-negative integer"
        if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < minimum):
            return "structured form max must be an integer greater than or equal to min"
        if step != 1:
            return "structured form step must be 1"
    return None


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
    if "context" in response and (not isinstance(response["context"], dict) or len(response["context"]) > 16):
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
        if key not in values:
            if field.get("required", True):
                return "structured form value is required"
            continue
        value = values[key]
        if value is None:
            if field.get("required", True) or not field.get("nullable", False):
                return "structured form value is required"
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            return "structured form value must be an integer or null"
        maximum = field.get("max")
        if value < field.get("min", 0) or (maximum is not None and value > maximum):
            return "structured form value is outside the allowed range"
    return None
