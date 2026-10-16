"""Real-HTTP regression: secret submit validation errors must never echo the secret.

422 responses from FastAPI/Pydantic used to reflect the request body via
``error[].input`` / ``ctx`` — the secret the user just typed came straight back
in the response. These tests mount the real chat router with the real
exception handlers and drive it over HTTP (only auth/server deps are mocked).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from octop.api.app import _install_exception_handlers
from octop.api.deps import current_user, get_server
from octop.api.routers.chat import routes as chat_routes

MARKER = "SYNTHETIC_SECRET_REVIEW_7d4af"  # synthetic; never a real credential


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    _install_exception_handlers(app)
    app.include_router(chat_routes.router, prefix="/api")
    # Validation fails before either dependency is consulted; trivial mocks.
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=1, is_admin=False)
    app.dependency_overrides[get_server] = lambda: SimpleNamespace(app_runtime=None)
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, payload: dict) -> str:
    response = client.post("/api/agents/a1/chat/secret-file/submit", json=payload)
    assert response.status_code == 422, response.text
    return response.text


def test_oversized_content_is_not_echoed(client: TestClient) -> None:
    body = MARKER * 5000  # > 64 KiB limit
    text = _post(
        client,
        {"thread_id": "t1", "pending_id": "p1", "action": "submit", "content": body},
    )
    assert MARKER not in text


def test_missing_thread_id_does_not_echo_content(client: TestClient) -> None:
    text = _post(client, {"pending_id": "p1", "action": "submit", "content": MARKER})
    assert MARKER not in text


def test_invalid_action_does_not_echo_content(client: TestClient) -> None:
    text = _post(
        client,
        {"thread_id": "t1", "pending_id": "p1", "action": "bogus", "content": MARKER},
    )
    assert MARKER not in text


def test_wrong_types_do_not_echo_content(client: TestClient) -> None:
    text = _post(
        client,
        {"thread_id": 123, "pending_id": None, "action": "submit", "content": MARKER},
    )
    assert MARKER not in text


def test_submit_documents_sse_response(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/agents/{agent_id}/chat/secret-file/submit"]["post"]
    assert operation["responses"]["200"]["content"] == {
        "text/event-stream": {"schema": {"type": "string"}},
    }
