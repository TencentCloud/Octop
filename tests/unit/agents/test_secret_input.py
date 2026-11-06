"""Unit tests for the chat secret-input feature (slots, tool, service, manager wiring)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.secret_input import (
    AGENT_SECRET_MAX_VALUE_CHARS,
    REQUEST_SECRET_INPUT_TOOL_NAME,
    SECRET_INPUT_HEADLESS_FALLBACK,
    SECRET_INPUT_INTERRUPT_ON,
    AgentSecretService,
    build_request_secret_input_tool,
    normalize_slot_name,
)
from octop.infra.agents.security.hitl_session import (
    HitlSessionPolicy,
    apply_session_bypass,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

# ---------------------------------------------------------------- slots


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("STEAM_WEB_API_KEY", "STEAM_WEB_API_KEY"),
        ("github_token", "GITHUB_TOKEN"),
        ("_private", "_PRIVATE"),
        ("a1_b2", "A1_B2"),
        ("PATH", None),
        ("HOME", None),
        ("OCTOP_AGENT_ID", None),
        ("1STARTS_WITH_DIGIT", None),
        ("has-dash", None),
        ("has space", None),
        ("", None),
        (None, None),
        (123, None),
        ("X" * 65, None),
        ("X" * 64, "X" * 64),
    ],
)
def test_normalize_slot_name(raw: object, expected: str | None) -> None:
    assert normalize_slot_name(raw) == expected


# ---------------------------------------------------------------- tool


def test_tool_schema_has_no_value_argument() -> None:
    tool = build_request_secret_input_tool()
    assert tool.name == REQUEST_SECRET_INPUT_TOOL_NAME
    schema = tool.args_schema.model_json_schema()
    properties = schema.get("properties", {})
    assert set(properties) == {"slot", "prompt", "title"}
    assert "value" not in properties
    assert "secret" not in properties


@pytest.mark.asyncio
async def test_tool_body_is_headless_fallback() -> None:
    tool = build_request_secret_input_tool()
    out = (
        await asyncio.to_thread(tool.func, slot="X_TOKEN", prompt="need it", title=None)
        if tool.func
        else None
    )  # StructuredTool.from_function(coroutine=...) path:
    if out is None:
        out = await tool.coroutine(slot="X_TOKEN", prompt="need it", title=None)  # type: ignore[union-attr]
    assert out == SECRET_INPUT_HEADLESS_FALLBACK
    assert "X_TOKEN" not in out


def test_interrupt_entry_is_respond_only() -> None:
    entry = SECRET_INPUT_INTERRUPT_ON[REQUEST_SECRET_INPUT_TOOL_NAME]
    assert entry["allowed_decisions"] == ["respond"]


# ---------------------------------------------------------------- service


@pytest.fixture
def service(tmp_path: Path) -> AgentSecretService:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    shared = build_shared_services(db=db, paths=paths, config=OctopConfig())
    # agent_secrets.agent_id is FK-bound to agents(agent_id), which is
    # FK-bound to users(id) — seed the chain.
    shared.repos.user_repo.create(username="owner", role="user")
    owner = shared.repos.user_repo.get_by_username("owner")
    assert owner is not None
    shared.repos.agent_repo.create(agent_id="AGT1", user_id=owner.id, name="bot")
    return AgentSecretService(
        repo=shared.repos.agent_secret_repo,
        secret_repo=shared.repos.secret_repo,
    )


def test_store_and_decrypt_roundtrip(service: AgentSecretService) -> None:
    row = service.store_slot(
        agent_id="AGT1",
        user_id=7,
        slot_name="STEAM_WEB_API_KEY",
        value="sk-live-abc123",
        display_name="Steam key",
    )
    assert row.slot_name == "STEAM_WEB_API_KEY"
    # List endpoints never see ciphertext or values.
    listed = service.list_slots("AGT1")
    assert [r.slot_name for r in listed] == ["STEAM_WEB_API_KEY"]
    assert all(r.secret_blob is None for r in listed)
    # Decrypting read returns the plaintext env mapping.
    assert service.decrypt_env("AGT1") == {"STEAM_WEB_API_KEY": "sk-live-abc123"}
    # Ciphertext stored, not plaintext.
    raw = service.repo.list_for_agent("AGT1", include_blob=True)[0].secret_blob
    assert raw is not None and b"sk-live-abc123" not in raw


def test_store_slot_upsert_rotates(service: AgentSecretService) -> None:
    service.store_slot(agent_id="AGT1", user_id=1, slot_name="tok", value="one")
    service.store_slot(agent_id="AGT1", user_id=1, slot_name="tok", value="two")
    rows = service.list_slots("AGT1")
    assert len(rows) == 1
    assert service.decrypt_env("AGT1") == {"TOK": "two"}
    assert rows[0].rotated_at is not None


def test_store_slot_rejects_invalid_slot(service: AgentSecretService) -> None:
    with pytest.raises(OctopError) as err:
        service.store_slot(agent_id="AGT1", user_id=1, slot_name="PATH", value="x")
    assert err.value.code == ErrorCode.SECRET_SLOT_INVALID


def test_store_slot_rejects_empty_and_oversized_value(service: AgentSecretService) -> None:
    with pytest.raises(OctopError):
        service.store_slot(agent_id="AGT1", user_id=1, slot_name="tok", value="  ")
    with pytest.raises(OctopError):
        service.store_slot(
            agent_id="AGT1",
            user_id=1,
            slot_name="tok",
            value="x" * (AGENT_SECRET_MAX_VALUE_CHARS + 1),
        )


def test_delete_slot(service: AgentSecretService) -> None:
    row = service.store_slot(agent_id="AGT1", user_id=1, slot_name="tok", value="v")
    assert service.delete_slot("AGT1", row.secret_id) is True
    assert service.decrypt_env("AGT1") == {}
    assert service.delete_slot("AGT1", row.secret_id) is False


# ---------------------------------------------------------------- session bypass


def test_session_bypass_never_skips_secret_input() -> None:
    allow_all = HitlSessionPolicy(mode="allow_all")
    assert allow_all.allows(REQUEST_SECRET_INPUT_TOOL_NAME) is False
    allow_tools = HitlSessionPolicy(mode="allow_tools", tools=(REQUEST_SECRET_INPUT_TOOL_NAME,))
    assert allow_tools.allows(REQUEST_SECRET_INPUT_TOOL_NAME) is False

    interrupt_on = {
        **SECRET_INPUT_INTERRUPT_ON,
        "execute": {"allowed_decisions": ["approve", "reject"]},
    }
    out = apply_session_bypass(interrupt_on, None)
    assert out is interrupt_on


# ---------------------------------------------------------------- manager wiring


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    return AgentManager(repos=services.repos, paths=services.paths)


def _row(agent_id: str = "01AGENT", config_json: str | None = None) -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name="bot",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json=config_json,
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def test_build_harness_config_mounts_tool_and_interrupt(manager: AgentManager) -> None:
    from octop.infra.agents.secret_input.middleware import SecretInputMiddleware

    cfg = manager._build_harness_config(_row())
    assert cfg.tools is not None
    names = {t.name for t in cfg.tools}
    assert REQUEST_SECRET_INPUT_TOOL_NAME in names
    # The interrupt rides a dedicated middleware instance, not cfg.interrupt_on
    # (which the harness gates behind bootstrap completion).
    instances = [m for m in (cfg.middleware or []) if isinstance(m, SecretInputMiddleware)]
    assert len(instances) == 1
    entry = instances[0].interrupt_on[REQUEST_SECRET_INPUT_TOOL_NAME]
    assert isinstance(entry, dict)
    assert entry["allowed_decisions"] == ["respond"]


def test_build_harness_config_skips_disabled_tool(manager: AgentManager) -> None:
    from octop.infra.agents.secret_input.middleware import SecretInputMiddleware

    cfg_json = json.dumps({"tools_disabled": [REQUEST_SECRET_INPUT_TOOL_NAME]})
    cfg = manager._build_harness_config(_row(config_json=cfg_json))
    assert cfg.tools is not None
    assert REQUEST_SECRET_INPUT_TOOL_NAME not in {t.name for t in cfg.tools}
    assert not [m for m in (cfg.middleware or []) if isinstance(m, SecretInputMiddleware)]


def test_build_harness_config_injects_secret_env(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager, "_agent_secret_env", lambda _aid: {"MY_TOKEN": "tok-plain"})
    cfg = manager._build_harness_config(_row())
    backend = cfg.backend
    assert isinstance(backend, dict)
    env = backend.get("env") or {}
    assert env.get("MY_TOKEN") == "tok-plain"
    # Platform identity vars still ride along.
    assert "OCTOP_AGENT_ID" in env


def test_build_harness_config_skips_secret_env_for_shared_agent(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shared agent's commands run for many users; the owner's slots must
    not ride the env overlay there even if a submit slipped in before the
    share flag flipped."""
    from dataclasses import replace as dc_replace

    monkeypatch.setattr(manager, "_agent_secret_env", lambda _aid: {"MY_TOKEN": "tok-plain"})
    cfg = manager._build_harness_config(dc_replace(_row(), is_shared=1))
    backend = cfg.backend
    assert isinstance(backend, dict)
    assert "MY_TOKEN" not in (backend.get("env") or {})
    # Platform identity vars are unaffected by the skip.
    assert "OCTOP_AGENT_ID" in (backend.get("env") or {})


