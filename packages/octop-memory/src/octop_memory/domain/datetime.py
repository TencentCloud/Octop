"""Datetime normalization rules shared across memory layers."""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime, interpreting legacy naive values as UTC.

    Persisted memory timestamps are intended to describe an absolute instant.
    Older Episode rows and imperfect LLM output may omit the timezone suffix;
    treating those values as UTC matches the extractor prompt and the fallback
    raw-event timestamps while keeping legacy stores readable.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime_utc(value: str) -> datetime:
    """Parse an ISO 8601 timestamp and normalize it to aware UTC."""
    return as_utc(datetime.fromisoformat(value))
