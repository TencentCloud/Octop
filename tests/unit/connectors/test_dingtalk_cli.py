from __future__ import annotations

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.gateway.adapters import dingtalk_cli
from octop.infra.connectors.gateway.registry import get_gateway_adapter


def test_credentials_are_an_optional_pair_with_isolation_key() -> None:
    with pytest.raises(ValueError, match="client_id and client_secret"):
        validate_create_credentials("dingtalk-cli", {"client_id": "k"})
    out = validate_create_credentials("dingtalk-cli", {"client_id": "k", "client_secret": "s"})
    assert out["client_id"] == "k" and out["cli_config_key"] and out["internal_token"]
    official = validate_create_credentials("dingtalk-cli", {})
    assert "client_id" not in official and official["cli_config_key"]


def test_env_uses_official_app_without_pair(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setenv("DWS_CLIENT_ID", "host-wide")
    env = dingtalk_cli.prepare_env({"cli_config_key": "inst2"})
    assert "DWS_CLIENT_ID" not in env and "DWS_CLIENT_SECRET" not in env
    assert env["DWS_CONFIG_DIR"].endswith("inst2")


def test_call_tool_passes_argv_and_isolated_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    seen: dict = {}
    monkeypatch.setattr(dingtalk_cli, "resolve_binary", lambda _n: fake_bin_path("dws"))

    def fake_run(argv, *, env, timeout_s, stdin_text):
        seen.update(argv=argv, env=env, stdin_text=stdin_text)
        return "{}"

    monkeypatch.setattr(dingtalk_cli, "run_cli", fake_run)
    creds = {"client_id": "k", "client_secret": "s", "cli_config_key": "inst1"}
    dingtalk_cli.call_tool(creds, "dws", {"args": ["contact", "user", "search"]})
    assert seen["argv"][1:] == ["contact", "user", "search"]
    assert seen["env"]["DWS_CLIENT_ID"] == "k"
    assert seen["stdin_text"] == ""  # never inherit the server's stdin
    dingtalk_cli.call_tool(creds, "dws", {"args": "--help"})
    assert seen["argv"][1:] == ["--help"]
    assert "inst1" in seen["env"]["DWS_CONFIG_DIR"]


def test_call_tool_rejects_interactive_and_bad_args() -> None:
    creds = {"client_id": "k", "client_secret": "s", "cli_config_key": "i"}
    with pytest.raises(ValueError, match="not available"):
        dingtalk_cli.call_tool(creds, "dws", {"args": ["auth", "login"]})
    for smuggled in ("--profile x auth login", "-v upgrade -y"):
        with pytest.raises(ValueError, match="must start with a dws product"):
            dingtalk_cli.call_tool(creds, "dws", {"args": smuggled})
    with pytest.raises(ValueError, match="non-empty command line"):
        dingtalk_cli.call_tool(creds, "dws", {"args": "   "})
    with pytest.raises(ValueError, match="not a valid command line"):
        dingtalk_cli.call_tool(creds, "dws", {"args": 'contact "unclosed'})


def test_llm_facing_schema_round_trips_a_command_line(monkeypatch, tmp_path) -> None:
    # Regression: harness mcp_args_model maps non-scalar JSON types to str, so an
    # array schema made every real LLM call fail validation in the adapter.
    from octop_harness.mcp import mcp_args_model

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    seen: dict = {}
    monkeypatch.setattr(dingtalk_cli, "resolve_binary", lambda _n: fake_bin_path("dws"))
    monkeypatch.setattr(dingtalk_cli, "run_cli", lambda argv, **_: seen.setdefault("argv", argv))
    model = mcp_args_model("dws", dingtalk_cli.TOOLS[0]["inputSchema"])
    for raw, want in (
        (
            'contact user search --query "Ada Lovelace" -f json',
            ["contact", "user", "search", "--query", "Ada Lovelace", "-f", "json"],
        ),
        ('["contact", "user", "get-self"]', ["contact", "user", "get-self"]),
    ):
        seen.clear()
        payload = model(args=raw).model_dump()
        dingtalk_cli.call_tool({"cli_config_key": "i"}, "dws", payload)
        assert seen["argv"][1:] == want


def test_registered() -> None:
    assert get_gateway_adapter("dingtalk-cli") is dingtalk_cli


def test_large_output_is_truncated_with_a_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(dingtalk_cli, "resolve_binary", lambda _n: fake_bin_path("dws"))
    monkeypatch.setattr(dingtalk_cli, "run_cli", lambda argv, **_: "x" * 40_000)
    out = dingtalk_cli.call_tool({"cli_config_key": "i"}, "dws", {"args": "chat +chat-messages"})
    assert out.startswith("x" * 32_000) and "truncated 8000 chars" in out
