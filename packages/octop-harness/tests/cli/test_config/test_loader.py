"""Tests for octop_harness.cli.config.loader."""

import json
from pathlib import Path

from octop_harness.cli.config.loader import load_config


def test_load_config_no_files(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[arg-type]
    cfg, cli_cfg = load_config(project_dir=tmp_path)
    assert cfg is None
    assert cli_cfg.theme == "dark"


def test_load_config_global_only(tmp_path: Path, monkeypatch: object) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))  # type: ignore[arg-type]

    global_dir = home / ".octop-harness"
    global_dir.mkdir(parents=True)
    global_config = {
        "providers": {
            "test": {
                "base_url": "http://localhost:8000",
                "api_key": "sk-test",
                "models": [{"id": "test-model"}],
            }
        },
        "cli": {"theme": "light"},
    }
    (global_dir / "config.json").write_text(json.dumps(global_config))

    cfg, cli_cfg = load_config(project_dir=tmp_path)
    assert cfg is not None
    assert "test" in cfg["providers"]
    assert cli_cfg.theme == "light"


def test_load_config_project_overrides_global(tmp_path: Path, monkeypatch: object) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))  # type: ignore[arg-type]

    global_dir = home / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / "config.json").write_text(json.dumps({"cli": {"theme": "dark"}}))

    project_dir = tmp_path / "project" / ".octop-harness"
    project_dir.mkdir(parents=True)
    (project_dir / "config.json").write_text(json.dumps({"cli": {"theme": "light"}}))

    _, cli_cfg = load_config(project_dir=tmp_path / "project")
    assert cli_cfg.theme == "light"


def test_load_config_credentials_injected(tmp_path: Path, monkeypatch: object) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))  # type: ignore[arg-type]

    global_dir = home / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / "config.json").write_text(
        json.dumps(
            {
                "providers": {
                    "openai": {
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "",
                        "models": [{"id": "gpt-4"}],
                    }
                }
            }
        )
    )
    (global_dir / "credentials.json").write_text(json.dumps({"openai": "sk-real-key"}))

    cfg, _ = load_config(project_dir=tmp_path)
    assert cfg is not None
    assert cfg["providers"]["openai"]["api_key"] == "sk-real-key"


def test_load_config_env_var_does_not_override_credentials(tmp_path: Path, monkeypatch: object) -> None:
    """After cleanup, env vars are NOT read by _inject_credentials; credentials.json wins."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))  # type: ignore[arg-type]
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-should-be-ignored")  # type: ignore[arg-type]

    global_dir = home / ".octop-harness"
    global_dir.mkdir(parents=True)
    (global_dir / "config.json").write_text(
        json.dumps(
            {
                "providers": {
                    "openai": {
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "",
                        "models": [{"id": "gpt-4"}],
                    }
                }
            }
        )
    )
    (global_dir / "credentials.json").write_text(json.dumps({"openai": "sk-from-file"}))

    cfg, _ = load_config(project_dir=tmp_path)
    assert cfg is not None
    assert cfg["providers"]["openai"]["api_key"] == "sk-from-file"


class TestInjectCredentialsEnvCleanup:
    def test_inject_credentials_does_not_read_env(self) -> None:
        """After cleanup, _inject_credentials must NOT read os.environ for api_key."""
        from typing import Any
        from unittest.mock import patch

        from octop_harness.cli.config.loader import _inject_credentials

        providers: dict[str, Any] = {"openai": {"base_url": "https://api.openai.com/v1", "api_key": "from-config"}}
        credentials: dict[str, Any] = {}

        with patch.dict("os.environ", {"OPENAI_API_KEY": "from-env-should-be-ignored"}):
            _inject_credentials(providers, credentials)

        assert providers["openai"]["api_key"] == "from-config"

    def test_inject_credentials_still_reads_credentials_json(self) -> None:
        """credentials.json injection must still work after cleanup."""
        from typing import Any

        from octop_harness.cli.config.loader import _inject_credentials

        providers: dict[str, Any] = {"openai": {"base_url": "https://api.openai.com/v1", "api_key": ""}}
        credentials: dict[str, Any] = {"openai": "sk-from-creds-file"}

        _inject_credentials(providers, credentials)

        assert providers["openai"]["api_key"] == "sk-from-creds-file"
