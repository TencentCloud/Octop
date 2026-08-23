"""Tests for email normalize / validate helpers."""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.email import normalize_email, parse_optional_email, validate_email_format


def test_normalize_email() -> None:
    assert normalize_email(None) is None
    assert normalize_email("") is None
    assert normalize_email("  ") is None
    assert normalize_email("Alice@Example.COM") == "alice@example.com"


def test_validate_email_format() -> None:
    validate_email_format("a@b.co")
    with pytest.raises(OctopError) as exc:
        validate_email_format("not-an-email")
    assert exc.value.code is ErrorCode.EMAIL_INVALID


def test_parse_optional_email() -> None:
    assert parse_optional_email(None) is None
    assert parse_optional_email("  ") is None
    assert parse_optional_email("Bob@Host.IO") == "bob@host.io"
    with pytest.raises(OctopError) as exc:
        parse_optional_email("bad")
    assert exc.value.code is ErrorCode.EMAIL_INVALID
