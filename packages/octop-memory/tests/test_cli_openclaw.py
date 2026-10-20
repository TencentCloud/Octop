"""Tests for ``octop-memory openclaw`` setup / doctor / uninstall."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import openclaw_cmd
from octop_memory.adapters.cli.openclaw_cmd import openclaw_group

# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


class TestSetup:
    def test_creates_config_when_missing(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(openclaw_cmd, "DEFAULT_OPENCLAW_HOME", tmp_path / ".openclaw")
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--namespace", "openclaw__test"],
        )
        assert result.exit_code == 0, result.output
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["plugins"]["slots"]["memory"] == "octopmemory"
        entry = cfg["plugins"]["entries"]["octopmemory"]
        assert entry["enabled"] is True
        assert entry["hooks"]["allowConversationAccess"] is True
        assert entry["config"]["namespace"] == "openclaw__test"
        # db_path is always explicit, under the openclaw home (sandbox-visible).
        assert entry["config"]["db_path"] == str(cfg_path.parent / "octopmemory" / "openclaw__test" / "memory.sqlite")
        assert entry["config"]["mode"] == "self-hosted"
        assert entry["config"]["capture"]["host_files_watcher"] is True
        assert entry["config"]["host_files_root"] == str((tmp_path / ".openclaw" / "workspace").resolve())
        assert entry["config"]["host_files_allow"] == ["topics/*.md", "projects/*.md"]

    def test_bridge_defaults_to_running_environment(self, tmp_path: Path) -> None:
        """Without --bridge-python, setup must point the bridge at the env
        running this command (console script preferred), never bare python3."""
        import sys

        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(openclaw_group, ["setup", "--openclaw-config", str(cfg_path)])
        assert result.exit_code == 0, result.output
        bridge = json.loads(cfg_path.read_text(encoding="utf-8"))["plugins"]["entries"]["octopmemory"]["config"][
            "bridge"
        ]
        script = Path(sys.executable).with_name("octopmemory-bridge")
        if script.exists():
            assert bridge["command"] == str(script)
            assert "python" not in bridge
        else:
            assert bridge["python"] == sys.executable

    def test_bridge_python_flag_overrides_autodetect(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--bridge-python", "/opt/py/bin/python"],
        )
        assert result.exit_code == 0, result.output
        bridge = json.loads(cfg_path.read_text(encoding="utf-8"))["plugins"]["entries"]["octopmemory"]["config"][
            "bridge"
        ]
        assert bridge == {"python": "/opt/py/bin/python", "log_level": "info"}

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--dry-run"],
        )
        assert result.exit_code == 0
        assert not cfg_path.exists()
        # Stdout has the would-be JSON.
        assert '"octopmemory"' in result.output

    def test_preserves_existing_keys(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(openclaw_cmd, "DEFAULT_OPENCLAW_HOME", tmp_path / ".openclaw")
        cfg_path = tmp_path / "openclaw.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "agents": {"defaults": {"compaction": {"reserveTokensFloor": 8192}}},
                    "plugins": {"slots": {"contextEngine": "legacy"}},
                }
            ),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path)],
        )
        assert result.exit_code == 0
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        # Existing keys preserved.
        assert cfg["agents"]["defaults"]["compaction"]["reserveTokensFloor"] == 8192
        assert cfg["plugins"]["slots"]["contextEngine"] == "legacy"
        # New key added.
        assert cfg["plugins"]["slots"]["memory"] == "octopmemory"
        # Namespace is always written explicitly (aligned with setup.ts).
        assert cfg["plugins"]["entries"]["octopmemory"]["config"]["namespace"] == "openclaw__default"
        assert cfg["plugins"]["entries"]["octopmemory"]["config"]["capture"]["host_files_watcher"] is True
        assert cfg["plugins"]["entries"]["octopmemory"]["config"]["host_files_root"] == str(
            (tmp_path / ".openclaw" / "workspace").resolve()
        )

    def test_workspace_enables_host_files_watcher(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        ws = tmp_path / "ws"
        ws.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--workspace", str(ws)],
        )
        assert result.exit_code == 0
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["capture"]["host_files_watcher"] is True
        assert plugin_cfg["host_files_root"] == str(ws.resolve())

    def test_no_host_files_watcher_flag(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--no-host-files-watcher"],
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["capture"]["host_files_watcher"] is False
        assert "host_files_root" not in plugin_cfg

    def test_openclaw_profile_changes_default_workspace(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(openclaw_cmd, "DEFAULT_OPENCLAW_HOME", tmp_path / ".openclaw")
        monkeypatch.setenv("OPENCLAW_PROFILE", "work")
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(openclaw_group, ["setup", "--openclaw-config", str(cfg_path)])
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["host_files_root"] == str((tmp_path / ".openclaw" / "workspace-work").resolve())

    def test_host_files_allow_accepts_repeated_and_csv_values(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            [
                "setup",
                "--openclaw-config",
                str(cfg_path),
                "--host-files-allow",
                "areas/*.md,runbooks/*.md",
                "--host-files-allow",
                "topics/deep/*.md",
            ],
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["host_files_allow"] == ["areas/*.md", "runbooks/*.md", "topics/deep/*.md"]

    def test_no_agent_end_hook_flag(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--no-agent-end-hook"],
        )
        assert result.exit_code == 0
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["plugins"]["entries"]["octopmemory"]["config"]["capture"]["agent_end_hook"] is False

    def test_setup_writes_recall_mode(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--recall-mode", "off"],
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["profile"] == "balanced"
        assert plugin_cfg["recall"]["mode"] == "off"

    def test_setup_profile_privacy_defaults(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--profile", "privacy"],
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["profile"] == "privacy"
        assert plugin_cfg["recall"]["raw_policy"] == "never"
        assert plugin_cfg["capture"]["host_files_watcher"] is False
        assert plugin_cfg["capture"]["include_roles"] == ["user"]
        assert plugin_cfg["privacy"]["store_raw_content"] is False

    def test_setup_explicit_workspace_overrides_profile(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        ws = tmp_path / "ws"
        ws.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--profile", "privacy", "--workspace", str(ws)],
        )
        assert result.exit_code == 0, result.output
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        plugin_cfg = cfg["plugins"]["entries"]["octopmemory"]["config"]
        assert plugin_cfg["capture"]["host_files_watcher"] is True
        assert plugin_cfg["host_files_root"] == str(ws.resolve())

    def test_setup_rejects_invalid_profile(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--profile", "bad"],
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_setup_rejects_invalid_recall_mode(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path), "--recall-mode", "bad"],
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_invalid_json_existing_config_aborts(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        cfg_path.write_text("not json{", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["setup", "--openclaw-config", str(cfg_path)],
        )
        # Click UsageError → exit code 2.
        assert result.exit_code != 0
        assert "not valid JSON" in result.output


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


class TestDoctor:
    def test_fails_when_openclaw_config_missing(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            [
                "doctor",
                "--openclaw-config",
                str(tmp_path / "missing.json"),
                "--extensions-dir",
                str(tmp_path / "extensions"),
            ],
        )
        assert result.exit_code == 1
        assert "openclaw config not found" in result.output

    def test_passes_when_set_up_correctly(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        ext_dir = tmp_path / "extensions"
        plugin_dir = ext_dir / "octopmemory"
        (plugin_dir / "dist").mkdir(parents=True)
        (plugin_dir / "dist" / "index.js").write_text("// built", encoding="utf-8")
        (plugin_dir / "openclaw.plugin.json").write_text(
            json.dumps({"id": "octopmemory", "kind": "memory"}),
            encoding="utf-8",
        )
        cfg_path.write_text(
            json.dumps(
                {
                    "plugins": {
                        "slots": {"memory": "octopmemory"},
                        "entries": {
                            "octopmemory": {
                                "enabled": True,
                                "hooks": {"allowConversationAccess": True},
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["doctor", "--openclaw-config", str(cfg_path), "--extensions-dir", str(ext_dir)],
        )
        assert result.exit_code == 0, result.output
        assert "All required checks passed" in result.output

    def test_fails_when_conversation_access_missing(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        ext_dir = tmp_path / "extensions"
        plugin_dir = ext_dir / "octopmemory"
        (plugin_dir / "dist").mkdir(parents=True)
        (plugin_dir / "dist" / "index.js").write_text("// built", encoding="utf-8")
        (plugin_dir / "openclaw.plugin.json").write_text(
            json.dumps({"id": "octopmemory", "kind": "memory"}),
            encoding="utf-8",
        )
        cfg_path.write_text(
            json.dumps(
                {
                    "plugins": {
                        "slots": {"memory": "octopmemory"},
                        "entries": {"octopmemory": {"enabled": True}},
                    }
                }
            ),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["doctor", "--openclaw-config", str(cfg_path), "--extensions-dir", str(ext_dir)],
        )
        assert result.exit_code == 1
        assert "allowConversationAccess" in result.output

    def test_finds_plugin_installed_via_plugin_manager(self, tmp_path: Path) -> None:
        # `openclaw plugins install` puts the package under
        # ~/.openclaw/npm/projects/<hash>/node_modules/@octop-memory/openclaw
        # rather than the extensions dir; doctor must accept that layout.
        openclaw_home = tmp_path / ".openclaw"
        cfg_path = openclaw_home / "openclaw.json"
        plugin_dir = openclaw_home / "npm" / "projects" / "abc123" / "node_modules" / "@octop-memory" / "openclaw"
        (plugin_dir / "dist").mkdir(parents=True)
        (plugin_dir / "dist" / "index.js").write_text("// built", encoding="utf-8")
        (plugin_dir / "openclaw.plugin.json").write_text(
            json.dumps({"id": "octopmemory", "kind": "memory"}),
            encoding="utf-8",
        )
        cfg_path.write_text(
            json.dumps(
                {
                    "plugins": {
                        "slots": {"memory": "octopmemory"},
                        "entries": {
                            "octopmemory": {
                                "enabled": True,
                                "hooks": {"allowConversationAccess": True},
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            [
                "doctor",
                "--openclaw-config",
                str(cfg_path),
                "--extensions-dir",
                str(openclaw_home / "extensions"),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "All required checks passed" in result.output

    def test_fails_on_disabled_entry(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        ext_dir = tmp_path / "extensions"
        plugin_dir = ext_dir / "octopmemory"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "openclaw.plugin.json").write_text(
            json.dumps({"id": "octopmemory", "kind": "memory"}),
            encoding="utf-8",
        )
        cfg_path.write_text(
            json.dumps(
                {
                    "plugins": {
                        "slots": {"memory": "octopmemory"},
                        "entries": {"octopmemory": {"enabled": False}},
                    }
                }
            ),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["doctor", "--openclaw-config", str(cfg_path), "--extensions-dir", str(ext_dir)],
        )
        assert result.exit_code == 1
        assert "enabled = false" in result.output


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


class TestUninstall:
    def test_removes_slot_binding(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        cfg_path.write_text(
            json.dumps({"plugins": {"slots": {"memory": "octopmemory"}}}),
            encoding="utf-8",
        )
        runner = CliRunner()
        # `--yes` short-circuits the click confirmation prompt.
        result = runner.invoke(
            openclaw_group,
            ["uninstall", "--openclaw-config", str(cfg_path), "--yes"],
        )
        assert result.exit_code == 0
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert "memory" not in cfg.get("plugins", {}).get("slots", {})

    def test_noop_when_already_unset(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "openclaw.json"
        cfg_path.write_text(json.dumps({"plugins": {"slots": {}}}), encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(
            openclaw_group,
            ["uninstall", "--openclaw-config", str(cfg_path), "--yes"],
        )
        assert result.exit_code == 0
        assert "no-op" in result.output


# ---------------------------------------------------------------------------
# print-config
# ---------------------------------------------------------------------------


class TestPrintConfig:
    def test_emits_valid_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(openclaw_group, ["print-config", "--namespace", "myns"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["plugins"]["slots"]["memory"] == "octopmemory"
        cfg = data["plugins"]["entries"]["octopmemory"]["config"]
        assert cfg["profile"] == "balanced"
        assert cfg["namespace"] == "myns"
        assert cfg["recall"]["mode"] == "tool_hint"

    def test_print_config_profile_archive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(openclaw_group, ["print-config", "--profile", "archive"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        cfg = data["plugins"]["entries"]["octopmemory"]["config"]
        assert cfg["profile"] == "archive"
        assert cfg["recall"]["raw_policy"] == "always"
        assert cfg["capture"]["include_tool_results"] is True
        assert cfg["compaction"]["soft_threshold_tokens"] == 3000
