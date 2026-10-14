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

    def fake_run(argv, *, env, timeout_s):
        seen.update(argv=argv, env=env)
        return "{}"

    monkeypatch.setattr(dingtalk_cli, "run_cli", fake_run)
    creds = {"client_id": "k", "client_secret": "s", "cli_config_key": "inst1"}
    dingtalk_cli.call_tool(creds, "dws", {"args": ["contact", "user", "search"]})
    assert seen["argv"][1:] == ["contact", "user", "search"]
    assert seen["env"]["DWS_CLIENT_ID"] == "k"
    assert "inst1" in seen["env"]["DWS_CONFIG_DIR"]


def test_call_tool_rejects_interactive_and_bad_args() -> None:
    creds = {"client_id": "k", "client_secret": "s", "cli_config_key": "i"}
    with pytest.raises(ValueError, match="not available"):
        dingtalk_cli.call_tool(creds, "dws", {"args": ["auth", "login"]})
    with pytest.raises(ValueError, match="non-empty array"):
        dingtalk_cli.call_tool(creds, "dws", {"args": "contact"})


def test_registered() -> None:
    assert get_gateway_adapter("dingtalk-cli") is dingtalk_cli
