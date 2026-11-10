"""Error frames for dashboard turns rejected before they start."""

from __future__ import annotations

from octop.api.routers.chat.ws import _prepare_error_frame
from octop.infra.errors import ErrorCode, OctopError


def test_frame_carries_the_error_code() -> None:
    frame = _prepare_error_frame(OctopError(ErrorCode.CONNECTOR_MCP_LOAD_FAILED, "boom"))

    assert frame == {
        "type": "error",
        "message": "boom",
        "error_code": "CONNECTOR_MCP_LOAD_FAILED",
    }


def test_connector_auth_frame_says_which_connectors_to_authorize() -> None:
    details = {"connectors": [{"server": "wiki"}], "servers": "Wiki"}

    frame = _prepare_error_frame(
        OctopError(ErrorCode.CONNECTOR_AUTH_REQUIRED, "authorize Wiki", details=details)
    )

    assert frame["error_code"] == "CONNECTOR_AUTH_REQUIRED"
    assert frame["error_details"] == details
    assert frame["message"] == "authorize Wiki"
