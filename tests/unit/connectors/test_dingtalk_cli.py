from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.gateway.adapters import dingtalk_cli
from octop.infra.connectors.gateway.registry import get_gateway_adapter


@pytest.fixture(autouse=True)
def file_backed_platform(monkeypatch):
    monkeypatch.setattr(dingtalk_cli, "sys", SimpleNamespace(platform="linux"))


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


def test_env_overrides_shared_keychain_without_changing_host(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "shared-home"))
    monkeypatch.setenv("DWS_KEYCHAIN_DIR", str(tmp_path / "shared-keychain"))
    first = dingtalk_cli.prepare_env({"cli_config_key": "first"})
    second = dingtalk_cli.prepare_env({"cli_config_key": "second"})
    for env in (first, second):
        assert Path(env["DWS_KEYCHAIN_DIR"]) == Path(env["DWS_CONFIG_DIR"]) / "keychain"
        assert Path(env["DWS_KEYCHAIN_DIR"]).is_dir()
        assert env["HOME"] == str(tmp_path / "shared-home")
        assert env["DWS_DISABLE_KEYCHAIN"] == "1"
    assert first["DWS_KEYCHAIN_DIR"] != second["DWS_KEYCHAIN_DIR"]
    assert dingtalk_cli.os.environ["DWS_KEYCHAIN_DIR"] == str(tmp_path / "shared-keychain")


def test_env_does_not_reuse_legacy_config_or_token_files(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    legacy = tmp_path / "connector-cli" / "dingtalk-cli" / "instance"
    legacy.mkdir(parents=True)
    (legacy / ".data").write_text("legacy-auth", encoding="utf-8")
    env = dingtalk_cli.prepare_env({"cli_config_key": "instance"})
    assert Path(env["DWS_CONFIG_DIR"]) == (
        tmp_path / "connector-cli" / "dingtalk-cli-v2" / "instance"
    )
    assert not (Path(env["DWS_CONFIG_DIR"]) / ".data").exists()
    assert (legacy / ".data").read_text(encoding="utf-8") == "legacy-auth"


@pytest.mark.skipif(dingtalk_cli.os.name != "posix", reason="POSIX directory permissions")
def test_auth_directories_are_private(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    env = dingtalk_cli.prepare_env({"cli_config_key": "private"})
    for key in ("DWS_CONFIG_DIR", "DWS_KEYCHAIN_DIR"):
        assert Path(env[key]).stat().st_mode & 0o777 == 0o700


def test_windows_registry_backend_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(dingtalk_cli, "sys", SimpleNamespace(platform="win32"))
    with pytest.raises(ValueError, match="Linux or macOS"):
        dingtalk_cli.prepare_env({"cli_config_key": "instance"})


def test_credentials_cannot_select_another_instances_directory() -> None:
    supplied = {"cli_config_key": "victim", "instance_id": "victim"}
    first = validate_create_credentials("dingtalk-cli", supplied)
    second = validate_create_credentials("dingtalk-cli", supplied)
    assert first["cli_config_key"] != second["cli_config_key"]
    assert first["cli_config_key"] != "victim" and second["cli_config_key"] != "victim"
    assert "instance_id" not in first and "instance_id" not in second


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
