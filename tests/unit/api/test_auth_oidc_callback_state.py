"""``oidc_callback`` must degrade a malformed state, not raise.

``secrets.compare_digest`` only accepts ASCII ``str`` operands:

```python
>>> secrets.compare_digest("abc", "\u00fc")
TypeError: comparing strings with non-ASCII characters is not supported
```

``state`` here is a raw query parameter, fully attacker-controlled, and the
comparison sits *inside* the ``if`` condition — so the ``TypeError`` escapes the
route and lands on the global handler as a 500. Every other malformed-state
path (missing, empty, mismatched) redirects to ``/login?oidc_error=state``.

The same file already shape-checks the value on the way out
(``oidc_start``: ``if not isinstance(state, str)``), and the sibling
``sso/service.py`` funnels every bad-state case into ``_error_redirect``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import Request

from octop.api.common import sso_cookie
from octop.api.routers import auth_oidc


def _request(state: str | None) -> Request:
    """A GET request whose query carries ``state`` and whose cookie holds the original."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/oidc/callback",
        "raw_path": b"/api/auth/oidc/callback",
        "root_path": "",
        "scheme": "https",
        "query_string": f"state={state}".encode(),
        "headers": [(b"host", b"octop.test")],
        "client": ("127.0.0.1", 12345),
        "server": ("octop.test", 443),
    }
    if state is not None:
        scope["headers"].append((b"cookie", f"{sso_cookie.SSO_STATE_COOKIE}={state}".encode()))
    return Request(scope)


def _server() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        pytest.param("\u00fc", id="latin-1"),
        pytest.param("\u4e2d\u6587", id="cjk"),
        pytest.param("\U0001f600", id="emoji"),
        pytest.param("ok\u00fc", id="ascii-prefixed"),
    ],
)
async def test_non_ascii_state_redirects_instead_of_raising(
    state: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_oidc, "_public_base", lambda request: "https://octop.test")
    monkeypatch.setattr(
        auth_oidc, "_login_error_redirect", lambda server, base: "https://octop.test"
    )
    monkeypatch.setattr(auth_oidc, "delete_sso_state_cookie", lambda response, request: None)

    response = await auth_oidc.oidc_callback(
        request=_request(state), code="ignored", state=state, error=None, server=_server()
    )

    assert response.status_code == 302
    assert "oidc_error=state" in response.headers["location"]


@pytest.mark.asyncio
async def test_ascii_mismatch_still_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: the ordinary mismatch path is unchanged."""
    monkeypatch.setattr(auth_oidc, "_public_base", lambda request: "https://octop.test")
    monkeypatch.setattr(
        auth_oidc, "_login_error_redirect", lambda server, base: "https://octop.test"
    )
    monkeypatch.setattr(auth_oidc, "delete_sso_state_cookie", lambda response, request: None)

    response = await auth_oidc.oidc_callback(
        request=_request("expected"), code="c", state="other", error=None, server=_server()
    )

    assert response.status_code == 302
    assert "oidc_error=state" in response.headers["location"]


@pytest.mark.asyncio
async def test_matching_ascii_state_reaches_handle_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control: a legitimate ASCII match still proceeds to the service."""
    monkeypatch.setattr(auth_oidc, "_public_base", lambda request: "https://octop.test")
    monkeypatch.setattr(auth_oidc, "delete_sso_state_cookie", lambda response, request: None)

    service = MagicMock()

    async def _handle(**kwargs: object) -> MagicMock:
        return MagicMock(url="https://octop.test/agents")

    service.handle_callback = _handle
    monkeypatch.setattr(auth_oidc, "_service", lambda server: service)

    response = await auth_oidc.oidc_callback(
        request=_request("validstate"), code="c", state="validstate", error=None, server=_server()
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://octop.test/agents"
