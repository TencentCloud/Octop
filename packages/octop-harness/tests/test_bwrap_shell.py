"""Tests for bubblewrap jail helpers and shell backends."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from octop_harness.backends import resolve_backend
from octop_harness.backends.bwrap_shell import (
    BubbledLocalShellBackend,
    build_bwrap_argv,
    can_use_bubbled_shell,
    resolve_bubbled_bwrap,
)
from octop_harness.backends.local_shell import (
    HarnessLocalShellBackend,
    is_host_root,
    map_virtual_abs_path,
    map_virtual_paths_in_env,
    present_host_paths_in_output,
    rewrite_virtual_paths_in_command,
)

_BWRAP = "/usr/bin/bwrap"


def test_is_host_root_slash() -> None:
    assert is_host_root("/")
    assert is_host_root(Path("/"))


def test_resolve_bubbled_bwrap_gates(tmp_path: Path) -> None:
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=True,
            root_dir=tmp_path,
            platform="linux",
            bwrap_path=_BWRAP,
        )
        == _BWRAP
    )
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=True,
            root_dir=tmp_path,
            platform="darwin",
            bwrap_path=_BWRAP,
        )
        is None
    )
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=False,
            root_dir=tmp_path,
            platform="linux",
            bwrap_path=_BWRAP,
        )
        is None
    )
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=True,
            root_dir="/",
            platform="linux",
            bwrap_path=_BWRAP,
        )
        is None
    )
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=True,
            root_dir=tmp_path,
            platform="linux",
            bwrap_path=None,
        )
        is None
    )


def test_can_use_bubbled_shell_gates(tmp_path: Path) -> None:
    assert can_use_bubbled_shell(
        virtual_mode=True,
        root_dir=tmp_path,
        platform="linux",
        bwrap_path=_BWRAP,
    )
    assert not can_use_bubbled_shell(
        virtual_mode=True,
        root_dir="/",
        platform="linux",
        bwrap_path=_BWRAP,
    )


def test_environment_host_root_does_not_enable_bwrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS_TEST_ROOT", "/")
    assert (
        resolve_bubbled_bwrap(
            virtual_mode=True,
            root_dir="$HARNESS_TEST_ROOT",
            platform="linux",
            bwrap_path=_BWRAP,
        )
        is None
    )


def test_resolve_backend_uses_bubbled_only_when_jail_available(tmp_path: Path) -> None:
    with patch(
        "octop_harness.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=_BWRAP,
    ):
        bubbled = resolve_backend({"type": "local_shell", "root_dir": str(tmp_path), "virtual_mode": True})
    assert isinstance(bubbled, BubbledLocalShellBackend)
    assert bubbled._bwrap_path == _BWRAP

    with patch(
        "octop_harness.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        plain = resolve_backend({"type": "local_shell", "root_dir": str(tmp_path), "virtual_mode": True})
    assert isinstance(plain, HarnessLocalShellBackend)
    assert not isinstance(plain, BubbledLocalShellBackend)


def test_resolve_backend_host_root_is_harness_not_bubbled() -> None:
    with patch(
        "octop_harness.backends.bwrap_shell.resolve_bubbled_bwrap",
        return_value=None,
    ):
        backend = resolve_backend({"type": "local_shell", "root_dir": "/", "virtual_mode": True})
    assert isinstance(backend, HarnessLocalShellBackend)
    assert not isinstance(backend, BubbledLocalShellBackend)


def test_build_bwrap_argv_shape(tmp_path: Path) -> None:
    argv = build_bwrap_argv(
        bwrap=_BWRAP,
        root_dir=tmp_path,
        command="echo hi",
    )
    assert argv[0] == _BWRAP
    assert "--new-session" in argv
    assert "--unshare-pid" in argv
    assert "--unshare-ipc" in argv
    assert "--unshare-uts" in argv
    assert "--bind" in argv
    bind_i = argv.index("--bind")
    assert argv[bind_i + 1] == str(tmp_path.resolve())
    assert argv[bind_i + 2] == "/"
    assert "--ro-bind" in argv or "--ro-bind-try" in argv
    assert "--tmpfs" in argv
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"
    assert "--chdir" in argv
    assert argv[argv.index("--chdir") + 1] == "/"
    assert argv[-3:] == ["/bin/sh", "-c", "echo hi"]


def test_build_bwrap_argv_uses_virtual_workspace_cwd(tmp_path: Path) -> None:
    argv = build_bwrap_argv(
        bwrap=_BWRAP,
        root_dir=tmp_path,
        command="pwd",
        work_dir="/.octop/workspaces/AGENT1",
    )
    assert argv[argv.index("--chdir") + 1] == "/.octop/workspaces/AGENT1"


def test_build_bwrap_argv_extra_binds(tmp_path: Path) -> None:
    skills = tmp_path / "ws" / "skills"
    skills.mkdir(parents=True)
    argv = build_bwrap_argv(
        bwrap=_BWRAP,
        root_dir=tmp_path / "root",
        command="true",
        extra_binds=[(str(skills), "/skills")],
    )
    pairs = list(zip(argv, argv[1:], argv[2:], strict=False))
    assert any(a == "--bind" and c == "/skills" for a, _b, c in pairs)


def test_execute_uses_bwrap_on_linux(tmp_path: Path) -> None:
    backend = BubbledLocalShellBackend(
        root_dir=tmp_path,
        bwrap_path=_BWRAP,
        virtual_mode=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "ok\n"
    fake.stderr = ""
    with patch("octop_harness.backends.bwrap_shell.subprocess.run", return_value=fake) as run:
        result = backend.execute("echo ok")
    assert result.exit_code == 0
    assert "ok" in result.output
    argv = run.call_args.args[0]
    assert argv[0] == _BWRAP
    assert run.call_args.kwargs.get("shell") is False


def test_execute_injects_process_env_and_workspace_dotenv(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("FROM_ADMIN", "yes")  # type: ignore[attr-defined]
    (tmp_path / ".env").write_text("FROM_AGENT=1\n", encoding="utf-8")
    backend = BubbledLocalShellBackend(
        root_dir=tmp_path,
        bwrap_path=_BWRAP,
        workspace_dir=tmp_path,
        virtual_mode=True,
        env={"EXTRA": "x"},
    )
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "ok\n"
    fake.stderr = ""
    with patch("octop_harness.backends.bwrap_shell.subprocess.run", return_value=fake) as run:
        backend.execute("echo ok")
    env = run.call_args.kwargs["env"]
    assert env["FROM_ADMIN"] == "yes"
    assert env["FROM_AGENT"] == "1"
    assert env["EXTRA"] == "x"


@pytest.mark.asyncio
async def test_write_env_file_reaches_execute_when_host_dotenv_missing(tmp_path: Path) -> None:
    """write_env_file via BackendWorkspace must feed execute even if host .env is absent."""
    from deepagents.backends import FilesystemBackend

    from octop_harness.backends.workspace import BackendWorkspace
    from octop_harness.builtin.tools.env_file import build_env_file_tools
    from octop_harness.runtime_env import backend_workspace_dotenv_reader

    host_ws = tmp_path / "host"
    remote = tmp_path / "remote"
    host_ws.mkdir()
    remote.mkdir()
    workspace = BackendWorkspace(
        FilesystemBackend(root_dir=str(remote), virtual_mode=True),
        remote,
    )
    write = next(t for t in build_env_file_tools(workspace) if t.name == "write_env_file")
    await write.ainvoke({"updates": {"FROM_WRITE": "1"}})

    backend = HarnessLocalShellBackend(
        root_dir=tmp_path / "jail",
        workspace_dir=host_ws,
        virtual_mode=True,
        inherit_env=False,
    )
    backend.set_workspace_dotenv_reader(backend_workspace_dotenv_reader(workspace))
    with patch.object(
        LocalShellBackend,
        "execute",
        return_value=ExecuteResponse(output="ok", exit_code=0, truncated=False),
    ):
        backend.execute("echo ok")
    assert backend._env["FROM_WRITE"] == "1"
    assert not (host_ws / ".env").exists()


def test_execute_falls_back_when_bwrap_missing_binary(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generated.mkdir()
    backend = BubbledLocalShellBackend(
        root_dir=tmp_path,
        bwrap_path=_BWRAP,
        virtual_mode=True,
        env={"PATH": "/bin"},
    )
    with (
        patch(
            "octop_harness.backends.bwrap_shell.subprocess.run",
            side_effect=FileNotFoundError("bwrap"),
        ),
        patch.object(
            backend,
            "_execute_on_host",
            return_value=ExecuteResponse(output="ok", exit_code=0, truncated=False),
        ) as host_exec,
    ):
        result = backend.execute("python /generated/run.py")
    assert result.exit_code == 0
    assert backend._bwrap_path is None
    assert host_exec.call_args.args[0] == f"python {tmp_path.resolve()}/generated/run.py"


@pytest.mark.skipif(os.name != "posix", reason="fallback integration uses POSIX shell")
def test_bwrap_start_failure_executes_translated_host_command(tmp_path: Path) -> None:
    workspace = tmp_path / ".octop" / "workspaces" / "FALLBACK1"
    workspace.mkdir(parents=True)
    (workspace / "probe.sh").write_text("printf fallback-ok", encoding="utf-8")
    backend = BubbledLocalShellBackend(
        root_dir=tmp_path,
        workspace_dir=workspace,
        bwrap_path="/missing/bwrap",
        virtual_mode=True,
        inherit_env=False,
    )
    real_run = subprocess.run

    def fail_bwrap_only(
        command: str | list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(command, list):
            raise FileNotFoundError("bwrap")
        return cast(subprocess.CompletedProcess[str], real_run(command, **kwargs))

    with patch("octop_harness.backends.bwrap_shell.subprocess.run", side_effect=fail_bwrap_only):
        result = backend.execute("sh /.octop/workspaces/FALLBACK1/probe.sh")
    assert result.exit_code == 0
    assert "fallback-ok" in result.output
    assert backend._bwrap_path is None


def test_skill_extra_binds_when_workspace_differs(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    ws = tmp_path / "ws"
    (ws / "skills").mkdir(parents=True)
    (ws / "_builtin_skills").mkdir(parents=True)
    backend = BubbledLocalShellBackend(
        root_dir=root,
        bwrap_path=_BWRAP,
        workspace_dir=ws,
        virtual_mode=True,
        env={"PATH": "/bin"},
    )
    binds = backend._skill_extra_binds()
    assert (str(ws / "skills"), "/skills") in binds
    assert (str(ws / "_builtin_skills"), "/_builtin_skills") in binds


def test_skill_extra_binds_prefers_system_files_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    ws = tmp_path / "ws"
    (ws / "skills").mkdir(parents=True)
    (ws / ".octop" / "skills").mkdir(parents=True)
    (ws / ".octop" / "_builtin_skills").mkdir(parents=True)
    backend = BubbledLocalShellBackend(
        root_dir=root,
        bwrap_path=_BWRAP,
        workspace_dir=ws,
        virtual_mode=True,
        env={"PATH": "/bin"},
        system_files_path=".octop",
    )
    binds = backend._skill_extra_binds()
    assert (str(ws / ".octop" / "skills"), "/skills") in binds
    assert (str(ws / ".octop" / "_builtin_skills"), "/_builtin_skills") in binds


def test_map_virtual_abs_path_requires_mapping_evidence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    workspace = root / ".octop" / "workspaces" / "QH53B8"
    workspace.mkdir(parents=True)

    virtual_script = "/.octop/workspaces/QH53B8/scripts/run.py"
    assert map_virtual_abs_path(
        virtual_script,
        root,
        workspace_dir=workspace,
    ) == str(workspace / "scripts" / "run.py")
    assert map_virtual_abs_path("/path/without/evidence", root) == "/path/without/evidence"
    assert map_virtual_abs_path("/usr/bin/python3", root) == "/usr/bin/python3"
    assert map_virtual_abs_path("/usr/harness-missing-tool", root) == "/usr/harness-missing-tool"
    assert map_virtual_abs_path(str(workspace / "run.py"), root) == str(workspace / "run.py")
    assert map_virtual_abs_path(virtual_script, "/") == virtual_script


def test_rewrite_command_handles_spaces_urls_globs_and_host_paths(tmp_path: Path) -> None:
    root = tmp_path / "home with spaces"
    workspace = root / ".octop" / "workspaces" / "QH53B8"
    generated = workspace / "generated"
    generated.mkdir(parents=True)
    virtual = "/.octop/workspaces/QH53B8"

    rewritten = rewrite_virtual_paths_in_command(
        f"curl https://example.com/a -o {virtual}/generated/out.txt && cat {virtual}/generated/*.txt && ls /usr/bin",
        root,
        workspace_dir=workspace,
    )

    quoted_root = shlex.quote(str(root.resolve()))
    assert "https://example.com/a" in rewritten
    assert f"{quoted_root}/.octop/workspaces/QH53B8/generated/out.txt" in rewritten
    assert f"{quoted_root}/.octop/workspaces/QH53B8/generated/*.txt" in rewritten
    assert "ls /usr/bin" in rewritten


@pytest.mark.skipif(os.name != "posix", reason="nested quote behavior uses POSIX shell")
def test_rewrite_preserves_nested_shell_quotes(tmp_path: Path) -> None:
    root = tmp_path / "home with spaces"
    workspace = root / ".octop" / "workspaces" / "QUOTES1"
    workspace.mkdir(parents=True)
    (workspace / "value.txt").write_text("nested-ok", encoding="utf-8")
    backend = HarnessLocalShellBackend(
        root_dir=root,
        workspace_dir=workspace,
        virtual_mode=True,
        inherit_env=False,
    )
    virtual = "/.octop/workspaces/QUOTES1/value.txt"
    single_outer = backend.execute(
        f"""{shlex.quote(sys.executable)} -c 'from pathlib import Path; print(Path("{virtual}").read_text())'"""
    )
    double_outer = backend.execute(
        f'''{shlex.quote(sys.executable)} -c "from pathlib import Path; print(Path('{virtual}').read_text())"'''
    )
    assert single_outer.exit_code == 0
    assert double_outer.exit_code == 0
    assert "nested-ok" in single_outer.output
    assert "nested-ok" in double_outer.output


def test_map_virtual_paths_in_env_maps_path_lists_only_when_credible(tmp_path: Path) -> None:
    root = tmp_path / "home"
    workspace = root / ".octop" / "workspaces" / "QH53B8"
    skills = workspace / ".octop" / "skills"
    custom_bin = workspace / "bin"
    skills.mkdir(parents=True)
    custom_bin.mkdir()

    mapped = map_virtual_paths_in_env(
        {
            "OCTOP_SKILLS_DIR": "/.octop/workspaces/QH53B8/.octop/skills",
            "PYTHONPATH": f"/.octop/workspaces/QH53B8/lib{os.pathsep}/usr/lib",
            "PATH": f"/usr/bin{os.pathsep}/.octop/workspaces/QH53B8/bin",
            "URL": "https://example.com/a",
            "OCTOP_HOME": str(root),
        },
        root,
        workspace_dir=workspace,
    )

    assert mapped["OCTOP_SKILLS_DIR"] == str(skills)
    assert mapped["PYTHONPATH"] == f"{workspace / 'lib'}{os.pathsep}/usr/lib"
    assert mapped["PATH"] == f"/usr/bin{os.pathsep}{custom_bin}"
    assert mapped["URL"] == "https://example.com/a"
    assert mapped["OCTOP_HOME"] == str(root)


@pytest.mark.skipif(os.name != "posix", reason="user report uses POSIX shell path semantics")
def test_scoped_workspace_skill_script_executes_without_bwrap(tmp_path: Path) -> None:
    """Regression probe for Octop's reported macOS scoped-workspace failure."""
    root = tmp_path / "home with spaces"
    workspace = root / ".octop" / "workspaces" / "QH53B8"
    skill = workspace / ".octop" / "skills" / "commind-data-fetch"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "fetch_gateway.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "print(Path.cwd().name)\n"
        "print(Path(os.environ['OCTOP_SKILLS_DIR']).name)\n",
        encoding="utf-8",
    )
    (workspace / "workspace_probe.py").write_text("print('workspace-cwd')\n", encoding="utf-8")

    backend = HarnessLocalShellBackend(
        root_dir=root,
        workspace_dir=workspace,
        virtual_mode=True,
        inherit_env=False,
        env={"OCTOP_SKILLS_DIR": "/.octop/workspaces/QH53B8/.octop/skills"},
    )
    virtual_skill = "/.octop/workspaces/QH53B8/.octop/skills/commind-data-fetch"
    assert backend.read(f"{virtual_skill}/SKILL.md").error is not None
    (skill / "SKILL.md").write_text("# data fetch\n", encoding="utf-8")
    assert backend.read(f"{virtual_skill}/SKILL.md").error is None

    listed = backend.execute("ls /.octop/workspaces/QH53B8/.octop/skills")
    assert listed.exit_code == 0
    assert "commind-data-fetch" in listed.output

    via_env = backend.execute(
        f'{shlex.quote(sys.executable)} "$OCTOP_SKILLS_DIR/commind-data-fetch/scripts/fetch_gateway.py"'
    )
    assert via_env.exit_code == 0
    assert "QH53B8" in via_env.output
    assert "skills" in via_env.output

    via_virtual_cd = backend.execute(f"cd {virtual_skill} && {shlex.quote(sys.executable)} scripts/fetch_gateway.py")
    assert via_virtual_cd.exit_code == 0
    assert "commind-data-fetch" in via_virtual_cd.output

    relative = backend.execute(f"{shlex.quote(sys.executable)} workspace_probe.py")
    assert relative.exit_code == 0
    assert "workspace-cwd" in relative.output

    pwd = backend.execute("pwd")
    assert pwd.exit_code == 0
    assert "/.octop/workspaces/QH53B8" in pwd.output
    assert str(root) not in pwd.output


