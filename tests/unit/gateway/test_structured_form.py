"""Unit tests for the structured HITL form protocol validators."""

from __future__ import annotations

import json

import pytest

from octop.infra.gateway.hitl.structured_form import (
    MAX_STRUCTURED_FORM_FIELDS,
    STRUCTURED_FORM_PROTOCOL,
    STRUCTURED_FORM_SCHEMA_VERSION,
    validate_structured_form_request,
    validate_structured_form_response,
)


def _req(fields: list[dict], **overrides: object) -> dict:
    payload: dict = {
        "form_protocol": STRUCTURED_FORM_PROTOCOL,
        "schema_version": STRUCTURED_FORM_SCHEMA_VERSION,
        "form_id": "test_form",
        "title": "Test Form",
        "fields": fields,
    }
    payload.update(overrides)
    return payload


def _resp(values: dict, form_id: str = "test_form", submission_id: str = "sub-1") -> str:
    return json.dumps(
        {
            "form_protocol": STRUCTURED_FORM_PROTOCOL,
            "form_id": form_id,
            "schema_version": STRUCTURED_FORM_SCHEMA_VERSION,
            "submission_id": submission_id,
            "values": values,
        }
    )


# ---------------------------------------------------------------------------
# Integer field — regression
# ---------------------------------------------------------------------------


def test_integer_field_allows_valid_range() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer", "min": 1, "max": 50}])) is None


def test_integer_field_by_default_still_works() -> None:
    assert validate_structured_form_request(_req([{"key": "count", "label": "Count", "type": "integer"}])) is None


def test_integer_field_rejects_inverted_range() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer", "min": 10, "max": 5}])) is not None


def test_integer_field_rejects_negative_min() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer", "min": -1}])) is not None


def test_integer_field_validates_default_within_range() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer", "min": 1, "max": 50, "default": 3}])) is None


def test_integer_field_rejects_default_outside_range() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer", "min": 1, "max": 50, "default": 99}])) is not None


def test_integer_response_allows_valid_value() -> None:
    assert validate_structured_form_response(_req([{"key": "n", "label": "N", "type": "integer", "min": 1, "max": 50}]), _resp({"n": 3})) is None


def test_integer_response_rejects_bool() -> None:
    assert validate_structured_form_response(_req([{"key": "n", "label": "N", "type": "integer"}]), _resp({"n": True})) is not None


# ---------------------------------------------------------------------------
# String field
# ---------------------------------------------------------------------------


def test_string_field_allows_valid_definition() -> None:
    assert validate_structured_form_request(_req([{"key": "name", "label": "Name", "type": "string", "min_length": 3, "max_length": 20}])) is None


def test_string_field_allows_minimal_definition() -> None:
    assert validate_structured_form_request(_req([{"key": "name", "label": "Name", "type": "string"}])) is None


def test_string_field_rejects_inverted_length() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "min_length": 10, "max_length": 5}])) is not None


def test_string_field_rejects_invalid_pattern() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "pattern": "[unclosed"}])) is not None


def test_string_field_accepts_pattern() -> None:
    assert validate_structured_form_request(_req([{"key": "name", "label": "Name", "type": "string", "pattern": r"^[a-z][a-z0-9-]*$"}])) is None


def test_string_field_validates_default() -> None:
    assert validate_structured_form_request(_req([{"key": "name", "label": "Name", "type": "string", "default": "web-1"}])) is None


def test_string_field_rejects_default_too_short() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "min_length": 5, "default": "ab"}])) is not None


def test_string_field_rejects_default_not_matching_pattern() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "pattern": r"^\d+$", "default": "abc"}])) is not None


def test_string_field_accepts_multiline() -> None:
    assert validate_structured_form_request(_req([{"key": "desc", "label": "Description", "type": "string", "multiline": True}])) is None


def test_string_field_rejects_multiline_non_bool() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "multiline": "yes"}])) is not None


def test_string_response_allows_valid_value() -> None:
    assert validate_structured_form_response(_req([{"key": "name", "label": "Name", "type": "string"}]), _resp({"name": "web-1"})) is None


def test_string_response_rejects_non_string() -> None:
    assert validate_structured_form_response(_req([{"key": "name", "label": "Name", "type": "string"}]), _resp({"name": 42})) is not None


