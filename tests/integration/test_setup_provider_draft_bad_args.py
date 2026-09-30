"""``POST /api/setup/finish`` must not label its own input rejection as a server fault.

Covers: a provider draft whose ``api_key`` / ``base_url`` / ``models`` are empty is
rejected with a client-error code, while a genuine bootstrap failure still reports
INTERNAL_ERROR / 500.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from octop.infra.setup.password_file import read_password

MODEL = {"id": "MiniMax-M2.7", "name": "MiniMax", "enabled": True, "input": ["text"]}
GOOD_DRAFT: dict[str, Any] = {
    "name": "HAI",
    "type": "openai",
    "api_key": "sk-test",
    "base_url": "https://api.example.com/v1",
    "models": [MODEL],
}


@pytest.fixture
async def env(patched_app_client):
    yield patched_app_client


async def _wizard_token(c: Any) -> str:
    pw = read_password(Path.home())
    assert pw is not None
    r = await c.post("/api/setup/verify-password", json={"password": pw})
    assert r.status_code == 200
    return str(r.json()["wizard_token"])


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"api_key": ""}, id="blank-api-key"),
        pytest.param({"api_key": "   "}, id="whitespace-api-key"),
        pytest.param({"base_url": ""}, id="blank-base-url"),
        pytest.param({"base_url": None}, id="null-base-url"),
        pytest.param({"models": []}, id="no-models"),
    ],
)
async def test_finish_rejects_draft_as_client_error(env: Any, override: dict[str, Any]) -> None:
    c, srv, _home = env
    tok = await _wizard_token(c)
    draft = {**GOOD_DRAFT, **override}
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": draft},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 400, r.text
    # INTERNAL_ERROR is pinned to 500 (infra/errors.py) and api/app.py only logs
    # at status >= 500, so a 400/INTERNAL_ERROR envelope tells the client nothing
    # and leaves no trace in ~/.octop/logs.
    assert r.json()["error"]["code"] == "SLASH_BAD_ARGS"
    assert srv.services.provider_repo.list_all() == []


async def test_finish_still_saves_a_complete_draft(env: Any) -> None:
    c, srv, _home = env
    tok = await _wizard_token(c)
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": GOOD_DRAFT},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert len(srv.services.provider_repo.list_all()) == 1


async def test_finish_keeps_internal_error_for_a_failed_bootstrap(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, srv, _home = env
    tok = await _wizard_token(c)

    def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("provider storage exploded")

    monkeypatch.setattr(srv.services.provider_repo, "create", _boom)
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": GOOD_DRAFT},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 500, r.text
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
