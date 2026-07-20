"""Integration tests for the 4-step wizard backend.

Covers: verify-password, token-protected initial-admin, finish endpoint,
and the 410-with-cleanup behavior on completed setups.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from octop.infra.setup.password_file import WIZARD_FILE_NAME, read_password
from tests.support.app import octop_client, write_octop_config


@pytest.fixture
async def env(patched_app_client):
    yield patched_app_client


# ─── verify-password ────────────────────────────────────────────────


async def test_verify_password_returns_token_on_match(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    assert pw is not None
    r = await c.post("/api/setup/verify-password", json={"password": pw})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["wizard_token"], str)
    assert body["expires_in"] > 0


async def test_verify_password_rejects_mismatch(env: Any) -> None:
    c, _srv, _home = env
    r = await c.post("/api/setup/verify-password", json={"password": "wrong"})
    assert r.status_code == 401


async def test_verify_password_rate_limited(env: Any) -> None:
    c, _srv, _home = env
    for _ in range(5):
        await c.post("/api/setup/verify-password", json={"password": "x"})
    r = await c.post("/api/setup/verify-password", json={"password": "x"})
    assert r.status_code == 429


# ─── initial-admin token guard ──────────────────────────────────────


async def test_initial_admin_requires_wizard_token(env: Any) -> None:
    c, _srv, _home = env
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
    )
    assert r.status_code == 401


async def test_initial_admin_succeeds_with_token(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["access_token"], str)
    assert not (Path.home() / WIZARD_FILE_NAME).exists()


async def test_initial_admin_respects_locale_body(env: Any) -> None:
    c, srv, _home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw", "locale": "en"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    assert r.json()["locale"] == "en"
    user = srv.user_manager.get("admin")
    assert user is not None
    assert user.locale == "en"


# ─── /setup/status ─────────────────────────────────────────────────


async def test_status_reports_wizard_password_exists(env: Any) -> None:
    c, _srv, home = env
    r = await c.get("/api/setup/status")
    body = r.json()
    assert body["setup_required"] is True
    assert body["wizard_password_required"] is True
    assert body["wizard_password_exists"] is True
    assert body["wizard_password_path"] == str(Path.home() / WIZARD_FILE_NAME)


async def test_begin_issues_token_when_password_not_required(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, require_setup_password=False)

    async with octop_client(tmp_octop_home) as (c, _srv):
        r = await c.get("/api/setup/status")
        body = r.json()
        assert body["wizard_password_required"] is False
        assert body["wizard_password_exists"] is False
        assert body["wizard_password_path"] is None

        r = await c.post("/api/setup/begin")
        assert r.status_code == 200
        assert r.json()["wizard_token"]


async def test_validate_token_rejects_missing_header(env: Any) -> None:
    c, _srv, _home = env
    r = await c.get("/api/setup/validate-token")
    assert r.status_code == 200
    assert r.json()["valid"] is False


async def test_validate_token_accepts_fresh_token(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.get(
        "/api/setup/validate-token",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is True


async def test_validate_token_rejects_stale_token(env: Any) -> None:
    c, _srv, _home = env
    r = await c.get(
        "/api/setup/validate-token",
        headers={"Authorization": "Bearer stale-token"},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is False


# ─── /setup/finish ─────────────────────────────────────────────────


async def test_finish_requires_wizard_token(env: Any) -> None:
    c, _srv, _home = env
    r = await c.post("/api/setup/finish", json={"provider_draft": None})
    assert r.status_code == 401


async def test_finish_returns_ok_with_valid_token(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_finish_works_after_admin_created(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_validate_token_still_valid_after_admin_created(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.get(
        "/api/setup/validate-token",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is True


async def test_test_provider_requires_wizard_token(env: Any) -> None:
    c, _srv, _home = env
    r = await c.post(
        "/api/setup/test-provider",
        json={
            "name": "OpenAI",
            "type": "openai",
            "api_key": "sk-test",
            "model_id": "gpt-4o-mini",
        },
    )
    assert r.status_code == 401


async def test_test_provider_returns_error_for_bad_key(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/test-provider",
        json={
            "name": "OpenAI",
            "type": "openai",
            "api_key": "sk-invalid",
            "model_id": "gpt-4o-mini",
        },
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_resume_wizard_after_admin_created(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.post("/api/setup/resume-wizard")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["wizard_token"], str)
    assert body["expires_in"] > 0


async def test_test_provider_accepts_admin_jwt_after_admin_created(env: Any) -> None:
    c, srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    admin = (
        await c.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "pw"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    ).json()
    assert "access_token" in admin
    srv.wizard_tokens.clear()
    r = await c.post(
        "/api/setup/test-provider",
        json={
            "name": "OpenAI",
            "type": "openai",
            "api_key": "sk-invalid",
            "model_id": "gpt-4o-mini",
        },
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


async def test_finish_saves_provider_with_admin_jwt(env: Any) -> None:
    c, srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    admin = (
        await c.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "pw"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    ).json()
    srv.wizard_tokens.clear()
    r = await c.post(
        "/api/setup/finish",
        json={
            "provider_draft": {
                "name": "HAI",
                "type": "openai",
                "api_key": "sk-test",
                "base_url": "https://api.example.com/v1",
                "models": [
                    {
                        "id": "MiniMax-M2.7",
                        "name": "MiniMax",
                        "enabled": True,
                        "input": ["text"],
                    }
                ],
            }
        },
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert r.status_code == 200, r.text
    providers = srv.services.provider_repo.list_all()
    assert len(providers) == 1
    assert providers[0].api_key == "sk-test"
    provider_name, model_id = srv.services.settings_repo.get_active_model()
    assert provider_name == "HAI"
    assert model_id == "MiniMax-M2.7"
    registry = srv.app_runtime.agent_registry
    assert registry._harness_manager is not None
    assert registry._harness_manager.shared_factory is not None
    main = srv.services.repos.agent_repo.get("main")
    assert main is not None
    # The default agent boots asynchronously after finish(); wait for it to settle.
    last_state = main.last_state
    for _ in range(50):
        await asyncio.sleep(0.1)
        if (
            current := srv.services.repos.agent_repo.get("main")
        ) and current.last_state == "running":
            last_state = current.last_state
            break
        if current is not None:
            last_state = current.last_state
    assert last_state == "running"


# ─── 410 cleanup ───────────────────────────────────────────────────


async def test_setup_410_after_admin_exists(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    # Plant a stale file to verify the cleanup branch.
    (Path.home() / WIZARD_FILE_NAME).write_text("stale\n", encoding="utf-8")
    r = await c.post("/api/setup/verify-password", json={"password": "stale"})
    assert r.status_code == 410
    assert not (Path.home() / WIZARD_FILE_NAME).exists()


# ─── lockdown middleware ───────────────────────────────────────────


async def test_lockdown_blocks_non_setup_endpoints_when_no_users(env: Any) -> None:
    c, _srv, _home = env
    r = await c.get("/api/agents")
    assert r.status_code == 503
    body = r.json()
    assert body.get("setup_required") is True


async def test_lockdown_allows_setup_endpoints(env: Any) -> None:
    c, _srv, _home = env
    r = await c.get("/api/setup/status")
    assert r.status_code == 200


async def test_lockdown_allows_health_path(env: Any) -> None:
    c, _srv, _home = env
    r = await c.get("/api/health")
    assert r.status_code == 200


async def test_lockdown_lifts_after_admin_created(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.get("/api/agents")
    # No JWT ⇒ 401 (auth, not lockdown).
    assert r.status_code == 401


async def test_finish_rejects_invalid_token_after_admin_exists(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": "Bearer faketoken"},
    )
    assert r.status_code == 401
