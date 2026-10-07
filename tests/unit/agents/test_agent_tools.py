"""tests/unit/test_agent_tools.py"""

from __future__ import annotations

from octop_harness.messages import extract_call_response
from octop_harness.teams.tools import build_team_tools


def test_extract_call_response_last_assistant() -> None:
    result = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    }
    assert extract_call_response(result) == "hello"


def test_build_team_tools_exposes_list_and_ask() -> None:
    tools = build_team_tools(object())  # type: ignore[arg-type]
    names = {t.name for t in tools}
    assert names == {"agent_list", "ask_agent"}


def test_ask_agent_schema_includes_mode() -> None:
    tools = build_team_tools(object())  # type: ignore[arg-type]
    ask = next(t for t in tools if t.name == "ask_agent")
    schema = ask.args_schema.model_json_schema() if ask.args_schema else {}
    props = schema.get("properties", {})
    assert "mode" in props
    assert props["mode"]["enum"] == ["sync", "background"]
