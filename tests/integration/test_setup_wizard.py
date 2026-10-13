"""Integration tests for the 4-step wizard backend.

Covers: verify-password, token-protected initial-admin, finish endpoint,
and the 410 behavior on completed setups.
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
    assert r.json()["error"]["code"] == "SETUP_PASSWORD_WRONG"


async def test_verify_password_rate_limited(env: Any) -> None:
    c, _srv, _home = env
    for _ in range(5):
        await c.post("/api/setup/verify-password", json={"password": "x"})
    r = await c.post("/api/setup/verify-password", json={"password": "x"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "SETUP_RATE_LIMITED"


# ─── initial-admin token guard ──────────────────────────────────────


async def test_initial_admin_requires_wizard_token(env: Any) -> None:
    c, _srv, _home = env
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "TestPass12"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SETUP_TOKEN_INVALID"


async def test_initial_admin_succeeds_with_token(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "TestPass12"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201
    body = r.json()
    assert isinstance(body["access_token"], str)
    # The wizard password file is kept permanently, even after setup completes.
    assert (Path.home() / WIZARD_FILE_NAME).exists()


async def test_initial_admin_rejects_weak_password(env: Any) -> None:
    c, _srv, _home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "pw"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PASSWORD_TOO_WEAK"


async def test_initial_admin_respects_locale_body(env: Any) -> None:
    c, srv, _home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    r = await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "TestPass12", "locale": "en"},
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
    assert "wizard_password_path" not in body  # SEC-17: never expose the secret's path


async def test_begin_issues_token_when_password_not_required(tmp_octop_home: Path) -> None:
    write_octop_config(tmp_octop_home, require_setup_password=False)

    async with octop_client(tmp_octop_home) as (c, _srv):
        r = await c.get("/api/setup/status")
        body = r.json()
        assert body["wizard_password_required"] is False
        assert body["wizard_password_exists"] is False
        assert "wizard_password_path" not in body  # SEC-17

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
        json={"username": "admin", "password": "TestPass12"},
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
        json={"username": "admin", "password": "TestPass12"},
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


async def _fresh_token(env: Any) -> str:
    """Mint a wizard token. ``verify-password`` is gated on zero users."""
    c, _srv, _home = env
    pw = read_password(Path.home())
    return (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]


async def _admin_created(env: Any) -> tuple[Any, Any, str]:
    """Drive the wizard to mid-wizard: admin created, wizard not finished.

    Returns the still-valid wizard token, which must be minted *before*
    ``initial-admin`` because ``verify-password`` requires zero users.
    """
    c, srv, _home = env
    tok = await _fresh_token(env)
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "TestPass12"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    return c, srv, tok


async def test_resume_wizard_rejects_anonymous_caller(env: Any) -> None:
    """SEC-1: ``resume-wizard`` must never mint a token without a credential.

    Reproduces the exploit. Once the admin exists but before ``finish``, an
    unauthenticated POST used to return a valid wizard token, which then
    authorises the token-gated ``finish`` endpoint.
    """
    c, srv, tok = await _admin_created(env)

    r = await c.post("/api/setup/resume-wizard")

    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SETUP_TOKEN_INVALID"
    # Nothing usable was minted, and the real token still works.
    assert srv.wizard_tokens.validate(r.json().get("wizard_token")) is False
    assert srv.wizard_tokens.validate(tok) is True


async def test_resume_wizard_rejects_unknown_bearer(env: Any) -> None:
    """A wrong guess is rejected and yields no working token."""
    c, srv, _tok = await _admin_created(env)

    r = await c.post("/api/setup/resume-wizard", headers={"Authorization": "Bearer not-a-token"})

    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SETUP_TOKEN_INVALID"
    assert srv.wizard_tokens.validate(r.json().get("wizard_token")) is False


async def test_resume_wizard_accepts_existing_wizard_token(env: Any) -> None:
    """Re-minting is the legitimate use: the caller already holds a token."""
    c, _srv, tok = await _admin_created(env)

    r = await c.post("/api/setup/resume-wizard", headers={"Authorization": f"Bearer {tok}"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["wizard_token"], str)
    assert body["expires_in"] > 0


async def test_resume_wizard_accepts_wizard_password(env: Any) -> None:
    """The wizard password is a credential, so a restart-lost token is recoverable."""
    c, srv, _tok = await _admin_created(env)
    # Simulate the operator's situation: the in-memory token is gone (restart),
    # but the password file on disk is still there.
    srv.wizard_tokens.clear()
    pw = read_password(Path.home())

    r = await c.post("/api/setup/resume-wizard", headers={"Authorization": f"Bearer {pw}"})

    assert r.status_code == 200, r.text
    assert r.json()["wizard_token"]
    assert srv.wizard_tokens.validate(r.json()["wizard_token"]) is True


async def test_resume_wizard_accepts_admin_jwt(env: Any) -> None:
    """Mid-wizard the browser holds the JWT from /initial-admin; that must work."""
    c, _srv, _home = env
    tok = await _fresh_token(env)
    admin = (
        await c.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "TestPass12"},
            headers={"Authorization": f"Bearer {tok}"},
        )
    ).json()

    r = await c.post(
        "/api/setup/resume-wizard",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )

    assert r.status_code == 200
    assert r.json()["wizard_token"]


async def test_resume_wizard_is_rate_limited(env: Any) -> None:
    """SEC-1: anonymous hammering is bounded, not merely rejected each time."""
    c, _srv, _tok = await _admin_created(env)

    codes = [
        (
            await c.post("/api/setup/resume-wizard", headers={"Authorization": f"Bearer guess-{i}"})
        ).status_code
        for i in range(10)
    ]

    assert 429 in codes, codes
    assert codes[-1] == 429


async def test_resume_wizard_closed_after_finish(env: Any) -> None:
    """SEC-1: completion is a persisted fact, not a user row count."""
    c, _srv, tok = await _admin_created(env)

    done = await c.post(
        "/api/setup/finish", json={"provider_draft": None}, headers={"Authorization": f"Bearer {tok}"}
    )
    assert done.status_code == 200, done.text

    r = await c.post("/api/setup/resume-wizard", headers={"Authorization": f"Bearer {tok}"})

    assert r.status_code == 410
    assert r.json()["error"]["code"] == "SETUP_REQUIRED"


async def test_resume_wizard_stays_closed_after_a_user_count_drops_to_one(env: Any) -> None:
    """The specific regression the row-count heuristic caused.

    The old predicate was ``count() > 1``, so the wizard window was open while
    the count was 1 -- which is the state a normal completed install is in
    (``finish`` creates exactly one admin). An operator who later deletes any
    other account and drops back to 1 re-opened a *finished* wizard, letting
    ``resume-wizard`` mint a fresh token for ``finish`` again. The persisted
    flag does not move.
    """
    c, srv, tok = await _admin_created(env)
    done = await c.post(
        "/api/setup/finish", json={"provider_draft": None}, headers={"Authorization": f"Bearer {tok}"}
    )
    assert done.status_code == 200, done.text

    # A second account, then its removal: the count returns to 1.
    await srv.user_manager.create(username="bob", password="TestPass12", role="user")
    assert srv.user_manager.count() == 2
    bob = srv.services.user_repo.get_by_username("bob")
    assert bob is not None
    srv.services.user_repo.delete(bob.id)
    assert srv.user_manager.count() == 1

    r = await c.post("/api/setup/resume-wizard", headers={"Authorization": f"Bearer {tok}"})

    assert r.status_code == 410
    assert r.json()["error"]["code"] == "SETUP_REQUIRED"


async def test_status_does_not_expose_wizard_password_path(env: Any) -> None:
    """SEC-17: do not hand an unauthenticated caller the secret's absolute path."""
    c, _srv, _tok = await _admin_created(env)

    r = await c.get("/api/setup/status")

    assert r.status_code == 200
    body = r.json()
    assert "wizard_password_path" not in body
    # The rest of the status contract is unchanged.
    assert body["wizard_password_required"] in (True, False)
    assert body["wizard_password_exists"] in (True, False)
    assert "setup_required" in body


