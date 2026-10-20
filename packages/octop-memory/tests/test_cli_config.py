"""Tests for CLI configuration management."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.adapters.cli.config import DEFAULTS, load_config, save_config


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        from octop_memory.adapters.cli.config import set_config_path

        set_config_path(tmp_path / "nonexistent.json")
        try:
            config = load_config()
        finally:
            set_config_path(None)
        assert config["backend"] == "sqlite"
        assert config["namespace"] == "default"

    def test_reads_from_file(self, tmp_path: Path) -> None:
        from octop_memory.adapters.cli.config import set_config_path

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"backend": "postgres", "postgres": {"dsn": "postgresql://myhost/db"}}))
        set_config_path(config_file)
        try:
            config = load_config()
        finally:
            set_config_path(None)
        assert config["backend"] == "postgres"
        assert config["postgres"]["dsn"] == "postgresql://myhost/db"
        # Defaults for other sections preserved
        assert config["sqlite"]["db_path"] == "~/.octop-memory/memory.db"

    def test_handles_malformed_file(self, tmp_path: Path) -> None:
        from octop_memory.adapters.cli.config import set_config_path

        config_file = tmp_path / "config.json"
        config_file.write_text("not json!!!")
        set_config_path(config_file)
        try:
            config = load_config()
        finally:
            set_config_path(None)
        assert config == DEFAULTS


class TestSaveConfig:
    def test_creates_file(self, tmp_path: Path) -> None:
        from octop_memory.adapters.cli.config import set_config_path

        config_file = tmp_path / "subdir" / "config.json"
        set_config_path(config_file)
        try:
            save_config({"backend": "postgres"})
        finally:
            set_config_path(None)
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["backend"] == "postgres"


class TestConfigCommands:
    def test_config_show(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--db", str(tmp_path / "t.db"), "config", "show"])
        assert result.exit_code == 0
        assert "Backend:" in result.output

    def test_config_show_json(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--db", str(tmp_path / "t.db"), "--json", "config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert "backend" in data["data"]

    def test_config_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert ".octop-memory" in result.output
        assert "config.json" in result.output

    def test_config_set(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_file), "config", "set", "backend", "postgres"])
        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["backend"] == "postgres"

    def test_config_set_dotted_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--config", str(config_file), "config", "set", "postgres.dsn", "postgresql://myhost/mydb"]
        )
        assert result.exit_code == 0
        data = json.loads(config_file.read_text())
        assert data["postgres"]["dsn"] == "postgresql://myhost/mydb"


class TestBackendResolution:
    def test_default_uses_sqlite(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(main, ["--db", db_path, "--namespace", "test", "memory", "tree"])
        assert result.exit_code == 0

    def test_flag_overrides_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"backend": "postgres"}))
        # --backend flag overrides config file
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--config",
                str(config_file),
                "--backend",
                "sqlite",
                "--db",
                db_path,
                "--namespace",
                "test",
                "memory",
                "tree",
            ],
        )
        assert result.exit_code == 0

    def test_env_var_backend(self, tmp_path: Path, monkeypatch: object) -> None:
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("OCTOP_MEMORY_BACKEND", "sqlite")
        monkeypatch.setenv("OCTOP_MEMORY_DB", db_path)
        runner = CliRunner()
        result = runner.invoke(main, ["--namespace", "test", "memory", "tree"])
        assert result.exit_code == 0

    def test_config_file_flag(self, tmp_path: Path) -> None:
        """--config flag specifies custom config file path."""
        config_file = tmp_path / "custom-config.json"
        db_path = str(tmp_path / "custom.db")
        config_file.write_text(
            json.dumps(
                {
                    "backend": "sqlite",
                    "namespace": "custom-ns",
                    "sqlite": {"db_path": db_path},
                }
            )
        )
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_file), "memory", "tree"])
        assert result.exit_code == 0

    def test_config_file_env_var(self, tmp_path: Path, monkeypatch: object) -> None:
        """OCTOP_MEMORY_CONFIG env var specifies custom config file path."""
        config_file = tmp_path / "env-config.json"
        db_path = str(tmp_path / "env.db")
        config_file.write_text(
            json.dumps(
                {
                    "backend": "sqlite",
                    "sqlite": {"db_path": db_path},
                }
            )
        )
        monkeypatch.setenv("OCTOP_MEMORY_CONFIG", str(config_file))
        runner = CliRunner()
        result = runner.invoke(main, ["--namespace", "test", "memory", "tree"])
        assert result.exit_code == 0

    def test_config_flag_shows_in_path_command(self, tmp_path: Path) -> None:
        """config path shows the custom path when --config is used."""
        config_file = tmp_path / "my-config.json"
        config_file.write_text("{}")
        runner = CliRunner()
        result = runner.invoke(main, ["--config", str(config_file), "config", "path"])
        assert result.exit_code == 0
        assert str(config_file) in result.output
