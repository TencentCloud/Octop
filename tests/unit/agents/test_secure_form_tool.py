"""Unit tests for the request_secure_form tool slice (schema, validation, wiring)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.secret_input import (
    REQUEST_SECURE_FORM_TOOL_NAME,
    SECURE_FORM_HEADLESS_FALLBACK,
    SECURE_FORM_INTERRUPT_ON,
    build_request_secure_form_tool,
    extract_secure_form_request,
    normalize_secure_form_origin,
    normalize_slot_name,
    validate_secure_form_action_requests,
    validate_secure_form_args,
)
from octop.infra.agents.secret_input.middleware import SecureFormMiddleware
from octop.infra.agents.security.hitl_session import HitlSessionPolicy, apply_session_bypass
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRow
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError

# ---------------------------------------------------------------- slot denylist


@pytest.mark.parametrize(
    "name",
    [
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "PYTHONPATH",
        "PYTHONHOME",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "SSL_CERT_FILE",
    ],
)
def test_exec_hijack_slot_names_are_reserved(name: str) -> None:
    assert normalize_slot_name(name) is None
    assert normalize_slot_name(name.lower()) is None


# ---------------------------------------------------------------- tool schema


def _env_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
        "prompt": "CLI credentials for the deployment host",
        "title": "Deploy credentials",
        "routing": {"kind": "env", "slots": {"host": "DEPLOY_HOST", "password": "DEPLOY_PASS"}},
    }
    args.update(overrides)
    return args


def _vault_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "fields": [
            {"id": "username", "label": "Username", "type": "text"},
            {"id": "password", "label": "Password", "type": "password"},
        ],
        "prompt": "Site login",
        "routing": {
            "kind": "vault",
            "vault_meta": {
                "item_type": "login",
                "title": "Example",
                "origin": "https://example.com",
            },
        },
    }
    args.update(overrides)
    return args


def test_tool_schema_shape() -> None:
    tool = build_request_secure_form_tool()
    assert tool.name == REQUEST_SECURE_FORM_TOOL_NAME
    schema = tool.args_schema.model_json_schema()
    properties = schema.get("properties", {})
    assert set(properties) == {"fields", "prompt", "title", "routing"}
    assert properties["fields"].get("maxItems") == 8
    assert properties["fields"].get("minItems") == 1
    # No field property carries values — the schema is the form definition only.
    field_props = schema["$defs"][_defs_name(schema, "SecureFormFieldArgs")]["properties"]
    assert set(field_props) == {"id", "label", "type", "required", "max_length"}


def _defs_name(schema: dict, model: str) -> str:
    for key, value in schema.get("$defs", {}).items():
        if value.get("title") == model:
            return key
    raise AssertionError(f"{model} not found in schema defs")


@pytest.mark.asyncio
async def test_tool_body_is_headless_fallback() -> None:
    tool = build_request_secure_form_tool()
    out = await tool.coroutine(  # type: ignore[union-attr]
        fields=[{"id": "a", "label": "A", "type": "text"}],
        prompt="p",
        routing={"kind": "env", "slots": {"a": "A_SLOT"}},
        title=None,
    )
    assert out == SECURE_FORM_HEADLESS_FALLBACK


def test_interrupt_entry_is_respond_only() -> None:
    entry = SECURE_FORM_INTERRUPT_ON[REQUEST_SECURE_FORM_TOOL_NAME]
    assert entry["allowed_decisions"] == ["respond"]


def test_middleware_registers_only_secure_form_tool() -> None:
    middleware = SecureFormMiddleware()
    assert set(middleware.interrupt_on) == {REQUEST_SECURE_FORM_TOOL_NAME}
    entry = middleware.interrupt_on[REQUEST_SECURE_FORM_TOOL_NAME]
    assert isinstance(entry, dict)
    assert entry["allowed_decisions"] == ["respond"]
    # Distinct class: the harness merges middleware by class name, so the
    # secure-form channel must never collide with the secret-input one.
    from octop.infra.agents.secret_input.middleware import SecretInputMiddleware

    assert SecureFormMiddleware is not SecretInputMiddleware
    assert SecureFormMiddleware.__name__ != SecretInputMiddleware.__name__


# ---------------------------------------------------------------- field rules


def test_valid_env_form_passes() -> None:
    assert validate_secure_form_args(_env_args()) is None


def test_valid_vault_form_passes() -> None:
    assert validate_secure_form_args(_vault_args()) is None


@pytest.mark.parametrize(
    "field_id",
    ["ok_id", "a", "a1_b", "x" * 32],
)
def test_good_field_ids(field_id: str) -> None:
    args = _env_args(
        fields=[{"id": field_id, "label": "L", "type": "text"}],
        routing={"kind": "env", "slots": {field_id: "SOME_SLOT"}},
    )
    assert validate_secure_form_args(args) is None


@pytest.mark.parametrize(
    "field_id",
    [
        "Has-Caps",
        "has-dash",
        "has space",
        "",
        "1starts",
        "x" * 33,
        "dot.id",
        # ``$``-anchored regexes would let a trailing newline through.
        "ok_id\n",
        7,
        None,
    ],
)
def test_bad_field_ids(field_id: object) -> None:
    args = _env_args(
        fields=[{"id": field_id, "label": "L", "type": "text"}],
        routing={"kind": "env", "slots": {"whatever": "SOME_SLOT"}},
    )
    reason = validate_secure_form_args(args)
    assert reason is not None and "id" in reason


def test_duplicate_field_ids_rejected() -> None:
    args = _env_args(
        fields=[
            {"id": "dup", "label": "A", "type": "text"},
            {"id": "dup", "label": "B", "type": "password"},
        ],
        routing={"kind": "env", "slots": {"dup": "SOME_SLOT"}},
    )
    assert "duplicate field id" in str(validate_secure_form_args(args))


def test_field_count_bounds() -> None:
    many = [{"id": f"f{i}", "label": "L", "type": "text"} for i in range(9)]
    args = _env_args(
        fields=many,
        routing={"kind": "env", "slots": {f"f{i}": f"SLOT_{i}" for i in range(9)}},
    )
    assert "1 to 8" in str(validate_secure_form_args(args))
    assert "1 to 8" in str(validate_secure_form_args(_env_args(fields=[])))


def test_bad_types_and_labels() -> None:
    bad_type = _env_args(
        fields=[{"id": "a", "label": "L", "type": "textarea"}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert "type must be one of" in str(validate_secure_form_args(bad_type))

    long_label = "L" * 61
    bad_label = _env_args(
        fields=[{"id": "a", "label": long_label, "type": "text"}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert "label" in str(validate_secure_form_args(bad_label))

    blank_label = _env_args(
        fields=[{"id": "a", "label": "   ", "type": "text"}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert "label" in str(validate_secure_form_args(blank_label))


def test_required_must_be_boolean() -> None:
    args = _env_args(
        fields=[{"id": "a", "label": "L", "type": "text", "required": "yes"}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert "required must be a boolean" in str(validate_secure_form_args(args))


@pytest.mark.parametrize(
    ("field_type", "max_length", "ok"),
    [
        ("card_number", 11, False),
        ("card_number", 12, True),
        ("card_cvv", 2, False),
        ("card_cvv", 3, True),
        ("otp", 3, False),
        ("otp", 4, True),
        ("card_exp", 4, False),
        ("card_exp", 5, True),
        ("text", 256, True),
        ("text", 257, False),
        ("password", 0, False),
    ],
)
def test_max_length_against_type_minimum(field_type: str, max_length: int, ok: bool) -> None:
    args = _env_args(
        fields=[{"id": "a", "label": "L", "type": field_type, "max_length": max_length}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert (validate_secure_form_args(args) is None) is ok


def test_max_length_must_be_integer() -> None:
    args = _env_args(
        fields=[{"id": "a", "label": "L", "type": "text", "max_length": True}],
        routing={"kind": "env", "slots": {"a": "SOME_SLOT"}},
    )
    assert "max_length must be an integer" in str(validate_secure_form_args(args))


def test_prompt_and_title_bounds() -> None:
    assert "prompt" in str(validate_secure_form_args(_env_args(prompt="x" * 501)))
    assert "prompt" in str(validate_secure_form_args(_env_args(prompt="   ")))
    assert "title" in str(validate_secure_form_args(_env_args(title="t" * 61)))
    assert validate_secure_form_args(_env_args(title=None)) is None


def test_non_object_args_rejected() -> None:
    assert validate_secure_form_args("nope") is not None
    assert validate_secure_form_args(None) is not None


# ---------------------------------------------------------------- env slots


def test_env_routing_requires_slot_per_field() -> None:
    missing = _env_args(routing={"kind": "env", "slots": {"host": "DEPLOY_HOST"}})
    assert "exactly one entry per field id" in str(validate_secure_form_args(missing))
    extra = _env_args(
        routing={"kind": "env", "slots": {"host": "A", "password": "B", "ghost": "C"}}
    )
    assert "exactly one entry per field id" in str(validate_secure_form_args(extra))
    none_at_all = _env_args(routing={"kind": "env"})
    assert "routing.slots" in str(validate_secure_form_args(none_at_all))


def test_env_slot_names_use_shared_rules() -> None:
    args = _env_args(routing={"kind": "env", "slots": {"host": "PATH", "password": "DEPLOY_PASS"}})
    assert "invalid or reserved slot name" in str(validate_secure_form_args(args))
    hijack = _env_args(routing={"kind": "env", "slots": {"host": "LD_PRELOAD", "password": "P"}})
    assert "invalid or reserved slot name" in str(validate_secure_form_args(hijack))


def test_normalized_slot_collision_rejected() -> None:
    args = _env_args(
        routing={"kind": "env", "slots": {"host": "DEPLOY_HOST", "password": "deploy_host"}}
    )
    assert "pairwise distinct" in str(validate_secure_form_args(args))


def test_slot_capacity_check_with_injected_reader() -> None:
    existing = {f"SLOT_{i}" for i in range(31)}
    args = _env_args(
        fields=[
            {"id": "a", "label": "A", "type": "text"},
            {"id": "b", "label": "B", "type": "text"},
        ],
        routing={"kind": "env", "slots": {"a": "NEW_ONE", "b": "NEW_TWO"}},
    )
    reason = validate_secure_form_args(
        args, agent_id="AGT", existing_slot_names=lambda _aid: existing
    )
    assert "slot capacity exceeded" in str(reason)
    # Rotating an existing slot adds no capacity.
    rotate = _env_args(
        fields=[{"id": "a", "label": "A", "type": "text"}],
        routing={"kind": "env", "slots": {"a": "SLOT_0"}},
    )
    assert (
        validate_secure_form_args(rotate, agent_id="AGT", existing_slot_names=lambda _aid: existing)
        is None
    )
    # Without a reader the capacity check is skipped (injectable by design).
    assert validate_secure_form_args(args) is None


# ---------------------------------------------------------------- origin grammar


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("http://example.com", "http://example.com"),
        ("https://Example.COM", "https://example.com"),
        ("https://example.com:8443", "https://example.com:8443"),
        ("https://10.0.0.1", "https://10.0.0.1"),
        ("https://10.0.0.1:9000", "https://10.0.0.1:9000"),
        ("https://[::1]", "https://[::1]"),
        ("https://sub.example.com", "https://sub.example.com"),
        ("https://example.com/", "https://example.com"),
    ],
)
def test_origin_normalization(raw: str, expected: str) -> None:
    assert normalize_secure_form_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://example.com",
        "example.com",
        "https://user@example.com",
        "https://user:pw@example.com",
        "https://example.com.",
        "https://*.example.com",
        "https://ex*ample.com",
        "https://exämple.com",
        "https://example.com/path",
        "https://example.com/?q=1",
        "https://example.com#frag",
        "https://",
        "",
        "not a url",
        None,
        7,
    ],
)
def test_origin_grammar_rejections(raw: object) -> None:
    assert normalize_secure_form_origin(raw) is None


def test_invalid_origin_rejected_in_vault_meta() -> None:
    args = _vault_args()
    routing = dict(args["routing"])  # type: ignore[arg-type]
    routing["vault_meta"] = {"item_type": "login", "title": "T", "origin": "https://a.example.com."}
    reason = validate_secure_form_args(_vault_args(routing=routing))
    assert "origin" in str(reason)


# ---------------------------------------------------------------- vault pairing


@pytest.mark.parametrize(
    ("item_type", "field_types", "ok"),
    [
        ("login", ["text", "password"], True),
        ("login", ["text", "otp"], False),
        ("login", ["password"], True),
        ("card", ["card_number", "card_exp"], True),
        ("card", ["card_number", "card_exp", "card_cvv"], False),
        ("card", ["card_number", "text"], False),
        ("contact", ["text"], True),
        ("contact", ["text", "password"], False),
        ("contact", ["otp"], False),
    ],
)
def test_vault_field_type_pairing(item_type: str, field_types: list[str], ok: bool) -> None:
    fields = [{"id": f"f{i}", "label": f"F{i}", "type": t} for i, t in enumerate(field_types)]
    args = _vault_args(
        fields=fields,
        routing={
            "kind": "vault",
            "vault_meta": {"item_type": item_type, "title": "Item"},
        },
    )
    assert (validate_secure_form_args(args) is None) is ok


def test_vault_meta_required_iff_vault_routing() -> None:
    missing = _vault_args(routing={"kind": "vault"})
    assert "vault_meta is required" in str(validate_secure_form_args(missing))

    bad_item = _vault_args(
        routing={"kind": "vault", "vault_meta": {"item_type": "note", "title": "T"}}
    )
    assert "item_type" in str(validate_secure_form_args(bad_item))

    blank_title = _vault_args(
        routing={"kind": "vault", "vault_meta": {"item_type": "login", "title": "   "}}
    )
    assert "vault_meta.title" in str(validate_secure_form_args(blank_title))

    long_title = _vault_args(
        routing={
            "kind": "vault",
            "vault_meta": {"item_type": "login", "title": "T" * 121},
        }
    )
    assert "vault_meta.title" in str(validate_secure_form_args(long_title))

    # Optional for env routing (offers the save-to-vault checkbox later), but
    # still shape-checked when present.
    with_meta = _env_args(
        routing={
            "kind": "env",
            "slots": {"host": "A", "password": "B"},
            "vault_meta": {"item_type": "login", "title": "T"},
        }
    )
    assert validate_secure_form_args(with_meta) is None
    bad_meta = _env_args(
        routing={
            "kind": "env",
            "slots": {"host": "A", "password": "B"},
            "vault_meta": {"item_type": "login"},
        }
    )
    assert "vault_meta.title" in str(validate_secure_form_args(bad_meta))


def test_routing_kind_validated() -> None:
    assert "routing.kind" in str(
        validate_secure_form_args(_env_args(routing={"kind": "browser_fill"}))
    )
    assert "routing must be an object" in str(validate_secure_form_args(_env_args(routing="env")))


# ---------------------------------------------------------------- action requests


def test_validate_action_requests_scopes_to_secure_form() -> None:
    actions = [
        {"name": "execute", "args": {"command": "ls"}},
        {"name": REQUEST_SECURE_FORM_TOOL_NAME, "args": _env_args()},
    ]
    assert validate_secure_form_action_requests(actions) is None

    bad = [dict(a) for a in actions]
    bad[1] = {
        "name": REQUEST_SECURE_FORM_TOOL_NAME,
        "args": _env_args(fields=[]),
    }
    assert validate_secure_form_action_requests(bad) is not None
    assert validate_secure_form_action_requests([]) is None


def test_extract_secure_form_request_rederives_schema() -> None:
    actions = [
        {"name": REQUEST_SECURE_FORM_TOOL_NAME, "args": _vault_args()},
    ]
    extracted = extract_secure_form_request(actions)
    assert extracted is not None
    assert extracted["routing"]["kind"] == "vault"  # type: ignore[index]
    assert extract_secure_form_request([{"name": "execute", "args": {}}]) is None


# ---------------------------------------------------------------- session bypass


def test_session_bypass_never_skips_secure_form() -> None:
    allow_all = HitlSessionPolicy(mode="allow_all")
    assert allow_all.allows(REQUEST_SECURE_FORM_TOOL_NAME) is False
    allow_tools = HitlSessionPolicy(mode="allow_tools", tools=(REQUEST_SECURE_FORM_TOOL_NAME,))
    assert allow_tools.allows(REQUEST_SECURE_FORM_TOOL_NAME) is False

    interrupt_on = {
        **SECURE_FORM_INTERRUPT_ON,
        "execute": {"allowed_decisions": ["approve", "reject"]},
    }
    out = apply_session_bypass(interrupt_on, None)
    assert out is interrupt_on


# ---------------------------------------------------------------- manager wiring


@pytest.fixture
def manager(tmp_path: Path) -> AgentManager:
    from octop.infra.utils.paths import PathLayout

    layout = PathLayout(tmp_path / ".octop")
    layout.ensure_root()
    db = SqlitePool(layout.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=layout, config=OctopConfig())
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


def test_build_harness_config_mounts_tool_and_middleware(manager: AgentManager) -> None:
    cfg = manager._build_harness_config(_row())
    assert cfg.tools is not None
    names = {t.name for t in cfg.tools}
    assert REQUEST_SECURE_FORM_TOOL_NAME in names
    instances = [m for m in (cfg.middleware or []) if isinstance(m, SecureFormMiddleware)]
    assert len(instances) == 1
    entry = instances[0].interrupt_on[REQUEST_SECURE_FORM_TOOL_NAME]
    assert isinstance(entry, dict)
    assert entry["allowed_decisions"] == ["respond"]


def test_build_harness_config_skips_disabled_tool(manager: AgentManager) -> None:
    cfg_json = json.dumps({"tools_disabled": [REQUEST_SECURE_FORM_TOOL_NAME]})
    cfg = manager._build_harness_config(_row(config_json=cfg_json))
    assert cfg.tools is not None
    assert REQUEST_SECURE_FORM_TOOL_NAME not in {t.name for t in cfg.tools}
    assert not [m for m in (cfg.middleware or []) if isinstance(m, SecureFormMiddleware)]


# ---------------------------------------------------------------- team refusal


def test_team_manager_detects_secure_form_pause() -> None:
    from octop.infra.agents.teams.team_manager import TeamManager

    form_chunk = {
        "type": "hitl_required",
        "request": {
            "action_requests": [{"name": REQUEST_SECURE_FORM_TOOL_NAME, "args": _env_args()}]
        },
    }
    actions = TeamManager._sensitive_pause_actions(form_chunk)
    assert actions is not None and len(actions) == 1
    assert TeamManager._sensitive_pause_actions({"type": "hitl_required"}) is None


def test_refusal_message_shape() -> None:
    from octop.infra.agents.secret_input.validation import (
        secure_form_refusal_decisions,
        secure_form_refusal_message,
    )

    message = secure_form_refusal_message("bad id")
    assert message.startswith("The secure form request was rejected: bad id.")
    assert "Do not retry within this turn." in message
    decisions = secure_form_refusal_decisions(
        [
            {"name": REQUEST_SECURE_FORM_TOOL_NAME, "args": {}},
            {"name": REQUEST_SECURE_FORM_TOOL_NAME, "args": {}},
        ],
        reason="bad id",
    )
    assert [d["type"] for d in decisions] == ["respond", "respond"]
    assert all(d["message"] == message for d in decisions)


def test_registration_error_code_is_defined() -> None:
    err = OctopError(ErrorCode.SECURE_FORM_REQUEST_INVALID, "bad form")
    assert err.code == ErrorCode.SECURE_FORM_REQUEST_INVALID
