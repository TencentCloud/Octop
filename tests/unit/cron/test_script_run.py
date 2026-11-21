"""Host and sandbox execution for cron scripts."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.cron.script_run import SCRIPT_TIMEOUT_SECONDS, ScriptRunError, run_cron_script


class _Workspace:
    def __init__(self, root: Path) -> None:
        self.workspace_dir = root
        self.backend = object()

    async def aread_text(self, path: str) -> str | None:
        file = self.workspace_dir / path
        if not file.is_file():
            return None
        return file.read_text(encoding="utf-8")

    async def aexists(self, path: str) -> bool:
        return (self.workspace_dir / path).is_file()


@pytest.mark.asyncio
async def test_inline_python_prints_stdout(tmp_path: Path) -> None:
    result = await run_cron_script(
        lang="python",
        source="inline",
        body="print('cron-ok')",
        path=None,
        workspace=_Workspace(tmp_path),
        backend_spec={"type": "filesystem"},
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "cron-ok"


@pytest.mark.asyncio
async def test_file_script_runs_in_the_workspace(tmp_path: Path) -> None:
    script = tmp_path / "jobs" / "hello.py"
    script.parent.mkdir()
    script.write_text("print('from-file')\n", encoding="utf-8")
    result = await run_cron_script(
        lang="python",
        source="file",
        body="",
        path="jobs/hello.py",
        workspace=_Workspace(tmp_path),
        backend_spec={"type": "filesystem"},
    )
    assert result.exit_code == 0
    assert "from-file" in result.stdout


@pytest.mark.asyncio
async def test_missing_workspace_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ScriptRunError) as exc:
        await run_cron_script(
            lang="python",
            source="file",
            body="",
            path="missing.py",
            workspace=_Workspace(tmp_path),
            backend_spec={"type": "filesystem"},
        )
    assert exc.value.code == "unreadable"


@pytest.mark.asyncio
async def test_failed_script_returns_stderr(tmp_path: Path) -> None:
    result = await run_cron_script(
        lang="python",
        source="inline",
        body="import sys; sys.stderr.write('boom'); sys.exit(3)",
        path=None,
        workspace=_Workspace(tmp_path),
        backend_spec={"type": "filesystem"},
    )
    assert result.exit_code == 3
    assert "boom" in result.stderr
    assert not list(tmp_path.glob(".octop-cron-*"))


@pytest.mark.asyncio
async def test_escaped_path_is_not_executed_in_place(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"cron-outside-{tmp_path.name}.py"
    outside.write_text("print('leaked')\n", encoding="utf-8")
    workspace = _Workspace(tmp_path)

    async def _refuse(path: str) -> str:
        if ".." in path.replace("\\", "/").split("/"):
            raise OSError(path)
        return await _Workspace.aread_text(workspace, path)

    workspace.aread_text = _refuse  # type: ignore[method-assign]
    try:
        with pytest.raises(ScriptRunError) as exc:
            await run_cron_script(
                lang="python",
                source="file",
                body="",
                path=f"../{outside.name}",
                workspace=workspace,
                backend_spec={"type": "filesystem"},
            )
    finally:
        outside.unlink(missing_ok=True)
    assert exc.value.code == "unreadable"


@pytest.mark.asyncio
async def test_remote_storage_reads_then_runs_in_a_temp_dir(tmp_path: Path) -> None:
    decoy = tmp_path / "jobs"
    decoy.mkdir()
    (decoy / "hello.py").write_text("print('local-decoy')\n", encoding="utf-8")
    workspace = _Workspace(tmp_path)

    async def _read(path: str) -> str:
        assert path == "jobs/hello.py"
        return "print('from-storage')\n"

    workspace.aread_text = _read  # type: ignore[method-assign]
    result = await run_cron_script(
        lang="python",
        source="file",
        body="",
        path="jobs/hello.py",
        workspace=workspace,
        backend_spec={"type": "s3"},
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "from-storage"


@pytest.mark.asyncio
async def test_host_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octop.infra.cron.script_run.SCRIPT_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(ScriptRunError) as exc:
        await run_cron_script(
            lang="python",
            source="inline",
            body="import time; time.sleep(5)",
            path=None,
            workspace=_Workspace(tmp_path),
            backend_spec={"type": "filesystem"},
        )
    assert exc.value.code == "timeout"


@pytest.mark.asyncio
async def test_missing_powershell_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("octop.infra.cron.script_run.shutil.which", lambda _name: None)
    with pytest.raises(ScriptRunError) as exc:
        await run_cron_script(
            lang="powershell",
            source="inline",
            body="Write-Output 'nope'",
            path=None,
            workspace=_Workspace(tmp_path),
            backend_spec={"type": "filesystem"},
        )
    assert exc.value.code == "interpreter_missing"


@pytest.mark.asyncio
async def test_bash_echo_when_present(tmp_path: Path) -> None:
    if shutil.which("bash") is None and shutil.which("sh") is None:
        pytest.skip("no bash or sh on this host")
    result = await run_cron_script(
        lang="bash",
        source="inline",
        body="echo cron-bash",
        path=None,
        workspace=_Workspace(tmp_path),
        backend_spec={"type": "filesystem"},
    )
    assert result.exit_code == 0
    assert "cron-bash" in result.stdout


class _Sandbox:
    def __init__(self, *, exit_code: int = 0, output: str = "sandbox-ok\n") -> None:
        self.written: dict[str, str] = {}
        self.deleted: list[str] = []
        self.commands: list[str] = []
        self._exit_code = exit_code
        self._output = output
        self.backend = self

    def execute(self, command: str, *, timeout: int) -> SimpleNamespace:
        assert timeout == SCRIPT_TIMEOUT_SECONDS
        self.commands.append(command)
        return SimpleNamespace(exit_code=self._exit_code, output=self._output)

    async def amkdir(self, path: str) -> None:
        assert path == ".octop/cron-scripts"

    async def awrite_text(self, path: str, body: str) -> None:
        self.written[path] = body

    async def adelete(self, path: str) -> None:
        self.deleted.append(path)

    async def aexists(self, path: str) -> bool:
        return path in self.written


@pytest.mark.asyncio
async def test_sandbox_inline_python_is_written_then_deleted() -> None:
    sandbox = _Sandbox()
    result = await run_cron_script(
        lang="python",
        source="inline",
        body="print('sandbox-ok')",
        path=None,
        workspace=sandbox,
        backend_spec={"type": "docker"},
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "sandbox-ok"
    assert len(sandbox.written) == 1
    path = next(iter(sandbox.written))
    assert path.startswith(".octop/cron-scripts/")
    assert path.endswith(".py")
    assert sandbox.commands[0].startswith("python3 ")
    assert path in sandbox.commands[0]
    assert sandbox.deleted == [path]


@pytest.mark.asyncio
async def test_sandbox_maps_timeout_and_missing_interpreter() -> None:
    with pytest.raises(ScriptRunError) as timeout:
        await run_cron_script(
            lang="bash",
            source="inline",
            body="echo hi",
            path=None,
            workspace=_Sandbox(exit_code=124, output=""),
            backend_spec={"type": "docker"},
        )
    assert timeout.value.code == "timeout"
    with pytest.raises(ScriptRunError) as missing:
        await run_cron_script(
            lang="python",
            source="inline",
            body="print(1)",
            path=None,
            workspace=_Sandbox(exit_code=127, output=""),
            backend_spec={"type": "opensandbox"},
        )
    assert missing.value.code == "interpreter_missing"


@pytest.mark.asyncio
async def test_sandbox_missing_file_does_not_execute() -> None:
    sandbox = _Sandbox()

    async def _missing(_path: str) -> bool:
        return False

    sandbox.aexists = _missing  # type: ignore[method-assign]
    with pytest.raises(ScriptRunError) as exc:
        await run_cron_script(
            lang="python",
            source="file",
            body="",
            path="jobs/missing.py",
            workspace=sandbox,
            backend_spec={"type": "docker"},
        )
    assert exc.value.code == "unreadable"
    assert sandbox.commands == []