def test_string_response_rejects_too_short() -> None:
    assert validate_structured_form_response(_req([{"key": "name", "label": "Name", "type": "string", "min_length": 5}]), _resp({"name": "ab"})) is not None


def test_string_response_rejects_pattern_mismatch() -> None:
    request = _req([{"key": "name", "label": "Name", "type": "string", "pattern": r"^[a-z][a-z0-9-]*$"}])
    assert validate_structured_form_response(request, _resp({"name": "Web_1"})) is not None


def test_string_response_applies_pattern() -> None:
    request = _req([{"key": "name", "label": "Name", "type": "string", "pattern": r"^[a-z][a-z0-9-]*$"}])
    assert validate_structured_form_response(request, _resp({"name": "web-1"})) is None


# ---------------------------------------------------------------------------
# Boolean field
# ---------------------------------------------------------------------------


def test_boolean_field_allows_valid_definition() -> None:
    assert validate_structured_form_request(_req([{"key": "public", "label": "Public", "type": "boolean"}])) is None


def test_boolean_field_rejects_nullable() -> None:
    assert validate_structured_form_request(_req([{"key": "flag", "label": "Flag", "type": "boolean", "nullable": True}])) is not None


def test_boolean_field_accepts_default() -> None:
    assert validate_structured_form_request(_req([{"key": "flag", "label": "Flag", "type": "boolean", "default": False}])) is None


def test_boolean_field_rejects_non_bool_default() -> None:
    assert validate_structured_form_request(_req([{"key": "flag", "label": "Flag", "type": "boolean", "default": 1}])) is not None


def test_boolean_response_allows_true() -> None:
    assert validate_structured_form_response(_req([{"key": "flag", "label": "Flag", "type": "boolean"}]), _resp({"flag": True})) is None


def test_boolean_response_allows_false() -> None:
    assert validate_structured_form_response(_req([{"key": "flag", "label": "Flag", "type": "boolean"}]), _resp({"flag": False})) is None


def test_boolean_response_rejects_string() -> None:
    assert validate_structured_form_response(_req([{"key": "flag", "label": "Flag", "type": "boolean"}]), _resp({"flag": "yes"})) is not None


def test_boolean_response_rejects_int() -> None:
    assert validate_structured_form_response(_req([{"key": "flag", "label": "Flag", "type": "boolean"}]), _resp({"flag": 1})) is not None


# ---------------------------------------------------------------------------
# Enum field
# ---------------------------------------------------------------------------


def test_enum_field_allows_valid_definition() -> None:
    assert validate_structured_form_request(_req([{"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"]}])) is None


def test_enum_field_rejects_empty_options() -> None:
    assert validate_structured_form_request(_req([{"key": "e", "label": "E", "type": "enum", "options": []}])) is not None


def test_enum_field_rejects_duplicate_options() -> None:
    assert validate_structured_form_request(_req([{"key": "e", "label": "E", "type": "enum", "options": ["a", "a"]}])) is not None


def test_enum_field_rejects_blank_option() -> None:
    assert validate_structured_form_request(_req([{"key": "e", "label": "E", "type": "enum", "options": ["a", "   "]}])) is not None


def test_enum_field_accepts_default() -> None:
    assert validate_structured_form_request(_req([{"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"], "default": "sms"}])) is None


def test_enum_field_rejects_default_outside_options() -> None:
    assert validate_structured_form_request(_req([{"key": "e", "label": "E", "type": "enum", "options": ["a", "b"], "default": "c"}])) is not None


def test_enum_response_allows_valid_option() -> None:
    assert validate_structured_form_response(_req([{"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"]}]), _resp({"channel": "sms"})) is None


def test_enum_response_rejects_unknown_option() -> None:
    assert validate_structured_form_response(_req([{"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"]}]), _resp({"channel": "slack"})) is not None


def test_enum_response_rejects_non_string() -> None:
    assert validate_structured_form_response(_req([{"key": "channel", "label": "Channel", "type": "enum", "options": ["sms"]}]), _resp({"channel": 1})) is not None


# ---------------------------------------------------------------------------
# Unknown type
# ---------------------------------------------------------------------------