async def test_test_provider_accepts_admin_jwt_after_admin_created(env: Any) -> None:
    c, srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    admin = (
        await c.post(
            "/api/setup/initial-admin",
            json={"username": "admin", "password": "TestPass12"},
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
            json={"username": "admin", "password": "TestPass12"},
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


# ─── 410 guard ─────────────────────────────────────────────────────


async def test_setup_410_after_admin_exists(env: Any) -> None:
    c, _srv, home = env
    pw = read_password(Path.home())
    tok = (await c.post("/api/setup/verify-password", json={"password": pw})).json()["wizard_token"]
    await c.post(
        "/api/setup/initial-admin",
        json={"username": "admin", "password": "TestPass12"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    # Plant a stale file to verify the 410 guard does not touch it.
    (Path.home() / WIZARD_FILE_NAME).write_text("stale\n", encoding="utf-8")
    r = await c.post("/api/setup/verify-password", json={"password": "stale"})
    assert r.status_code == 410
    # The wizard password file is never deleted by the app, even on the 410 path.
    assert (Path.home() / WIZARD_FILE_NAME).exists()


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
        json={"username": "admin", "password": "TestPass12"},
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
        json={"username": "admin", "password": "TestPass12"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    r = await c.post(
        "/api/setup/finish",
        json={"provider_draft": None},
        headers={"Authorization": "Bearer faketoken"},
    )
    assert r.status_code == 401

