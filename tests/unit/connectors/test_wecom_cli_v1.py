"""Regression coverage for the official WeCom CLI 1.x command model."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.gateway import cli_runner
from octop.infra.connectors.gateway.adapters import wecom_cli


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setenv("WECOM_CLI_ACCESS_TOKEN", "another-connectors-token")
    monkeypatch.setattr(wecom_cli, "resolve_binary", lambda _: fake_bin_path("wecom-cli"))
    monkeypatch.setattr(wecom_cli, "materialize_wecom_bot_config", lambda *a, **k: None)
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> str:
        env = kwargs["env"]
        assert "WECOM_CLI_ACCESS_TOKEN" not in env
        assert Path(env["WECOM_CLI_CONFIG_DIR"]) == (
            tmp_path / "connector-cli" / "wecom-cli" / "instance"
        )
        calls.append(argv)
        if argv[1:] == ["--version"]:
            return "wecom-cli 1.3.4 (wecom build commit)"
        return '{"ok":true}'

    monkeypatch.setattr(wecom_cli, "run_cli", run)
    return calls


CREDS = {"bot_id": "bot", "bot_secret": "secret", "instance_id": "instance"}


@pytest.mark.parametrize(
    ("category", "method", "command"),
    [
        ("doc", "search", ["doc", "search"]),
        ("doc", "contents.get", ["doc", "contents", "get"]),
        ("doc", "doc.contents.get", ["doc", "contents", "get"]),
        ("doc", "get_doc_content", ["doc", "contents", "get"]),
        ("sheet", "get", ["sheet", "get"]),
        ("sheet", "sheet.ranges.get", ["sheet", "ranges", "get"]),
        ("smartsheet", "records.list", ["smartsheet", "records", "list"]),
        ("doc", "smartsheet_get_sheet", ["smartsheet", "sheets", "list"]),
        ("doc", "smartsheet_get_records", ["smartsheet", "records", "list"]),
        ("schedule", "calendar.schedules.get", ["calendar", "schedules", "get"]),
        ("msg", "message.aibot.sessions.list", ["message", "aibot", "sessions", "list"]),
    ],
)
def test_modern_methods_preserve_json(
    cli: list[list[str]], category: str, method: str, command: list[str]
) -> None:
    payload = {"keywords": ['中文 "引号" & %PATH%'], "limit": 5}
    result = wecom_cli.call_tool(CREDS, category, {"method": method, "args": payload})
    assert result == '{"ok":true}'
    assert cli[-1][1:-1] == [*command, "--json"]
    assert json.loads(cli[-1][-1]) == payload


def test_serialized_mcp_args_are_not_discarded(cli: list[list[str]]) -> None:
    wecom_cli.call_tool(CREDS, "doc", {"method": "search", "args": '{"keywords":["水电"]}'})
    assert json.loads(cli[-1][-1]) == {"keywords": ["水电"]}


@pytest.mark.parametrize("payload", ["{", "[]", [], 1])
def test_invalid_payload_does_not_execute(cli: list[list[str]], payload: Any) -> None:
    with pytest.raises(ValueError, match="JSON object"):
        wecom_cli.call_tool(CREDS, "doc", {"method": "search", "args": payload})
    assert len(cli) == 1  # Only the version probe ran.


@pytest.mark.parametrize("method", ["--help", "contents get", "doc", "contents..get", "get&whoami"])
def test_method_cannot_inject_flags_or_shell(cli: list[list[str]], method: str) -> None:
    with pytest.raises(ValueError, match="method"):
        wecom_cli.call_tool(CREDS, "doc", {"method": method})
    assert len(cli) == 1


@pytest.mark.parametrize(
    ("category", "method", "command"),
    [
        ("doc", None, ["doc", "--schema"]),
        ("sheet", "ranges.get", ["sheet", "ranges", "get", "--schema"]),
        ("schedule", None, ["calendar", "--schema"]),
        ("msg", None, ["message", "--schema"]),
    ],
)
def test_help_exposes_machine_readable_schema(
    cli: list[list[str]], category: str, method: str | None, command: list[str]
) -> None:
    wecom_cli.call_tool(CREDS, "help", {"category": category, "method": method})
    assert cli[-1][1:] == command


def test_category_help_does_not_send_empty_json(cli: list[list[str]]) -> None:
    wecom_cli.call_tool(CREDS, "doc", {"method": "help", "args": {}})
    assert cli[-1][1:] == ["doc", "--schema"]


@pytest.mark.parametrize(("version", "modern"), [("0.1.9", False), ("1.3.4", True)])
def test_version_detection(monkeypatch: pytest.MonkeyPatch, version: str, modern: bool) -> None:
    monkeypatch.setattr(wecom_cli, "run_cli", lambda *a, **k: f"wecom-cli {version}")
    assert wecom_cli._uses_modern_cli(fake_bin_path("wecom-cli"), {}) is modern


def test_unknown_version_is_not_silently_treated_as_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wecom_cli, "run_cli", lambda *a, **k: "{}")
    with pytest.raises(ValueError, match="版本"):
        wecom_cli._uses_modern_cli(fake_bin_path("wecom-cli"), {})


@pytest.mark.parametrize("status", ["authorized", "unauthorized"])
def test_probe_checks_modern_authorization(
    cli: list[list[str]], monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    config_dir = Path(wecom_cli._prepare_env(CREDS)["WECOM_CLI_CONFIG_DIR"])
    (config_dir / "mcp_config.enc").write_bytes(b"cache")
    monkeypatch.setattr(wecom_cli, "read_mcp_items_count", lambda _: 2)
    original = wecom_cli.run_cli

    def run(argv: list[str], **kwargs: Any) -> str:
        if argv[1:3] == ["auth", "show"]:
            cli.append(argv)
            assert argv[3:] == ["--status"]
            return status
        return original(argv, **kwargs)

    monkeypatch.setattr(wecom_cli, "run_cli", run)
    if status == "authorized":
        wecom_cli.probe_credentials(CREDS)
        assert cli[-1][1:] == ["doc", "--schema"]
    else:
        with pytest.raises(ValueError, match="Bot"):
            wecom_cli.probe_credentials(CREDS)
        assert cli[-1][1:] == ["auth", "show", "--status"]


@pytest.mark.skipif(os.name != "nt", reason="npm CMD shims are Windows-specific")
@pytest.mark.parametrize("nested", [True, False])
def test_windows_prefers_native_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, nested: bool
) -> None:
    shim = tmp_path / "wecom-cli.cmd"
    packages = tmp_path / "node_modules" / "@wecom"
    if nested:
        packages = packages / "cli" / "node_modules" / "@wecom"
    native = packages / "cli-win32-x64" / "bin" / "wecom-cli.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"binary")
    monkeypatch.setattr(wecom_cli, "resolve_binary", lambda _: str(shim))
    assert Path(wecom_cli._resolve_cli_binary()) == native


def test_subprocess_roundtrip_preserves_utf8_and_json(tmp_path: Path) -> None:
    script = tmp_path / "echo_args.py"
    script.write_text(
        "import json,sys\n"
        "sys.stdout.buffer.write(json.dumps(json.loads(sys.argv[1]), ensure_ascii=False).encode('utf-8'))\n",
        encoding="utf-8",
    )
    payload = {"keywords": ['水电 "引号" & %PATH%'], "nested": {"enabled": True}}
    output = cli_runner.run_cli(
        [sys.executable, str(script), json.dumps(payload, ensure_ascii=False)]
    )
    assert json.loads(output) == payload