def test_request_rejects_unknown_type() -> None:
    assert validate_structured_form_request(_req([{"key": "f", "label": "F", "type": "float"}])) is not None


def test_request_rejects_unknown_type_for_empty_custom_config() -> None:
    assert validate_structured_form_request(_req([{"key": "f", "label": "F", "type": "date"}])) is not None


# ---------------------------------------------------------------------------
# Mixed fields
# ---------------------------------------------------------------------------


def test_request_accepts_all_four_types() -> None:
    assert validate_structured_form_request(_req([
        {"key": "replicas", "label": "Replicas", "type": "integer", "required": True, "min": 1, "max": 50},
        {"key": "name", "label": "Name", "type": "string", "min_length": 3},
        {"key": "public", "label": "Public", "type": "boolean"},
        {"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"]},
    ])) is None


def test_response_accepts_mixed_values() -> None:
    request = _req([
        {"key": "replicas", "label": "Replicas", "type": "integer", "min": 1, "max": 50},
        {"key": "name", "label": "Name", "type": "string"},
        {"key": "public", "label": "Public", "type": "boolean"},
        {"key": "channel", "label": "Channel", "type": "enum", "options": ["sms", "email"]},
    ])
    assert validate_structured_form_response(request, _resp({"replicas": 3, "name": "web-1", "public": True, "channel": "sms"})) is None


# ---------------------------------------------------------------------------
# Stray keys per type
# ---------------------------------------------------------------------------

def test_string_field_rejects_integer_only_keys() -> None:
    assert validate_structured_form_request(_req([{"key": "s", "label": "S", "type": "string", "min": 5}])) is not None


def test_boolean_field_rejects_unwanted_keys() -> None:
    assert validate_structured_form_request(_req([{"key": "flag", "label": "Flag", "type": "boolean", "options": ["x"]}])) is not None


def test_enum_field_rejects_integer_only_keys() -> None:
    assert validate_structured_form_request(_req([{"key": "e", "label": "E", "type": "enum", "options": ["a"], "min": 5}])) is not None


# ---------------------------------------------------------------------------
# Envelope-level validation (regression)
# ---------------------------------------------------------------------------


def test_request_rejects_wrong_protocol() -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer"}], form_protocol="v2")) is not None


def test_request_rejects_duplicate_keys() -> None:
    assert validate_structured_form_request(_req([
        {"key": "a", "label": "A", "type": "integer"},
        {"key": "a", "label": "B", "type": "string"},
    ])) is not None


def test_request_rejects_empty_fields() -> None:
    assert validate_structured_form_request(_req([])) is not None


def test_request_accepts_max_fields() -> None:
    fields = [{"key": f"f{i}", "label": f"F{i}", "type": "integer"} for i in range(MAX_STRUCTURED_FORM_FIELDS)]
    assert validate_structured_form_request(_req(fields)) is None


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


def test_response_rejects_unknown_field_key() -> None:
    assert validate_structured_form_response(_req([{"key": "a", "label": "A", "type": "integer"}]), _resp({"b": 1})) is not None


def test_response_allows_omitted_optional_field() -> None:
    assert validate_structured_form_response(_req([{"key": "a", "label": "A", "type": "integer"}]), _resp({})) is None


def test_response_requires_required_field() -> None:
    request = _req([{"key": "a", "label": "A", "type": "integer", "required": True}])
    assert validate_structured_form_response(request, _resp({})) is not None


def test_response_rejects_null_for_non_nullable() -> None:
    request = _req([{"key": "a", "label": "A", "type": "integer", "nullable": False}])
    assert validate_structured_form_response(request, _resp({"a": None})) is not None


# ---------------------------------------------------------------------------
# timeout_seconds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("timeout", [30, 60, 300, 3600])
def test_request_accepts_valid_timeout(timeout: int) -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer"}], timeout_seconds=timeout)) is None


@pytest.mark.parametrize("timeout", [0, 29, 3601, -5])
def test_request_rejects_invalid_timeout(timeout: int) -> None:
    assert validate_structured_form_request(_req([{"key": "n", "label": "N", "type": "integer"}], timeout_seconds=timeout)) is not None
