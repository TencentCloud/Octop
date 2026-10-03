"""``request_device_code`` must not let a bad ``interval`` escape as a raw TypeError.

``request_device_code`` normalizes every other failure of the device-code
response into a sanitized ``CodexOAuthDeviceCodeError``: HTTP errors, network
errors, undecodable bodies, a non-dict body, and finally the two required
fields (``device_auth_id`` / ``user_code``).The ``interval`` field -- read from
that very same dict -- was converted with a bare ``float()`` on the return line,
outside the ``try`` block, so a non-numeric value raised ``ValueError`` or
``TypeError`` straight through the module's own error contract.
"""

from __future__ import annotations

import json
import urllib.request
from unittest import mock

import pytest

from octop.infra.agents.providers.codex_oauth import (
    CodexOAuthDeviceCodeError,
    request_device_code,
)


class _Resp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _response(interval: object) -> _Resp:
    payload = json.dumps(
        {"device_auth_id": "dev-1", "user_code": "ABCD-1234", "interval": interval}
    ).encode()

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30) -> _Resp:
        return _Resp(payload)

    return mock.patch("urllib.request.urlopen", fake_urlopen)


@pytest.mark.parametrize("interval", [{"seconds": 5}, [5], "5s", "abc"])
def test_a_non_numeric_interval_is_reported_as_an_invalid_response(interval: object) -> None:
    with _response(interval), pytest.raises(CodexOAuthDeviceCodeError) as excinfo:
        request_device_code()

    assert excinfo.value.reason == "invalid_response"


@pytest.mark.parametrize("interval,expected", [(5, 5.0), (2.5, 2.5), (None, 5.0), (0, 5.0)])
def test_a_usable_interval_is_still_honoured(interval: object, expected: float) -> None:
    with _response(interval):
        info = request_device_code()

    assert info["interval_s"] == expected
