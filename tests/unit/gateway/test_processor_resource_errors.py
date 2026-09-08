"""Resource-policy stream error projection tests."""

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.processor import _stream_error


def test_stream_error_preserves_resource_error_code() -> None:
    error = OctopError(
        ErrorCode.TOKEN_QUOTA_EXCEEDED,
        "token quota exceeded",
        details={"used": 12, "quota": 10},
    )

    message, code = _stream_error(error, "zh")

    assert code == "TOKEN_QUOTA_EXCEEDED"
    assert "12/10" in message
