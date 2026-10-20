"""Tests for harness chat command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from octop_harness.cli.main import cli


def test_chat_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
    assert "-p" in result.output
    assert "--model" in result.output
    assert "--session" in result.output
    assert "--agent" in result.output


def test_chat_no_config_shows_error_one_shot(tmp_path: Path, monkeypatch: object) -> None:
    """When no provider is configured in one-shot mode, chat shows a helpful error."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[attr-defined]
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "-p", "hello"])
    # Should exit with error about no provider
    assert "No provider" in result.output or "configure" in result.output.lower()


def test_chat_no_config_launches_wizard(tmp_path: Path, monkeypatch: object) -> None:
    """When no provider is configured in interactive mode, wizard is invoked."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[attr-defined]

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.providers.setup_wizard.run_setup_wizard") as mock_wizard,
        patch("octop_harness.cli.commands.chat._run_repl") as mock_repl,
    ):
        from octop_harness.cli.config.schema import CliConfig
        from octop_harness.cli.providers.setup_wizard import SetupResult

        cli_cfg = CliConfig()
        fake_config = {"providers": {"deepseek": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}
        mock_load.side_effect = [(None, cli_cfg), (fake_config, cli_cfg)]
        mock_wizard.return_value = SetupResult(provider_key="deepseek", model_id="deepseek-chat")

        runner = CliRunner()
        result = runner.invoke(cli, ["chat"])
        assert result.exit_code == 0
        mock_wizard.assert_called_once()
        mock_repl.assert_called_once()


def test_chat_no_config_wizard_cancelled(tmp_path: Path, monkeypatch: object) -> None:
    """When wizard is cancelled, chat exits with error."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fakehome"))  # type: ignore[attr-defined]

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.providers.setup_wizard.run_setup_wizard") as mock_wizard,
    ):
        from octop_harness.cli.config.schema import CliConfig

        cli_cfg = CliConfig()
        mock_load.return_value = (None, cli_cfg)
        mock_wizard.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["chat"])
        assert result.exit_code == 1


def test_chat_one_shot_calls_agent(tmp_path: Path, monkeypatch: object) -> None:
    """One-shot mode with -p flag calls the agent and prints output."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    mock_message = MagicMock()
    mock_message.content = "Hello from agent!"

    mock_agent = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [mock_message]})

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.HarnessAgent", return_value=mock_agent),
        patch("octop_harness.HarnessAgentConfig"),
    ):
        from octop_harness.cli.config.schema import CliConfig

        mock_load.return_value = (fake_config, CliConfig())
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "-p", "hello"])
        assert result.exit_code == 0
        assert "Hello from agent!" in result.output


def test_chat_one_shot_no_messages(tmp_path: Path, monkeypatch: object) -> None:
    """One-shot mode prints nothing when agent returns no messages."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    mock_agent = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": []})

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.HarnessAgent", return_value=mock_agent),
        patch("octop_harness.HarnessAgentConfig"),
    ):
        from octop_harness.cli.config.schema import CliConfig

        mock_load.return_value = (fake_config, CliConfig())
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "-p", "hello"])
        assert result.exit_code == 0
        assert result.output.strip() == ""


def test_chat_repl_launched_without_prompt(tmp_path: Path, monkeypatch: object) -> None:
    """Without -p flag, the REPL is launched."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.commands.chat._run_repl") as mock_repl,
    ):
        from octop_harness.cli.config.schema import CliConfig

        cli_cfg = CliConfig()
        mock_load.return_value = (fake_config, cli_cfg)
        runner = CliRunner()
        result = runner.invoke(cli, ["chat"])
        assert result.exit_code == 0
        mock_repl.assert_called_once_with(fake_config, cli_cfg.to_dict(), None, None, None)


def test_chat_agent_option_passed_to_repl(tmp_path: Path, monkeypatch: object) -> None:
    """--agent flag is passed through to _run_repl."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.cli.commands.chat._run_repl") as mock_repl,
    ):
        from octop_harness.cli.config.schema import CliConfig

        cli_cfg = CliConfig()
        mock_load.return_value = (fake_config, cli_cfg)
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--agent", "code"])
        assert result.exit_code == 0
        mock_repl.assert_called_once_with(fake_config, cli_cfg.to_dict(), None, None, "code")


def test_chat_model_override(tmp_path: Path, monkeypatch: object) -> None:
    """--model flag is passed through to ChatRequest."""
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

    mock_agent = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": []})

    fake_config = {"providers": {"test": {"base_url": "http://x", "api_key": "k", "models": [{"id": "m"}]}}}

    with (
        patch("octop_harness.cli.commands.chat.load_config") as mock_load,
        patch("octop_harness.HarnessAgent", return_value=mock_agent),
        patch("octop_harness.HarnessAgentConfig"),
        patch("octop_harness.ChatRequest") as mock_req_cls,
    ):
        from octop_harness.cli.config.schema import CliConfig

        mock_load.return_value = (fake_config, CliConfig())
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "-p", "hello", "--model", "openai/gpt-4"])
        assert result.exit_code == 0
        mock_req_cls.assert_called_once_with(messages="hello", model="openai/gpt-4", source="cli")
