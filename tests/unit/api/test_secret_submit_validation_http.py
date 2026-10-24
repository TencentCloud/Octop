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
from pydantic import BaseModel, Field

from octop.api.app import _install_exception_handlers
from octop.api.deps import current_user, get_server
from octop.api.routers.chat import routes as chat_routes

MARKER = "SYNTHETIC_SECRET_REVIEW_7d4af"  # synthetic; never a real credential


class _LookalikeBody(BaseModel):
    """Body for a route whose URL ends like secret submit but is not that route."""

    content: str = Field(max_length=8)


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
    body = response.json()
    assert isinstance(body, dict)
    assert isinstance(body.get("detail"), list)
    for error in body["detail"]:
        assert "input" not in error
        assert "ctx" not in error
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


def test_lookalike_path_keeps_validation_input(client: TestClient) -> None:
    """A URL that merely ends like the secret route still echoes ``input``."""

    @client.app.post("/api/not-agents/chat/secret-file/submit")
    def _probe(body: _LookalikeBody) -> dict[str, str]:
        return {"ok": body.content}

    response = client.post(
        "/api/not-agents/chat/secret-file/submit",
        json={"content": MARKER},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body.get("detail"), list)
    assert any(error.get("input") == MARKER for error in body["detail"])


def test_submit_documents_sse_response(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/agents/{agent_id}/chat/secret-file/submit"]["post"]
    assert operation["responses"]["200"]["content"] == {
        "text/event-stream": {"schema": {"type": "string"}},
    }
