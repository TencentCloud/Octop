"""Agent default_conversation_mode in API row payload (#616 M8)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.api.routers.agents import _row_dict, _validated_agent_config
from octop.infra.errors import ErrorCode, OctopError


def _agent_row(**kwargs: object) -> SimpleNamespace:
    base = {
        "id": 1,
        "agent_id": "ag1",
        "user_id": 1,
        "name": "A",
        "description": None,
        "persona_mbti": None,
        "default_model": None,
        "system_prompt": None,
        "last_state": "stopped",
        "last_error": None,
        "config_json": "{}",
        "icon": None,
        "template_name": None,
        "icon_name": None,
        "icon_url": None,
        "color": None,
        "skill_package_ids": None,
        "published_expert_id": None,
        "welcome_message": None,
        "is_shared": 0,
        "updated_at": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_row_dict_exposes_default_conversation_mode_from_config() -> None:
    import json

    row = _agent_row(config_json=json.dumps({"default_conversation_mode": "ask"}))
    payload = _row_dict(row, viewer_user_id=1)
    assert payload["default_conversation_mode"] == "ask"
    assert payload["config"]["default_conversation_mode"] == "ask"


def test_row_dict_defaults_conversation_mode_to_craft() -> None:
    payload = _row_dict(_agent_row(), viewer_user_id=1)
    assert payload["default_conversation_mode"] == "craft"


def test_validated_agent_config_rejects_invalid_mode() -> None:
    with pytest.raises(OctopError) as ei:
        _validated_agent_config({"default_conversation_mode": "agent"})
    assert ei.value.code == ErrorCode.INTERNAL_ERROR
    assert ei.value.status == 400


def test_validated_agent_config_accepts_ask() -> None:
    out = _validated_agent_config({"default_conversation_mode": "ask", "foo": 1})
    assert out == {"default_conversation_mode": "ask", "foo": 1}
