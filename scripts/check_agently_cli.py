"""Check the installed Agent Mail CLI contract without login or mail operations.

Run with ``uv run scripts/check_agently_cli.py --binary /path/to/agently-cli --runs 3``.
Business commands run only with --dry-run; auth status reads fresh workspace metadata.
The adapter generates the real arguments, but no API response or delivery is simulated.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from octop.infra.connectors.gateway.adapters import agently_cli as adapter
from octop.infra.utils.paths import PathLayout


class CommandChecked(Exception):
    """Stop adapter execution after its generated command passes dry-run."""


def check_round(binary: str) -> int:
    checks = 0
    creds = {"cli_config_key": "contract-a"}
    env = adapter.prepare_env(creds)
    other_env = adapter.prepare_env({"cli_config_key": "contract-b"})
    assert "AGENTLY_CLI_CONFIG_DIR" not in env, "CONFIG_DIR overrides workspace isolation"
    assert env["AGENTLY_WORKSPACE"] != other_env["AGENTLY_WORKSPACE"]
    assert {key for key in env if key.startswith("AGENTLY_")} == {"AGENTLY_WORKSPACE"}

    def run(
        args: list[str],
        *,
        cwd: Path | None = None,
        expected: int = 0,
        environment: dict[str, str] | None = None,
    ) -> str:
        nonlocal checks
        process_env = dict(environment or env)
        process_env.update(AGENTLY_DISABLE_TELEMETRY="1", AGENTLY_CLI_NO_UPDATE_NOTIFIER="1")
        result = subprocess.run(
            [binary, *args],
            cwd=cwd,
            env=process_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == expected, f"Unexpected exit for {args[:2]}: {result.returncode}"
        checks += 1
        return result.stdout

    for workspace_env in (env, other_env):
        data = json.loads(run(["auth", "status"], environment=workspace_env))["data"]
        assert data["workspace"] == workspace_env["AGENTLY_WORKSPACE"]
        assert data["logged_in"] is False, "Smoke workspace unexpectedly has credentials"
    for action in ("login", "logout", "refresh"):
        assert json.loads(run(["auth", action, "--dry-run"]))["data"]["dry_run"] is True
    for command, _, _ in adapter._COMMANDS.values():
        assert json.loads(run([*command, "--print-output-schema"]))

    root = (
        PathLayout.from_env().connector_cli_instance_dir("agently-cli", "contract-a")
        / "attachments"
    )
    attachment = root / "smoke" / "report.txt"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("No credentials or mail operations.\n", encoding="utf-8")
    cases: dict[str, dict[str, Any]] = {
        "agently_me": {},
        "agently_list": {"dir": "inbox", "limit": 50, "is_unread": True},
        "agently_read": {"id": "msg_smoke"},
        "agently_search": {
            "q": "smoke",
            "from": "alice@example.com",
            "search_in": "SEARCH_IN_SUBJECT",
        },
        "agently_send": {
            "to": "alice@example.com,bob@example.com",
            "subject": "Smoke",
            "body": "Dry-run",
            "attachments": "smoke/report.txt",
        },
        "agently_reply": {"id": "msg_smoke", "body": "Dry-run", "reply_all": True},
        "agently_forward": {
            "id": "msg_smoke",
            "to": "alice@example.com",
            "include_attachments": True,
        },
        "agently_trash": {"id": "msg_smoke"},
        "agently_delete": {"id": "msg_smoke"},
        "agently_upload": {
            "filename": "report.txt",
            "content_base64": base64.b64encode(b"Smoke").decode(),
        },
        "agently_download": {"msg": "msg_smoke", "att": "att_smoke"},
    }

    def check_command(
        _creds: dict[str, Any], command: list[str], *, cwd: Path | None = None
    ) -> None:
        dry_command = command if command[-1:] == ["--dry-run"] else [*command, "--dry-run"]
        assert json.loads(run(dry_command, cwd=cwd))["calls"]
        if command[:2] in [adapter._COMMANDS[name][0] for name in adapter._WRITES]:
            assert json.loads(run([*dry_command, "--confirmation-token=ctk_smoke"], cwd=cwd))[
                "calls"
            ]
        # Upload/download cleanup executes normally; no fake server response is needed.
        raise CommandChecked

    with patch.object(adapter, "_run", side_effect=check_command):
        for name, args in cases.items():
            try:
                adapter.call_tool(creds, name, args)
            except CommandChecked:
                pass
            else:
                raise AssertionError(f"Command was not checked: {name}")
    for name in adapter._WRITES:
        command = adapter._COMMANDS[name][0]
        run([*command, "--confirmation-token=ctk_smoke", "--dry-run"], expected=1)
    run(["attachment", "+upload", f"--file={attachment.resolve()}", "--dry-run"], expected=1)
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=shutil.which("agently-cli"))
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if not args.binary or args.runs < 1:
        parser.error("Provide an installed --binary and a positive --runs")
    binary = str(Path(args.binary).resolve())
    clean_env = {key: value for key, value in os.environ.items() if not key.startswith("AGENTLY_")}
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True, timeout=15, env=clean_env
    )
    print(version.stdout.strip())
    for number in range(args.runs):
        with (
            tempfile.TemporaryDirectory(prefix="octop-agently-contract-") as temporary,
            patch.dict(os.environ, {**clean_env, "OCTOP_HOME": temporary}, clear=True),
        ):
            checks = check_round(binary)
        print(f"Round {number + 1}: {checks} checks passed (no login or mail operations)")


if __name__ == "__main__":
    main()