@pytest.mark.skipif(os.name != "posix", reason="reported probe uses POSIX shell path semantics")
def test_reported_resolve_backend_probe_has_one_path_semantics(tmp_path: Path) -> None:
    """Mirror the Octop report through the public backend factory."""
    root = tmp_path / "home"
    workspace = root / ".octop" / "workspaces" / "REPORT1"
    skill = workspace / ".octop" / "skills" / "commind-data-fetch"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# probe\n", encoding="utf-8")
    (scripts / "fetch_gateway.py").write_text("print('script-ok')\n", encoding="utf-8")

    with patch("octop_harness.backends.bwrap_shell.shutil.which", return_value=None):
        backend = resolve_backend(
            {
                "type": "local_shell",
                "virtual_mode": True,
                "root_dir": str(root),
            },
            workspace_dir=workspace,
            system_files_path=".octop",
        )

    target = getattr(backend, "default", backend)
    assert isinstance(target, HarnessLocalShellBackend)
    assert not isinstance(target, BubbledLocalShellBackend)

    virtual_skill = "/.octop/workspaces/REPORT1/.octop/skills/commind-data-fetch"
    assert backend.read(f"{virtual_skill}/SKILL.md").error is None
    listed = backend.execute("ls /.octop/workspaces/REPORT1/.octop/skills")
    assert listed.exit_code == 0
    assert "commind-data-fetch" in listed.output
    executed = backend.execute(f"cd {virtual_skill} && {shlex.quote(sys.executable)} scripts/fetch_gateway.py --help")
    assert executed.exit_code == 0
    assert "script-ok" in executed.output


