"""tests/unit/agents/test_execute_env.py"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

import pytest
from octop_harness.backends import resolve_backend
from octop_harness.backends.workspace import BackendWorkspace

from octop.infra.agents.secret_file.service import submit_secret_content
from octop.infra.agents.workspace.execute_env import inject_agent_execute_env
from octop.infra.db.repos.agents import AgentRow
from octop.infra.utils.env_file import save_env_file
from octop.infra.utils.paths import PathLayout


def _row(agent_id: str = "a1") -> AgentRow:
    return AgentRow(
        id=1,
        agent_id=agent_id,
        user_id=1,
        name="test",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        enabled=1,
        config_json=None,
        last_state=None,
        last_error=None,
        created_at=0,
        updated_at=0,
    )


def test_inject_local_shell_uses_octop_auth_for_new_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    save_env_file(paths.root / "env", {"GLOBAL_KEY": "global"})

    ws = paths.ensure_agent_workspace("agent-1")
    (ws / ".env").write_text("AGENT_KEY=agent\n", encoding="utf-8")

    spec = inject_agent_execute_env(
        {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
        paths=paths,
        row=_row("agent-1"),
        workspace_dir=ws,
        cfg={"system_files_path": ".octop"},
    )
    env = spec["env"]
    assert env["OCTOP_AGENT_ID"] == "agent-1"
    assert (ws / ".octop" / "auth").is_dir()
    assert env["OCTOP_AUTH_DIR"] == str(ws / ".octop" / "auth")
    assert env["OCTOP_CLI_HOME"] == str(ws / ".octop" / "auth" / "cli-home")
    assert env["OCTOP_HOME"] == str(paths.root)
    assert env["OCTOP_SKILLS_DIR"] == str(ws / ".octop" / "skills")
    assert "GLOBAL_KEY" not in env
    assert "AGENT_KEY" not in env
    assert spec["inherit_env"] is True


def test_inject_legacy_layout_keeps_root_octop_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    ws = paths.ensure_agent_workspace("agent-legacy")

    spec = inject_agent_execute_env(
        {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
        paths=paths,
        row=_row("agent-legacy"),
        workspace_dir=ws,
        cfg={},
    )
    assert (ws / ".octop-auth").is_dir()
    assert spec["env"]["OCTOP_AUTH_DIR"] == str(ws / ".octop-auth")
    assert spec["env"]["OCTOP_CLI_HOME"] == str(ws / ".octop-auth" / "cli-home")


def test_inject_keeps_legacy_auth_when_tokens_already_there(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    ws = paths.ensure_agent_workspace("agent-mig")
    legacy = ws / ".octop-auth"
    legacy.mkdir()
    (legacy / "token.json").write_text("{}", encoding="utf-8")

    spec = inject_agent_execute_env(
        {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
        paths=paths,
        row=_row("agent-mig"),
        workspace_dir=ws,
        cfg={"system_files_path": ".octop"},
    )
    assert spec["env"]["OCTOP_AUTH_DIR"] == str(legacy)


def test_inject_composite_default_local_shell(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    ws = paths.ensure_agent_workspace("agent-c")

    spec = inject_agent_execute_env(
        {
            "type": "composite",
            "default": {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
            "routes": {},
        },
        paths=paths,
        row=_row("agent-c"),
        workspace_dir=ws,
        cfg={"system_files_path": ".octop"},
    )
    assert spec["default"]["env"]["OCTOP_AGENT_ID"] == "agent-c"
    assert spec["default"]["env"]["OCTOP_AUTH_DIR"] == str(ws / ".octop" / "auth")
    assert spec["default"]["inherit_env"] is True


def test_inject_scoped_root_uses_agent_facing_auth_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    root = tmp_path / "scoped"
    root.mkdir()
    ws = root / ".octop" / "workspaces" / "agent-s"
    ws.mkdir(parents=True)
    cfg = {
        "system_files_path": ".octop",
        "workspace_dir": "/.octop/workspaces/agent-s",
        "backend": {
            "type": "local_shell",
            "root_dir": str(root),
            "virtual_mode": True,
        },
    }

    spec = inject_agent_execute_env(
        {"type": "local_shell", "root_dir": str(root), "virtual_mode": True},
        paths=paths,
        row=_row("agent-s"),
        workspace_dir=ws,
        cfg=cfg,
    )
    env = spec["env"]
    assert (ws / ".octop" / "auth").is_dir()
    assert env["OCTOP_AUTH_DIR"] == "/.octop/workspaces/agent-s/.octop/auth"
    assert env["OCTOP_SKILLS_DIR"] == "/.octop/workspaces/agent-s/.octop/skills"
    assert "OCTOP_CLI_HOME" not in env


def test_inject_docker_only_sets_platform_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    paths = PathLayout(tmp_path)
    paths.ensure_root()
    save_env_file(paths.root / "env", {"GLOBAL_KEY": "global"})
    ws = paths.ensure_agent_workspace("agent-2")

    spec = inject_agent_execute_env(
        {"type": "docker"},
        paths=paths,
        row=_row("agent-2"),
        workspace_dir=ws,
        cfg={"system_files_path": ".octop"},
    )
    env = spec["env"]
    assert env["OCTOP_AGENT_ID"] == "agent-2"
    assert env["OCTOP_AUTH_DIR"] == str(ws / ".octop" / "auth")
    assert "GLOBAL_KEY" not in env
    assert "OCTOP_CLI_HOME" not in env


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only per-command shell environment")
@pytest.mark.asyncio
async def test_cli_default_home_reads_only_selected_expert_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "platform"))
    host_home = tmp_path / "host home"
    host_config = host_home / ".config"
    host_config.mkdir(parents=True)
    host_token = host_config / "existing-token"
    host_token.write_text("host credentials", encoding="utf-8")
    monkeypatch.setenv("HOME", str(host_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(host_config))
    paths = PathLayout(tmp_path / "platform")
    cli = tmp_path / "fake cli.py"
    cli.write_text(
        "import json, os\n"
        "from pathlib import Path\n"
        "home = Path.home()\n"
        "legacy = json.loads((home / '.example' / 'credentials').read_text())\n"
        "xdg = json.loads((Path(os.environ['XDG_CONFIG_HOME']) / 'example' / 'config.json').read_text())\n"
        "print(json.dumps({'home': str(home), 'account': legacy['account'], "
        "'xdg_account': xdg['account'], 'authenticated': bool(legacy['token'] and xdg['token']), "
        "'octop_home': os.environ['OCTOP_HOME']}))\n",
        encoding="utf-8",
    )
    command = (
        'env HOME="$OCTOP_CLI_HOME" XDG_CONFIG_HOME="$OCTOP_CLI_HOME/.config" '
        f"{shlex.quote(sys.executable)} {shlex.quote(str(cli))}"
    )
    for agent_id in ("expert one", "expert two"):
        ws = paths.ensure_agent_workspace(agent_id)
        spec = inject_agent_execute_env(
            {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
            paths=paths,
            row=_row(agent_id),
            workspace_dir=ws,
            cfg={"system_files_path": ".octop"},
        )
        backend = resolve_backend(spec, workspace_dir=ws, system_files_path=".octop")
        workspace = BackendWorkspace(backend, ws, system_files_path=".octop")
        content = json.dumps({"account": agent_id, "token": "synthetic-private-token"})
        for name in ("cli-home/.example/credentials", "cli-home/.config/example/config.json"):
            await submit_secret_content(workspace, raw_path=name, content=content)
        result = await asyncio.to_thread(backend.execute, command)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {
            "home": str(ws / ".octop" / "auth" / "cli-home"),
            "account": agent_id,
            "xdg_account": agent_id,
            "authenticated": True,
            "octop_home": str(paths.root),
        }
        assert "synthetic-private-token" not in command + result.output
        ordinary = await asyncio.to_thread(
            backend.execute,
            f"{shlex.quote(sys.executable)} -c "
            + shlex.quote("from pathlib import Path; print(Path.home())"),
        )
        assert ordinary.exit_code == 0
        assert ordinary.output.strip() == str(host_home)
    assert os.environ["HOME"] == str(host_home)
    assert os.environ["XDG_CONFIG_HOME"] == str(host_config)
    assert host_token.read_text(encoding="utf-8") == "host credentials"