def test_team_manager_detects_secret_input_pause() -> None:
    """Member pauses carrying request_secret_input are refused inline instead
    of opening a room card the dashboard cannot satisfy."""
    from octop.infra.agents.teams.team_manager import TeamManager

    secret_chunk = {
        "type": "hitl_required",
        "request": {
            "action_requests": [
                {"name": REQUEST_SECRET_INPUT_TOOL_NAME, "args": {"slot": "TOKEN", "prompt": "p"}}
            ]
        },
    }
    approval_chunk = {
        "type": "hitl_required",
        "request": {"action_requests": [{"name": "run_command", "args": {"command": "ls"}}]},
    }
    actions = TeamManager._secret_input_pause_actions(secret_chunk)
    assert actions is not None and len(actions) == 1
    assert TeamManager._secret_input_pause_actions(approval_chunk) is None
    assert TeamManager._secret_input_pause_actions({"type": "hitl_required"}) is None


def test_secret_filled_message_reflects_injection_outcome() -> None:
    """The resumed tool result must not promise a usable env when the harness
    rebuild failed — the model would run commands against a missing variable."""
    from octop.infra.agents.secret_input.submit import _secret_filled_message

    ok = _secret_filled_message("MY_TOKEN", injected=True)
    assert "use it right now" in ok
    assert "NEXT turn" not in ok
    degraded = _secret_filled_message("MY_TOKEN", injected=False)
    assert "NEXT turn" in degraded
    assert "use it right now" not in degraded


@pytest.mark.asyncio
async def test_manager_schedule_reload_is_public(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    reloaded = AsyncMock()
    monkeypatch.setattr(manager, "_reload_agent", reloaded)
    manager.schedule_reload("01AGENT")
    await asyncio.sleep(0)
    reloaded.assert_called_once_with("01AGENT")


@pytest.mark.asyncio
async def test_manager_reload_reports_rebuild_outcome(
    manager: AgentManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The secret submit path must observe the rebuilt env before resuming."""
    for outcome in (True, False):
        reloaded = AsyncMock(return_value=outcome)
        monkeypatch.setattr(manager, "_reload_agent", reloaded)
        assert await manager.reload("01AGENT") is outcome
        reloaded.assert_awaited_once_with("01AGENT")