@pytest.mark.skipif(os.name != "posix", reason="tilde root is a POSIX runtime configuration")
def test_tilde_root_dir_executes_from_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    workspace = tmp_path / ".octop" / "workspaces" / "TILDE1"
    workspace.mkdir(parents=True)
    (workspace / "probe.sh").write_text("printf tilde-ok", encoding="utf-8")
    backend = HarnessLocalShellBackend(
        root_dir="~",
        workspace_dir=workspace,
        virtual_mode=True,
        inherit_env=False,
    )
    result = backend.execute("sh /.octop/workspaces/TILDE1/probe.sh")
    assert result.exit_code == 0
    assert "tilde-ok" in result.output


@pytest.mark.skipif(os.name != "posix", reason="environment root is a POSIX configuration")
def test_environment_variable_root_dir_is_expanded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCOPED_ROOT", str(tmp_path))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "probe.sh").write_text("printf env-root-ok", encoding="utf-8")
    backend = HarnessLocalShellBackend(
        root_dir="$SCOPED_ROOT",
        workspace_dir=workspace,
        virtual_mode=True,
        inherit_env=False,
    )
    result = backend.execute("sh /workspace/probe.sh")
    assert result.exit_code == 0
    assert "env-root-ok" in result.output


def test_host_root_and_non_virtual_backends_do_not_rewrite(
    tmp_path: Path,
) -> None:
    command = "python /virtual/run.py"
    host_root = HarnessLocalShellBackend(
        root_dir="/",
        workspace_dir=tmp_path,
        virtual_mode=True,
        inherit_env=False,
    )
    non_virtual = HarnessLocalShellBackend(
        root_dir=tmp_path,
        workspace_dir=tmp_path,
        virtual_mode=False,
        inherit_env=False,
    )
    with patch.object(
        HarnessLocalShellBackend,
        "_execute_on_host",
        return_value=ExecuteResponse(output="ok", exit_code=0, truncated=False),
    ) as execute:
        host_root.execute(command)
        assert execute.call_args.args[0] == command
        non_virtual.execute(command)
        assert execute.call_args.args[0] == command


def test_present_host_paths_in_output_uses_agent_facing_form(tmp_path: Path) -> None:
    root = tmp_path / "home"
    workspace = root / ".octop" / "workspaces" / "QH53B8"
    output = f"cwd={workspace}\nsimilar={root}-backup\n"
    assert present_host_paths_in_output(output, root) == (f"cwd=/.octop/workspaces/QH53B8\nsimilar={root}-backup\n")
