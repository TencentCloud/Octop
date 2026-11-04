"""Secure-form submit/GET endpoints and vault router: lifecycle, lease, and value hygiene."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.testclient import TestClient

import octop.api.routers.chat.routes as chat_routes
import octop.api.routers.vault as vault_routes
from octop.api.routers.chat.models import SecureFormSubmitBody
from octop.config import OctopConfig
from octop.infra.agents.secret_input.service import AgentSecretService
from octop.infra.agents.secure_form.envelope import open_vault_fields
from octop.infra.agents.secure_form.submit import resolve_secure_form_submission
from octop.infra.agents.secure_form.vault_service import VaultService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator
from octop.infra.utils.paths import PathLayout

_TOOL = "request_secure_form"
_MARK_HOST = "MARK-host-value-917"
_MARK_PASS = "MARK-pass-value-431"
_MARK_CVV = "773"  # cvv synthetic marker: never in vault/logs/frames
_MARK_USER = "MARK-user-value-256"

ENV_FORM: dict[str, Any] = {
    "fields": [
        {"id": "host", "label": "Host", "type": "text", "max_length": 40},
        {"id": "password", "label": "Password", "type": "password"},
    ],
    "prompt": "Deploy credentials",
    "title": "Deploy form",
    "routing": {
        "kind": "env",
        "slots": {"host": "DEPLOY_HOST", "password": "DEPLOY_PASS"},
    },
}

VAULT_LOGIN_FORM: dict[str, Any] = {
    "fields": [
        {"id": "user", "label": "Username", "type": "text"},
        {"id": "pass", "label": "Password", "type": "password"},
    ],
    "prompt": "Save your site login",
    "routing": {
        "kind": "vault",
        "vault_meta": {"item_type": "login", "title": "GitHub", "origin": "https://github.com"},
    },
}

# env-routed card form with an optional save-to-vault checkbox: the cvv field
# is legal for env slots but must never survive the card envelope allow-list.
CARD_ENV_FORM: dict[str, Any] = {
    "fields": [
        {"id": "card_number", "label": "Card number", "type": "card_number"},
        {"id": "card_exp", "label": "Expiry", "type": "card_exp"},
        {"id": "card_cvv", "label": "CVV", "type": "card_cvv"},
    ],
    "prompt": "Card details",
    "routing": {
        "kind": "env",
        "slots": {
            "card_number": "CARD_NUMBER",
            "card_exp": "CARD_EXP",
            "card_cvv": "CARD_CVV",
        },
        "vault_meta": {"item_type": "card", "title": "My card"},
    },
}


class Env:
    def __init__(self, tmp_path: Path) -> None:
        paths = PathLayout(tmp_path / ".octop")
        paths.ensure_root()
        self.db = SqlitePool(paths.db)
        run_migrations(self.db)
        self.shared: SharedServices = build_shared_services(
            db=self.db, paths=paths, config=OctopConfig()
        )
        self.user_repo = self.shared.repos.user_repo
        self.user_repo.create(username="owner", role="user")
        self.user_repo.create(username="intruder", role="user")
        owner = self.user_repo.get_by_username("owner")
        intruder = self.user_repo.get_by_username("intruder")
        assert owner is not None and intruder is not None
        self.owner = owner
        self.intruder = intruder
        self.shared.repos.agent_repo.create(agent_id="agent-1", user_id=owner.id, name="Agent One")
        self.agent_secrets = AgentSecretService(
            repo=self.shared.repos.agent_secret_repo, secret_repo=self.shared.repos.secret_repo
        )
        self.vault = VaultService(
            repo=self.shared.repos.vault_items_repo, secret_repo=self.shared.repos.secret_repo
        )
        self.hitl = HitlChannelCoordinator()
        self.resume_calls: list[list[dict[str, Any]]] = []

        async def _resume_chunks(**kwargs: Any):
            self.resume_calls.append(kwargs["decisions"])
            yield {"type": "token", "content": "stored, continuing"}
            yield {"type": "done"}

        processor = MagicMock()
        processor.hitl_coordinator = self.hitl
        processor.iter_hitl_resume_chunks = _resume_chunks
        self.reload = AsyncMock(return_value=True)
        registry = SimpleNamespace(agent_secrets=self.agent_secrets, reload=self.reload)
        self.server = SimpleNamespace(
            app_runtime=SimpleNamespace(
                gateway=SimpleNamespace(
                    processor=processor,
                    thread_registry=SimpleNamespace(get_thread=lambda _t: None),
                ),
                agent_registry=registry,
            ),
            services=self.shared,
        )

    def register_form(
        self, args: dict[str, Any], *, user_id: int | None = None, agent_id: str = "agent-1"
    ):
        uid = user_id if user_id is not None else self.owner.id
        return self.hitl.store.register(
            thread_id="thr-1",
            agent_id=agent_id,
            user_id=uid,
            session_key=f"{agent_id}:dashboard:{uid}:dm",
            channel_type="dashboard",
            action_requests=[{"name": _TOOL, "args": args}],
            review_configs=None,
        )

    def body(
        self,
        record,
        action: str = "submit",
        values: dict[str, str] | None = None,
        **extra: Any,
    ) -> SecureFormSubmitBody:
        return SecureFormSubmitBody(
            thread_id=record.thread_id,
            pending_id=record.pending_id,
            action=action,  # type: ignore[arg-type]
            values=values or {},
            **extra,
        )

    def open_vault(self, vault_item_id: str, *, item_type: str = "login") -> dict[str, str]:
        row = self.shared.repos.vault_items_repo.get(
            vault_item_id, user_id=self.owner.id, include_blob=True
        )
        assert row is not None and row.fields_blob is not None
        return open_vault_fields(
            self.shared.repos.secret_repo,
            row_user_id=self.owner.id,
            vault_item_id=vault_item_id,
            item_type=item_type,
            blob=row.fields_blob,
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


@pytest.fixture(autouse=True)
def _owner_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )


@pytest.fixture(autouse=True)
def _quiet_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)


def _request() -> Any:
    return SimpleNamespace(
        headers={"accept-language": "en"},
        url=SimpleNamespace(path="/api/agents/agent-1/chat/secure-form/submit"),
        is_disconnected=AsyncMock(return_value=False),
    )


async def _drain(response: Any) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    async for raw in response.body_iterator:  # type: ignore[union-attr]
        for block in str(raw).split("\n\n"):
            line = next((ln[6:] for ln in block.split("\n") if ln.startswith("data: ")), None)
            if line:
                chunks.append(json.loads(line))
    return chunks


_ALL_MARKERS = (_MARK_HOST, _MARK_PASS, _MARK_CVV, _MARK_USER)


def _assert_markers_absent(env: Env, *texts: str, caplog: pytest.LogCaptureFixture) -> None:
    """Per-field markers never reach frames, resumed decisions, or logs."""
    decisions = json.dumps([d for calls in env.resume_calls for d in calls])
    for marker in _ALL_MARKERS:
        for text in texts:
            assert marker not in text
        assert marker not in decisions
        assert marker not in caplog.text


# ---------------------------------------------------------------- happy paths


@pytest.mark.asyncio
async def test_env_submit_writes_all_slots_and_resumes_injected(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    record = env.register_form(ENV_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")

    response = await chat_routes.submit_secure_form(
        "agent-1",
        env.body(record, values={"host": _MARK_HOST, "password": _MARK_PASS}),
        _request(),
        user=user,
        server=env.server,
    )
    chunks = await _drain(response)

    assert chunks[-1] == {"type": "done"}
    _assert_markers_absent(env, json.dumps(chunks), caplog=caplog)
    stored = env.agent_secrets.decrypt_env("agent-1")
    assert stored == {"DEPLOY_HOST": _MARK_HOST, "DEPLOY_PASS": _MARK_PASS}
    env.reload.assert_awaited_once_with("agent-1")
    message = env.resume_calls[-1][0]["message"]
    assert "DEPLOY_HOST" in message and "DEPLOY_PASS" in message
    assert "already injected" in message
    assert env.hitl.store.get(record.pending_id).status == "filled"


@pytest.mark.asyncio
async def test_env_submit_rebuild_failure_degrades_to_next_turn(env: Env) -> None:
    record = env.register_form(ENV_FORM)
    env.reload.return_value = False
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")

    response = await chat_routes.submit_secure_form(
        "agent-1",
        env.body(record, values={"host": _MARK_HOST, "password": _MARK_PASS}),
        _request(),
        user=user,
        server=env.server,
    )
    await _drain(response)

    message = env.resume_calls[-1][0]["message"]
    assert "NEXT turn" in message
    assert "already injected" not in message


@pytest.mark.asyncio
async def test_vault_submit_creates_then_rotates_reusing_item_id(env: Env) -> None:
    record = env.register_form(VAULT_LOGIN_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    values = {"user": _MARK_USER, "pass": _MARK_PASS}

    response = await chat_routes.submit_secure_form(
        "agent-1", env.body(record, values=values), _request(), user=user, server=env.server
    )
    await _drain(response)

    item = env.shared.repos.vault_items_repo.find_by_title(
        user_id=env.owner.id, item_type="login", title="GitHub"
    )
    assert item is not None
    assert env.open_vault(item.vault_item_id) == {"text": _MARK_USER, "password": _MARK_PASS}
    assert item.origin == "https://github.com"
    message = env.resume_calls[-1][0]["message"]
    assert item.vault_item_id in message
    assert _MARK_USER not in message and _MARK_PASS not in message
    env.reload.assert_not_awaited()  # vault-only: no harness rebuild

    # Second submit on a fresh form collides on the title (pre-claim 422) ...
    second = env.register_form(VAULT_LOGIN_FORM)
    with pytest.raises(OctopError) as refused:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(second, values={"user": "x", "pass": "y"}),
            _request(),
            user=user,
            server=env.server,
        )
    assert refused.value.code is ErrorCode.VAULT_REPLACE_REQUIRED
    assert refused.value.details["existing_vault_item_id"] == item.vault_item_id
    assert env.hitl.store.get(second.pending_id).status == "pending"

    # ... and rotate reuses the existing row identity.
    third = env.register_form(VAULT_LOGIN_FORM)
    response = await chat_routes.submit_secure_form(
        "agent-1",
        env.body(third, values={"user": "alice", "pass": "n3w"}, replace_confirmed=True),
        _request(),
        user=user,
        server=env.server,
    )
    await _drain(response)
    rotated = env.shared.repos.vault_items_repo.find_by_title(
        user_id=env.owner.id, item_type="login", title="GitHub"
    )
    assert rotated is not None
    assert rotated.vault_item_id == item.vault_item_id
    assert env.open_vault(rotated.vault_item_id) == {"text": "alice", "password": "n3w"}
    actions = [row.action for row in env.shared.repos.audit_repo.query(limit=10)]
    assert "vault.create" in actions and "vault.rotate" in actions


@pytest.mark.asyncio
async def test_save_to_vault_on_env_form_excludes_cvv(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    record = env.register_form(CARD_ENV_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    values = {
        "card_number": "4242 4242 4242 4242",
        "card_exp": "12/29",
        "card_cvv": _MARK_CVV,
    }

    response = await chat_routes.submit_secure_form(
        "agent-1",
        env.body(record, values=values, save_to_vault=True),
        _request(),
        user=user,
        server=env.server,
    )
    chunks = await _drain(response)

    # env slots got everything (byte-exact after the card_number space strip)...
    stored = env.agent_secrets.decrypt_env("agent-1")
    assert stored["CARD_NUMBER"] == "4242424242424242"
    assert stored["CARD_EXP"] == "12/29"
    assert stored["CARD_CVV"] == _MARK_CVV
    # ...but the vault envelope holds exactly the card allow-list: no cvv.
    item = env.shared.repos.vault_items_repo.find_by_title(
        user_id=env.owner.id, item_type="card", title="My card"
    )
    assert item is not None
    assert env.open_vault(item.vault_item_id, item_type="card") == {
        "card_number": "4242424242424242",
        "card_exp": "12/29",
    }
    _assert_markers_absent(env, json.dumps(chunks), caplog=caplog)


@pytest.mark.asyncio
async def test_cancel_skips_writes_and_marks_cancelled(env: Env) -> None:
    record = env.register_form(ENV_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")

    response = await chat_routes.submit_secure_form(
        "agent-1", env.body(record, action="cancel"), _request(), user=user, server=env.server
    )
    chunks = await _drain(response)

    assert chunks[-1] == {"type": "done"}
    assert env.agent_secrets.list_slots("agent-1") == []
    assert env.vault.list_items(env.owner.id) == []
    env.reload.assert_not_awaited()
    assert env.hitl.store.get(record.pending_id).status == "cancelled"
    assert "cancelled" in env.resume_calls[-1][0]["message"]


@pytest.mark.asyncio
async def test_shared_agent_is_refused(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    record = env.register_form(ENV_FORM)
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=1),
    )
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(record, values={"host": _MARK_HOST, "password": _MARK_PASS}),
            _request(),
            user=user,
            server=env.server,
        )
    assert err.value.code is ErrorCode.FORBIDDEN


# ---------------------------------------------------------------- pre-claim 422s


def _env_values() -> dict[str, str]:
    return {"host": _MARK_HOST, "password": _MARK_PASS}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("form", "values", "code", "save_to_vault"),
    [
        (
            ENV_FORM,
            {"host": _MARK_HOST, "password": _MARK_PASS, "extra": "x"},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            ENV_FORM,
            {"host": "  ", "password": _MARK_PASS},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            ENV_FORM,
            {"host": "h" * 41, "password": _MARK_PASS},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            {
                "fields": [{"id": "code", "label": "OTP", "type": "otp"}],
                "prompt": "p",
                "routing": {"kind": "env", "slots": {"code": "OTP_CODE"}},
            },
            {"code": "12"},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            CARD_ENV_FORM,
            {"card_number": "4242", "card_exp": "12/29", "card_cvv": _MARK_CVV},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            CARD_ENV_FORM,
            {"card_number": "4242424242424242", "card_exp": "13/29", "card_cvv": _MARK_CVV},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        (
            CARD_ENV_FORM,
            {"card_number": "4242424242424242", "card_exp": "12/29", "card_cvv": "12"},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            False,
        ),
        # save_to_vault without registered vault_meta
        (
            {
                "fields": [{"id": "host", "label": "Host", "type": "text"}],
                "prompt": "p",
                "routing": {"kind": "env", "slots": {"host": "DEPLOY_HOST"}},
            },
            {"host": _MARK_HOST},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            True,
        ),
        # all-filtered save: only a cvv field for a login item_type
        (
            {
                "fields": [{"id": "cvv", "label": "CVV", "type": "card_cvv"}],
                "prompt": "p",
                "routing": {
                    "kind": "env",
                    "slots": {"cvv": "CARD_CVV"},
                    "vault_meta": {"item_type": "login", "title": "CVV only"},
                },
            },
            {"cvv": _MARK_CVV},
            ErrorCode.SECURE_FORM_FIELD_INVALID,
            True,
        ),
    ],
)
async def test_pre_claim_validation_refusals_keep_lease(
    env: Env,
    form: dict[str, Any],
    values: dict[str, str],
    code: ErrorCode,
    save_to_vault: bool,
) -> None:
    record = env.register_form(form)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(record, values=values, save_to_vault=save_to_vault),
            _request(),
            user=user,
            server=env.server,
        )
    assert err.value.code is code
    pending = env.hitl.store.get(record.pending_id)
    assert pending is not None and pending.status == "pending"
    assert pending.reopen_budget == 5
    assert err.value.status == 422


@pytest.mark.asyncio
async def test_slot_capacity_drift_is_refused(env: Env) -> None:
    for i in range(31):
        env.agent_secrets.store_slot(
            agent_id="agent-1", user_id=env.owner.id, slot_name=f"SLOT_{i:02d}", value="x"
        )
    record = env.register_form(ENV_FORM)  # adds DEPLOY_HOST + DEPLOY_PASS -> 33 > 32
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(record, values=_env_values()),
            _request(),
            user=user,
            server=env.server,
        )
    assert err.value.code is ErrorCode.SECURE_FORM_SLOT_INVALID
    assert err.value.status == 422
    assert env.hitl.store.get(record.pending_id).status == "pending"


@pytest.mark.asyncio
async def test_vault_cap_is_refused_pre_claim(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    import octop.infra.agents.secure_form.vault_service as vault_service_module

    env.vault.store_item(
        env.owner.id, "login", "Existing", None, {"text": "a"}, replace_confirmed=False
    )
    monkeypatch.setattr(vault_service_module, "VAULT_ITEMS_MAX_PER_USER", 1)
    record = env.register_form(VAULT_LOGIN_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(record, values={"user": _MARK_USER, "pass": _MARK_PASS}),
            _request(),
            user=user,
            server=env.server,
        )
    assert err.value.code is ErrorCode.VAULT_CAP_EXCEEDED
    assert env.hitl.store.get(record.pending_id).status == "pending"


# ---------------------------------------------------------------- lease semantics


def _resolver_kwargs(env: Env, record, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "store": env.hitl.store,
        "agent_secrets": env.agent_secrets,
        "vault": env.vault,
        "agent_id": "agent-1",
        "user_id": env.owner.id,
        "thread_id": "thr-1",
        "pending_id": record.pending_id,
        "rebuild": env.reload,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.asyncio
async def test_hard_write_failure_spends_reopen_credit_and_persists_nothing(env: Env) -> None:
    record = env.register_form(CARD_ENV_FORM)
    values = {"card_number": "4242424242424242", "card_exp": "12/29", "card_cvv": _MARK_CVV}

    def _boom(conn: Any, action: str, target: str) -> None:
        raise RuntimeError("forced audit failure")

    with pytest.raises(OctopError) as err:
        await resolve_secure_form_submission(
            **_resolver_kwargs(
                env,
                record,
                action="submit",
                values=values,
                save_to_vault=True,
                audit=_boom,
            )
        )
    assert err.value.code is ErrorCode.SECURE_FORM_WRITE_FAILED
    pending = env.hitl.store.get(record.pending_id)
    assert pending is not None
    assert pending.status == "pending"
    assert pending.reopen_budget == 4
    # Nothing persisted: slots, vault rows, and audit rows all rolled back.
    assert env.agent_secrets.list_slots("agent-1") == []
    assert env.vault.list_items(env.owner.id) == []
    assert env.shared.repos.audit_repo.query(limit=10) == []


@pytest.mark.asyncio
async def test_recoverable_drift_releases_lease_without_credit(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = env.register_form(VAULT_LOGIN_FORM)

    def _drift(self: VaultService, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise OctopError(ErrorCode.VAULT_REPLACE_REQUIRED, "drift inside the unit")

    monkeypatch.setattr(VaultService, "store_item", _drift)
    with pytest.raises(OctopError) as err:
        await resolve_secure_form_submission(
            **_resolver_kwargs(env, record, action="submit", values={"user": "a", "pass": "b"})
        )
    assert err.value.code is ErrorCode.VAULT_REPLACE_REQUIRED
    pending = env.hitl.store.get(record.pending_id)
    assert pending is not None
    assert pending.status == "pending"
    assert pending.reopen_budget == 5


@pytest.mark.asyncio
async def test_lost_response_replays_terminal_metadata_without_second_write(env: Env) -> None:
    record = env.register_form(ENV_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    values = {"host": _MARK_HOST, "password": _MARK_PASS}

    first = await chat_routes.submit_secure_form(
        "agent-1", env.body(record, values=values), _request(), user=user, server=env.server
    )
    await _drain(first)

    replay = await chat_routes.submit_secure_form(
        "agent-1", env.body(record, values=values), _request(), user=user, server=env.server
    )
    chunks = await _drain(replay)

    assert chunks[0]["type"] == "secure_form_result"
    assert chunks[0]["result"]["slot_names"] == ["DEPLOY_HOST", "DEPLOY_PASS"]
    assert chunks[0]["result"]["vault_item_id"] is None
    assert chunks[0]["result"]["injected"] is True
    assert chunks[-1] == {"type": "done", "secure_form_replay": True}
    # No second write and no second resume: one rebuild, one resume call.
    env.reload.assert_awaited_once_with("agent-1")
    assert len(env.resume_calls) == 1
    assert len(env.agent_secrets.list_slots("agent-1")) == 2


@pytest.mark.asyncio
async def test_cancelled_elsewhere_is_terminal_409(env: Env) -> None:
    record = env.register_form(ENV_FORM)
    env.hitl.store.claim_secret_input(record.pending_id)
    env.hitl.store.mark_resolved(record.pending_id, "cancelled")
    with pytest.raises(OctopError) as err:
        await resolve_secure_form_submission(
            **_resolver_kwargs(env, record, action="submit", values=_env_values())
        )
    assert err.value.code is ErrorCode.SECURE_FORM_ALREADY_HANDLED
    assert err.value.status == 409


@pytest.mark.asyncio
async def test_expired_pending_is_terminal_on_submit(env: Env) -> None:
    first = env.register_form(ENV_FORM)
    # Same session slot with DIFFERENT args: evicts the first card (register()
    # dedupes only equivalent re-projections of the same pause).
    env.register_form({**ENV_FORM, "title": "Newer form"})
    with pytest.raises(OctopError) as err:
        await resolve_secure_form_submission(
            **_resolver_kwargs(env, first, action="submit", values=_env_values())
        )
    assert err.value.code is ErrorCode.SECURE_FORM_ALREADY_HANDLED
    assert err.value.status == 409


@pytest.mark.asyncio
async def test_reopen_limit_goes_terminal(env: Env) -> None:
    record = env.register_form(VAULT_LOGIN_FORM)
    values = {"user": _MARK_USER, "pass": _MARK_PASS}

    def _boom(conn: Any, action: str, target: str) -> None:
        raise RuntimeError("forced failure")

    for _ in range(5):
        with pytest.raises(OctopError) as err:
            await resolve_secure_form_submission(
                **_resolver_kwargs(env, record, action="submit", values=values, audit=_boom)
            )
        assert err.value.code is ErrorCode.SECURE_FORM_WRITE_FAILED
        pending = env.hitl.store.get(record.pending_id)
        assert pending is not None and pending.status == "pending"

    with pytest.raises(OctopError) as exhausted:
        await resolve_secure_form_submission(
            **_resolver_kwargs(env, record, action="submit", values=values, audit=_boom)
        )
    assert exhausted.value.code is ErrorCode.SECURE_FORM_WRITE_FAILED
    assert env.hitl.store.get(record.pending_id).status == "failed"

    with pytest.raises(OctopError) as terminal:
        await resolve_secure_form_submission(
            **_resolver_kwargs(env, record, action="submit", values=values)
        )
    assert terminal.value.code is ErrorCode.SECURE_FORM_ALREADY_HANDLED
    # Every failed attempt rolled the whole unit back.
    assert env.vault.list_items(env.owner.id) == []


@pytest.mark.asyncio
async def test_scope_and_shape_guards(env: Env) -> None:
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    # Unknown pending id -> plain 404.
    with pytest.raises(OctopError) as missing:
        await chat_routes.submit_secure_form(
            "agent-1",
            SecureFormSubmitBody(thread_id="thr-1", pending_id="beef", action="submit"),
            _request(),
            user=user,
            server=env.server,
        )
    assert missing.value.code is ErrorCode.NOT_FOUND

    # Pending owned by another user -> 404, not a leak.
    other_record = env.register_form(ENV_FORM, user_id=env.intruder.id)
    with pytest.raises(OctopError) as foreign:
        await chat_routes.submit_secure_form(
            "agent-1",
            SecureFormSubmitBody(
                thread_id="thr-1", pending_id=other_record.pending_id, action="submit"
            ),
            _request(),
            user=user,
            server=env.server,
        )
    assert foreign.value.code is ErrorCode.NOT_FOUND

    # Non-secure-form pending -> request invalid.
    plain = env.hitl.store.register(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=env.owner.id,
        session_key=f"agent-1:dashboard:{env.owner.id}:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "ls"}}],
        review_configs=None,
    )
    with pytest.raises(OctopError) as not_form:
        await chat_routes.submit_secure_form(
            "agent-1",
            SecureFormSubmitBody(thread_id="thr-1", pending_id=plain.pending_id, action="cancel"),
            _request(),
            user=user,
            server=env.server,
        )
    assert not_form.value.code is ErrorCode.SECURE_FORM_REQUEST_INVALID

    # Mixed pause: submit refused, cancel allowed.
    mixed = env.hitl.store.register(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=env.owner.id,
        session_key=f"agent-1:dashboard:{env.owner.id}:dm",
        channel_type="dashboard",
        action_requests=[
            {"name": _TOOL, "args": ENV_FORM},
            {"name": "execute", "args": {"command": "ls"}},
        ],
        review_configs=None,
    )
    with pytest.raises(OctopError) as mixed_refusal:
        await chat_routes.submit_secure_form(
            "agent-1",
            env.body(mixed, values=_env_values()),
            _request(),
            user=user,
            server=env.server,
        )
    assert mixed_refusal.value.code is ErrorCode.SECURE_FORM_REQUEST_INVALID
    response = await chat_routes.submit_secure_form(
        "agent-1", env.body(mixed, action="cancel"), _request(), user=user, server=env.server
    )
    chunks = await _drain(response)
    assert chunks[-1] == {"type": "done"}
    assert len(env.resume_calls[-1]) == 2


# ---------------------------------------------------------------- GET schema


@pytest.mark.asyncio
async def test_get_returns_structured_schema_with_rederived_facts(env: Env) -> None:
    record = env.register_form(CARD_ENV_FORM)
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")

    view = await chat_routes.get_secure_form(
        "agent-1", record.pending_id, user=user, server=env.server
    )
    assert view.status == "pending"
    assert [f.id for f in view.fields] == ["card_number", "card_exp", "card_cvv"]
    assert view.routing.kind == "env"
    assert view.routing.slots == {
        "card_number": "CARD_NUMBER",
        "card_exp": "CARD_EXP",
        "card_cvv": "CARD_CVV",
    }
    assert view.routing.vault_meta is not None and view.routing.vault_meta.item_type == "card"
    assert view.existing_vault_item_id is None
    assert view.existing_slot_names == []
    assert view.vault_storable_field_ids == ["card_number", "card_exp"]

    # Drift between registration and GET becomes visible: a colliding item and
    # one existing slot appear in the re-derived facts.
    env.agent_secrets.store_slot(
        agent_id="agent-1", user_id=env.owner.id, slot_name="CARD_EXP", value="00/00"
    )
    created = env.vault.store_item(
        env.owner.id, "card", "My card", None, {"card_number": "1"}, replace_confirmed=False
    )
    refreshed = await chat_routes.get_secure_form(
        "agent-1", record.pending_id, user=user, server=env.server
    )
    assert refreshed.existing_vault_item_id == created.vault_item_id
    assert refreshed.existing_slot_names == ["CARD_EXP"]
    assert _MARK_CVV not in refreshed.model_dump_json()


@pytest.mark.asyncio
async def test_get_404_unknown_and_410_expired(env: Env) -> None:
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    with pytest.raises(OctopError) as missing:
        await chat_routes.get_secure_form("agent-1", "beef", user=user, server=env.server)
    assert missing.value.code is ErrorCode.NOT_FOUND
    assert missing.value.status == 404

    first = env.register_form(ENV_FORM)
    env.register_form({**ENV_FORM, "title": "Newer form"})  # evicts the first card
    with pytest.raises(OctopError) as expired:
        await chat_routes.get_secure_form("agent-1", first.pending_id, user=user, server=env.server)
    assert expired.value.code is ErrorCode.SECURE_FORM_PENDING_EXPIRED
    assert expired.value.status == 410


# ---------------------------------------------------------------- vault router


@pytest.mark.asyncio
async def test_vault_router_list_is_metadata_only(env: Env) -> None:
    env.vault.store_item(
        env.owner.id,
        "login",
        "GitHub",
        "https://github.com",
        {"text": _MARK_USER},
        replace_confirmed=False,
    )
    user = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")

    out = await vault_routes.list_vault_items(user=user, server=env.server)

    assert len(out.items) == 1
    item = out.items[0]
    assert item.title == "GitHub" and item.item_type == "login"
    assert item.origin == "https://github.com"
    payload = item.model_dump_json()
    assert _MARK_USER not in payload and "fields_blob" not in payload


@pytest.mark.asyncio
async def test_vault_router_delete_owner_admin_and_non_owner(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = env.vault.store_item(
        env.owner.id, "login", "GitHub", None, {"text": _MARK_USER}, replace_confirmed=False
    )
    owner = SimpleNamespace(id=env.owner.id, is_admin=False, username="owner")
    intruder = SimpleNamespace(id=env.intruder.id, is_admin=False, username="intruder")
    admin = SimpleNamespace(id=env.intruder.id, is_admin=True, username="intruder")

    with pytest.raises(OctopError) as forbidden:
        await vault_routes.delete_vault_item(row.vault_item_id, user=intruder, server=env.server)
    assert forbidden.value.code is ErrorCode.VAULT_ITEM_NOT_FOUND

    out = await vault_routes.delete_vault_item(row.vault_item_id, user=owner, server=env.server)
    assert out == {"deleted": True}
    assert env.vault.list_items(env.owner.id) == []
    audits = env.shared.repos.audit_repo.query(action="vault.delete", limit=5)
    assert [a.target for a in audits] == [row.vault_item_id]

    # Admin may delete another user's item after the owner re-creates it.
    again = env.vault.store_item(
        env.owner.id, "login", "GitHub", None, {"text": "x"}, replace_confirmed=False
    )
    out = await vault_routes.delete_vault_item(again.vault_item_id, user=admin, server=env.server)
    assert out == {"deleted": True}
    assert env.vault.list_items(env.owner.id) == []


# ---------------------------------------------------------------- 422 validation echo


def _build_echo_app() -> FastAPI:
    from octop.api.app import _install_exception_handlers

    app = FastAPI()
    _install_exception_handlers(app)

    def _raise() -> None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "values"),
                    "msg": "Invalid input",
                    "input": {"host": _MARK_HOST},
                    "ctx": {"error": _MARK_HOST},
                }
            ]
        )

    @app.post("/api/agents/{agent_id}/chat/secure-form/submit")
    async def secure_form_route(agent_id: str) -> None:
        _raise()

    @app.post("/api/agents/{agent_id}/chat/other/submit")
    async def lookalike_route(agent_id: str) -> None:
        _raise()

    return app


def test_validation_422_does_not_echo_values_on_submit_route() -> None:
    client = TestClient(_build_echo_app())
    r = client.post("/api/agents/a1/chat/secure-form/submit", json={})
    assert r.status_code == 422
    assert _MARK_HOST not in r.text
    assert r.json()["detail"][0]["loc"] == ["body", "values"]


def test_validation_422_keeps_stock_body_on_lookalike_route() -> None:
    client = TestClient(_build_echo_app())
    r = client.post("/api/agents/a1/chat/other/submit", json={})
    assert r.status_code == 422
    assert _MARK_HOST in r.text
