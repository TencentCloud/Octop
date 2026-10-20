"""Classification of object-store / probe I/O errors."""

from __future__ import annotations

from octop_harness.backends.probe import probe_backend
from octop_harness.backends.storage_errors import (
    classify_storage_error,
    format_storage_error,
    wrap_io_error,
)


def test_nosuchbucket_boto_string() -> None:
    raw = (
        "write failed: Error writing "
        "'/.harness-probe-74c04578410540b9b132b541ef8edc62.txt': "
        "An error occurred (NoSuchBucket) when calling the PutObject operation: "
        "The specified bucket does not exist."
    )
    classified = classify_storage_error(raw, op="write")
    assert classified.message_key == "probe_no_such_bucket"
    assert "harness-probe" not in classified.message
    assert "PutObject" not in classified.message
    assert "bucket" in classified.message.lower()


def test_format_storage_error_strips_sdk_boilerplate() -> None:
    text = format_storage_error(
        "An error occurred (NoSuchBucket) when calling the PutObject operation: The specified bucket does not exist."
    )
    assert text == "The specified bucket does not exist. Check the bucket name."


def test_wrap_io_error_keeps_path() -> None:
    err = wrap_io_error(
        "writing",
        "/SOUL.md",
        "An error occurred (AccessDenied) when calling the PutObject operation: Access Denied",
    )
    assert err.startswith("Error writing '/SOUL.md':")
    assert "access" in err.lower()
    assert "PutObject" not in err


def test_invalid_access_key() -> None:
    classified = classify_storage_error(
        "An error occurred (InvalidAccessKeyId) when calling the PutObject operation: "
        "The AWS Access Key Id you provided does not exist in our records.",
        op="write",
    )
    assert classified.message_key == "probe_invalid_credentials"


def test_connection_refused() -> None:
    classified = classify_storage_error("could not connect to server: Connection refused", op="write")
    assert classified.message_key == "probe_connection_failed"


def test_postgres_database_missing() -> None:
    classified = classify_storage_error('database "backend" does not exist', op="write")
    assert classified.message_key == "probe_database_missing"


def test_unknown_write_error_keeps_cleaned_detail() -> None:
    classified = classify_storage_error(
        "Error writing '/.harness-probe-abc.txt': widget frobnicator exploded",
        op="write",
    )
    assert classified.message_key == "probe_write_failed"
    assert classified.message == "widget frobnicator exploded"
    assert "harness-probe" not in classified.message


def test_probe_write_failure_uses_message_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class _Write:
        error = (
            "Error writing '/.harness-probe-x.txt': "
            "An error occurred (NoSuchBucket) when calling the PutObject operation: "
            "The specified bucket does not exist."
        )

    class _Backend:
        def write(self, path: str, content: str) -> _Write:
            del path, content
            return _Write()

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "octop_harness.backends.probe._resolve_probe_backend",
        lambda spec, workspace_dir=None: _Backend(),
    )
    result = probe_backend(
        {
            "type": "s3",
            "bucket": "missing",
            "access_key_id": "ak",
            "secret_access_key": "sk",
            "region": "us-east-1",
        }
    )
    assert result["ok"] is False
    assert result["message_key"] == "probe_no_such_bucket"
    assert "harness-probe" not in result["message"]
    assert "write failed" not in result["message"]
