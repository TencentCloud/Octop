"""Tests for the Docker sandbox backend (mocked docker SDK — no daemon required)."""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.backends import resolve_backend, spec_supports_execution


def _tar_bytes(arcname: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=arcname)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def mock_docker() -> Any:
    """Patch ``docker.from_env`` and return (module_mock, client, container)."""
    container = MagicMock()
    container.id = "abc123def456"
    container.status = "running"
    container.exec_run.return_value = (0, b"ok\n")
    container.put_archive.return_value = True
    container.get_archive.return_value = (iter([_tar_bytes("SOUL.md", b"hello")]), {"name": "x"})

    docker_mod = MagicMock()
    docker_mod.errors = MagicMock()
    docker_mod.errors.NotFound = type("NotFound", (Exception,), {})
    docker_mod.errors.ImageNotFound = type("ImageNotFound", (Exception,), {})
    docker_mod.errors.APIError = type("APIError", (Exception,), {})
    docker_mod.errors.DockerException = type("DockerException", (Exception,), {})

    client = MagicMock()
    client.containers.run.return_value = container
    client.containers.get.side_effect = docker_mod.errors.NotFound("missing")
    client.ping.return_value = True
    client.images.get.return_value = MagicMock()
    client.volumes.create.return_value = MagicMock()
    client.api.exec_create.return_value = {"Id": "exec-default"}
    client.api.exec_start.return_value = b"ok\n"
    client.api.exec_inspect.return_value = {"ExitCode": 0, "Pid": 1, "Running": False}
    docker_mod.from_env.return_value = client

    with patch.dict("sys.modules", {"docker": docker_mod}):
        yield docker_mod, client, container


class TestSpecSupportsExecution:
    def test_docker_string(self) -> None:
        assert spec_supports_execution("docker") is True

    def test_docker_dict(self) -> None:
        assert spec_supports_execution({"type": "docker", "image": "python:3.12-slim"}) is True

    def test_composite_with_docker_default(self) -> None:
        assert spec_supports_execution({"type": "composite", "default": {"type": "docker"}}) is True


class TestMissingDependency:
    def test_import_error_mentions_extra(self, tmp_path: Path) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "docker" or name.startswith("docker."):
                raise ImportError("No module named docker")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_fake_import),
            pytest.raises(ImportError, match=r"octop-harness\[docker\]"),
        ):
            resolve_backend({"type": "docker"}, workspace_dir=tmp_path)


class TestResolveAndLifecycle:
    def test_resolve_starts_container(self, tmp_path: Path, mock_docker: Any) -> None:
        _docker_mod, client, container = mock_docker
        backend = resolve_backend(
            {
                "type": "docker",
                "image": "python:3.12-slim",
                "allow_network": False,
                "agent_id": "lifecycle1",
            },
            workspace_dir=tmp_path,
        )
        assert backend.id.startswith("docker:")
        client.containers.run.assert_called_once()
        kwargs = client.containers.run.call_args.kwargs
        assert kwargs["image"] == "python:3.12-slim"
        expected_root = str(tmp_path.resolve())
        assert kwargs["working_dir"] == expected_root
        assert kwargs["network_mode"] == "none"
        assert kwargs["name"] == "sandbox_agent_lifecycle1"
        # No auto volume — container FS only; user mounts are opt-in.
        assert "volumes" not in kwargs or not kwargs["volumes"]
        assert getattr(backend, "sandbox_fs", False) is True
        assert backend.previewable is False
        assert backend._workspace_root == expected_root

        result = backend.execute("echo hi")
        assert result.exit_code == 0
        assert "ok" in result.output
        client.api.exec_create.assert_called()
        exec_kwargs = client.api.exec_create.call_args.kwargs
        passed_env = exec_kwargs.get("environment") or {}
        assert "PATH" in passed_env
        assert "HOME" in passed_env

        backend.close()
        # Persistent sandbox: close must not stop/remove the container.
        container.stop.assert_not_called()
        container.remove.assert_not_called()

    def test_execute_env_is_filtered_not_full_host(
        self, tmp_path: Path, mock_docker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOST_SECRET", "nope")
        _docker_mod, client, _container = mock_docker
        backend = resolve_backend(
            {
                "type": "docker",
                "environment": {"TAVILY_API_KEY": "tvly"},
            },
            workspace_dir=tmp_path,
        )
        backend.execute("true")
        env = client.api.exec_create.call_args.kwargs["environment"]
        assert env["TAVILY_API_KEY"] == "tvly"
        assert "HOST_SECRET" not in env
        assert env["PATH"]
        backend.close()

    def test_execute_rereads_environment_file(self, tmp_path: Path, mock_docker: Any) -> None:
        _docker_mod, client, _container = mock_docker
        env_file = tmp_path / "global.env"
        env_file.write_text("ADMIN_KEY=one\n", encoding="utf-8")
        backend = resolve_backend(
            {"type": "docker", "environment_file": str(env_file)},
            workspace_dir=tmp_path,
        )
        backend.execute("true")
        env = client.api.exec_create.call_args.kwargs["environment"]
        assert env["ADMIN_KEY"] == "one"
        env_file.write_text("ADMIN_KEY=two\n", encoding="utf-8")
        backend.execute("true")
        env = client.api.exec_create.call_args.kwargs["environment"]
        assert env["ADMIN_KEY"] == "two"
        backend.close()

    @pytest.mark.parametrize("atomic_replace", [False, True])
    def test_execute_refreshes_environment_with_unchanged_metadata(
        self, tmp_path: Path, mock_docker: Any, atomic_replace: bool
    ) -> None:
        _docker_mod, client, _container = mock_docker
        env_file = tmp_path / "global.env"
        env_file.write_text("ADMIN_KEY=one\n", encoding="utf-8")
        before = env_file.stat()
        with resolve_backend({"type": "docker", "environment_file": str(env_file)}, workspace_dir=tmp_path) as backend:
            backend.execute("true")
            assert client.api.exec_create.call_args.kwargs["environment"]["ADMIN_KEY"] == "one"
            replacement = tmp_path / "replacement.env" if atomic_replace else env_file
            replacement.write_text("ADMIN_KEY=two\n", encoding="utf-8")
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            if atomic_replace:
                replacement.replace(env_file)
            after = env_file.stat()
            assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)
            backend.execute("true")
            assert client.api.exec_create.call_args.kwargs["environment"]["ADMIN_KEY"] == "two"

    def test_upload_and_download(self, tmp_path: Path, mock_docker: Any) -> None:
        _docker_mod, _client, container = mock_docker
        backend = resolve_backend({"type": "docker"}, workspace_dir=tmp_path)

        uploads = backend.upload_files([("/SOUL.md", b"content")])
        assert uploads[0].error is None
        assert container.put_archive.called

        container.get_archive.return_value = (
            iter([_tar_bytes("SOUL.md", b"content")]),
            {},
        )
        downloads = backend.download_files(["/SOUL.md"])
        assert downloads[0].content == b"content"
        backend.close()

    def test_close_via_octop_harness(self, tmp_path: Path, mock_docker: Any) -> None:
        from octop_harness.agent import HarnessAgent
        from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

        backend = resolve_backend({"type": "docker"}, workspace_dir=tmp_path)
        close_mock = MagicMock(wraps=backend.close)
        backend.close = close_mock  # type: ignore[method-assign]

        config = HarnessAgentConfig(
            name="docker-test",
            workspace_dir=tmp_path,
            backend=backend,
            providers=[
                ProviderConfig(
                    id="test",
                    base_url="https://example.com",
                    api_key="sk-xxx",
                    models=[ModelConfig(id="m", name="m")],
                )
            ],
            default_model="test/m",
        )
        with (
            patch("deepagents.create_deep_agent", return_value=MagicMock()),
            patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        ):
            agent = HarnessAgent(config)
            agent.close()
        close_mock.assert_called()


class TestEnsureImage:
    def test_missing_image_pull_failure_raises_runtime_error(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        docker_mod, client, _container = mock_docker
        client.images.get.side_effect = docker_mod.errors.ImageNotFound("missing")
        client.images.pull.side_effect = docker_mod.errors.DockerException(
            "network unreachable",
        )

        with pytest.raises(RuntimeError, match=r"docker pull python:3\.12-slim"):
            resolve_backend({"type": "docker", "image": "python:3.12-slim"}, workspace_dir=tmp_path)

        client.containers.run.assert_not_called()

    def test_credstore_error_retries_anonymous_pull(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        docker_mod, client, _container = mock_docker
        client.images.get.side_effect = docker_mod.errors.ImageNotFound("missing")
        client.images.pull.side_effect = docker_mod.errors.DockerException(
            "Credentials store error: docker-credential-osxkeychain not installed",
        )
        client.api.pull.return_value = iter([{"status": "Downloaded newer image"}])

        backend = resolve_backend(
            {"type": "docker", "image": "python:3.12-slim"},
            workspace_dir=tmp_path,
        )
        client.api.pull.assert_called_once()
        assert client.api.pull.call_args.kwargs.get("auth_config") == {}
        client.containers.run.assert_called_once()
        backend.close()

    def test_credstore_and_anonymous_both_fail(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        docker_mod, client, _container = mock_docker
        client.images.get.side_effect = docker_mod.errors.ImageNotFound("missing")
        client.images.pull.side_effect = docker_mod.errors.DockerException(
            "Credentials store error: docker-credential-osxkeychain not installed",
        )
        client.api.pull.return_value = iter([{"error": "pull access denied"}])

        with pytest.raises(RuntimeError, match=r"credential helper|docker pull"):
            resolve_backend({"type": "docker", "image": "private/img:1"}, workspace_dir=tmp_path)

    def test_missing_image_pull_success_then_runs(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        docker_mod, client, _container = mock_docker
        client.images.get.side_effect = docker_mod.errors.ImageNotFound("missing")
        client.images.pull.return_value = MagicMock()

        backend = resolve_backend(
            {"type": "docker", "image": "python:3.12-slim"},
            workspace_dir=tmp_path,
        )
        client.images.pull.assert_called_once_with("python:3.12-slim")
        client.containers.run.assert_called_once()
        backend.close()

    def test_local_image_skips_pull(self, tmp_path: Path, mock_docker: Any) -> None:
        _docker_mod, client, _container = mock_docker
        backend = resolve_backend({"type": "docker"}, workspace_dir=tmp_path)
        client.images.get.assert_called()
        client.images.pull.assert_not_called()
        backend.close()


class TestPathMapping:
    def test_virtual_root_maps_into_workspace(self, tmp_path: Path, mock_docker: Any) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, _client, _container = mock_docker
        sandbox = DockerSandbox(workspace_dir=tmp_path, image="python:3.12-slim")
        root = str(tmp_path.resolve())
        assert sandbox._workspace_root == root
        assert sandbox._map_path("/SOUL.md") == f"{root}/SOUL.md"
        assert sandbox._map_path("rel.txt") == f"{root}/rel.txt"
        assert sandbox._map_path(f"{root}/x") == f"{root}/x"
        assert sandbox._map_path(".") == root
        assert sandbox._map_path("/") == root
        assert sandbox._map_path("/tmp/x") == f"{root}/tmp/x"
        sandbox.close()

    def test_explicit_workspace_path_overrides_dir(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, _container = mock_docker
        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            workspace_path="/workspace",
            image="python:3.12-slim",
        )
        assert sandbox._workspace_root == "/workspace"
        assert client.containers.run.call_args.kwargs["working_dir"] == "/workspace"
        sandbox.close()

    def test_optional_user_volumes_passed_through(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, _container = mock_docker
        vols = {"/host/data": {"bind": "/data", "mode": "ro"}}
        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            image="python:3.12-slim",
            agent_id="vol1",
            volumes=vols,
        )
        assert client.containers.run.call_args.kwargs["volumes"] == vols
        client.volumes.create.assert_not_called()
        sandbox.close()

    def test_ls_returns_virtual_paths_not_container_root(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        import asyncio
        import base64
        import json
        import re

        from octop_harness.backends.docker_sandbox import DockerSandbox
        from octop_harness.backends.workspace import BackendWorkspace

        _docker_mod, client, container = mock_docker

        def exec_output_for_cmd(cmd: Any) -> bytes:
            c = cmd[2] if isinstance(cmd, list) else str(cmd)
            if "mkdir -p" in c and "base64" not in c:
                return b""
            m = re.search(r"base64\.b64decode\('([^']+)'\)", c)
            path = base64.b64decode(m.group(1)).decode() if m else "?"
            root = str(tmp_path.resolve())
            assert path == root, f"ls must target sandbox workspace, got {path!r}"
            entries = [
                {"path": f"{root}/SOUL.md", "is_dir": False},
                {"path": f"{root}/skills", "is_dir": True},
            ]
            return ("\n".join(json.dumps(e) for e in entries) + "\n").encode()

        def exec_create(container_id: str, cmd: Any, **kwargs: Any) -> dict[str, str]:
            client.api._last_cmd = cmd
            return {"Id": "exec-ls"}

        def exec_start(exec_id: str, **kwargs: Any) -> bytes:
            return exec_output_for_cmd(client.api._last_cmd)

        client.api.exec_create.side_effect = exec_create
        client.api.exec_start.side_effect = exec_start
        # mkdir -p during __init__ still uses container.exec_run
        container.exec_run.return_value = (0, b"")

        sandbox = DockerSandbox(workspace_dir=tmp_path, image="python:3.12-slim")
        result = sandbox.ls("/")
        paths = [e["path"] if isinstance(e, dict) else e.path for e in (result.entries or [])]
        assert paths == ["/SOUL.md", "/skills"]

        ws = BackendWorkspace(sandbox, tmp_path)
        listed = asyncio.run(ws.als("."))
        presented = [e["path"] if isinstance(e, dict) else getattr(e, "path", e) for e in (listed.entries or [])]
        assert presented == ["SOUL.md", "skills"]
        # Host workspace dir must stay empty of agent content (no bind-mount).
        assert not (tmp_path / "SOUL.md").exists()
        sandbox.close()

    def test_async_als_does_not_bypass_path_mapping(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        """Regression: deepagents>=0.6.12 BaseSandbox.als uses aexecute(raw path).

        Without an override, BackendWorkspace.als('/') lists container root
        (bin/usr/…) instead of ``workspace_path``.
        """
        import asyncio
        import base64
        import json
        import re

        from octop_harness.backends.docker_sandbox import DockerSandbox
        from octop_harness.backends.workspace import BackendWorkspace

        _docker_mod, client, container = mock_docker
        seen_paths: list[str] = []

        def exec_output_for_cmd(cmd: Any) -> bytes:
            c = cmd[2] if isinstance(cmd, list) else str(cmd)
            if "mkdir -p" in c and "base64" not in c:
                return b""
            m = re.search(r"base64\.b64decode\('([^']+)'\)", c)
            path = base64.b64decode(m.group(1)).decode() if m else "?"
            seen_paths.append(path)
            root = str(tmp_path.resolve())
            assert path == root, f"async ls must map to workspace, got {path!r}"
            return (json.dumps({"path": f"{root}/AGENTS.md", "is_dir": False}) + "\n").encode()

        def exec_create(container_id: str, cmd: Any, **kwargs: Any) -> dict[str, str]:
            client.api._last_cmd = cmd
            return {"Id": "exec-als"}

        def exec_start(exec_id: str, **kwargs: Any) -> bytes:
            return exec_output_for_cmd(client.api._last_cmd)

        client.api.exec_create.side_effect = exec_create
        client.api.exec_start.side_effect = exec_start
        container.exec_run.return_value = (0, b"")

        sandbox = DockerSandbox(workspace_dir=tmp_path, image="python:3.12-slim")
        # Call the async API the dashboard uses (not sync ls).
        result = asyncio.run(sandbox.als("/"))
        paths = [e["path"] if isinstance(e, dict) else e.path for e in (result.entries or [])]
        assert paths == ["/AGENTS.md"]
        assert str(tmp_path.resolve()) in seen_paths

        ws = BackendWorkspace(sandbox, tmp_path)
        listed = asyncio.run(ws.als("."))
        presented = [e["path"] if isinstance(e, dict) else getattr(e, "path", e) for e in (listed.entries or [])]
        assert presented == ["AGENTS.md"]
        assert "bin" not in presented and "usr" not in presented
        sandbox.close()

    def test_send_file_downloads_from_sandbox(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox
        from octop_harness.backends.workspace import BackendWorkspace
        from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

        _docker_mod, _client, container = mock_docker
        container.get_archive.return_value = (
            iter([_tar_bytes("AI助手能力介绍.pptx", b"pptx-bytes")]),
            {},
        )

        sandbox = DockerSandbox(workspace_dir=tmp_path, image="python:3.12-slim")
        ws = BackendWorkspace(sandbox, tmp_path)
        tool = build_send_file_to_user_tool(ws)

        block = tool.invoke({"file_path": "/AI助手能力介绍.pptx"})
        assert block["source"]["url"].startswith("file://")
        from urllib.parse import unquote, urlparse

        local = Path(unquote(urlparse(block["source"]["url"]).path))
        assert local.read_bytes() == b"pptx-bytes"
        # Delivery cache only — not the live workspace on host.
        assert (tmp_path / ".harness-materialize").exists()
        assert not (tmp_path / "AI助手能力介绍.pptx").exists()
        sandbox.close()

    def test_workspace_storage_keys_are_virtual(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox
        from octop_harness.backends.workspace import BackendWorkspace

        _docker_mod, _client, _container = mock_docker
        sandbox = DockerSandbox(workspace_dir=tmp_path, image="python:3.12-slim")
        ws = BackendWorkspace(sandbox, tmp_path)
        assert ws.resolve_path("skills") == "/skills"
        assert ws.resolve_path("/SOUL.md") == "/SOUL.md"
        assert ws._backend_storage_key("SOUL.md") == "/SOUL.md"
        sandbox.close()


class TestContainerReuse:
    def test_reuses_running_container_by_agent_id(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, existing = mock_docker
        existing.status = "running"
        existing.name = "sandbox_agent_abc12"
        client.containers.get.side_effect = None
        client.containers.get.return_value = existing

        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            image="python:3.12-slim",
            agent_id="abc12",
        )
        client.containers.get.assert_called_with("sandbox_agent_abc12")
        client.containers.run.assert_not_called()
        existing.start.assert_not_called()
        assert sandbox.id.startswith("docker:")
        sandbox.close()
        existing.stop.assert_not_called()
        existing.remove.assert_not_called()

    def test_starts_stopped_container(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, existing = mock_docker
        existing.status = "exited"
        client.containers.get.side_effect = None
        client.containers.get.return_value = existing

        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            agent_id="abc12",
        )
        existing.start.assert_called_once()
        client.containers.run.assert_not_called()
        sandbox.close()

    def test_create_when_missing(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        docker_mod, client, _container = mock_docker
        client.containers.get.side_effect = docker_mod.errors.NotFound("gone")

        sandbox = DockerSandbox(workspace_dir=tmp_path, agent_id="abc12")
        client.containers.run.assert_called_once()
        assert client.containers.run.call_args.kwargs["name"] == "sandbox_agent_abc12"
        assert client.containers.run.call_args.kwargs.get("auto_remove") in (None, False)
        assert "volumes" not in client.containers.run.call_args.kwargs
        sandbox.close()

    def test_rebind_when_container_vanishes(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        docker_mod, client, first = mock_docker
        first.status = "running"
        client.containers.get.side_effect = docker_mod.errors.NotFound("gone")
        second = MagicMock()
        second.id = "second999"
        second.status = "running"
        client.containers.run.side_effect = [first, second]

        sandbox = DockerSandbox(workspace_dir=tmp_path, agent_id="gone1")
        assert sandbox._container is first
        # Simulate external remove: reload raises NotFound.
        first.reload.side_effect = docker_mod.errors.NotFound("removed")
        client.containers.get.side_effect = docker_mod.errors.NotFound("gone")
        result = sandbox.execute("echo hi")
        assert result.exit_code == 0
        assert sandbox._container is second
        assert client.containers.run.call_count == 2
        sandbox.close()

    def test_restart_fail_renames_orphan_then_creates(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        docker_mod, client, existing = mock_docker
        existing.status = "exited"
        existing.start.side_effect = docker_mod.errors.APIError("cannot start")
        client.containers.get.side_effect = None
        client.containers.get.return_value = existing
        fresh = MagicMock()
        fresh.id = "fresh999"
        client.containers.run.return_value = fresh

        sandbox = DockerSandbox(workspace_dir=tmp_path, agent_id="abc12")
        existing.rename.assert_called()
        orphan_name = existing.rename.call_args.args[0]
        assert "sandbox_agent_abc12" in orphan_name
        assert orphan_name != "sandbox_agent_abc12"
        client.containers.run.assert_called_once()
        assert sandbox._container is fresh
        # Orphan is kept (not removed).
        existing.remove.assert_not_called()
        sandbox.close()

    def test_destroy_removes_container(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, _client, container = mock_docker
        sandbox = DockerSandbox(workspace_dir=tmp_path, agent_id="d1")
        sandbox.destroy()
        container.stop.assert_called()
        container.remove.assert_called()
        with pytest.raises(RuntimeError, match=r"closed|destroyed"):
            sandbox.execute("echo hi")


class TestSandboxNaming:
    def test_resolve_agent_default_prefix(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        assert resolve_sandbox_name(agent_id="ZE6GR2") == "sandbox_agent_ZE6GR2"

    def test_resolve_agent_octop_prefix(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        assert (
            resolve_sandbox_name(
                sandbox_prefix="octop_sandbox",
                agent_id="ZE6GR2",
            )
            == "octop_sandbox_agent_ZE6GR2"
        )

    def test_resolve_user_scope(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        assert (
            resolve_sandbox_name(
                sandbox_scope="user",
                sandbox_prefix="octop_sandbox",
                username="alice",
            )
            == "octop_sandbox_alice"
        )

    def test_resolve_fixed_scope(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        assert (
            resolve_sandbox_name(
                sandbox_scope="fixed",
                sandbox_id="my_shared_box",
            )
            == "my_shared_box"
        )

    def test_user_scope_requires_username(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        with pytest.raises(ValueError, match=r"username"):
            resolve_sandbox_name(sandbox_scope="user")

    def test_fixed_scope_requires_sandbox_id(self) -> None:
        from octop_harness.backends.docker_sandbox import resolve_sandbox_name

        with pytest.raises(ValueError, match=r"sandbox_id"):
            resolve_sandbox_name(sandbox_scope="fixed")

    def test_user_scope_previewable_false(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, _container = mock_docker
        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            sandbox_scope="user",
            sandbox_prefix="octop_sandbox",
            username="bob",
        )
        assert client.containers.run.call_args.kwargs["name"] == "octop_sandbox_bob"
        assert sandbox.previewable is False
        sandbox.close()

    def test_fixed_scope_previewable_true(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, _container = mock_docker
        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            sandbox_scope="fixed",
            sandbox_id="shared1",
        )
        assert client.containers.run.call_args.kwargs["name"] == "shared1"
        assert sandbox.previewable is True
        sandbox.close()


class TestExecuteTimeout:
    def test_execute_times_out(self, tmp_path: Path, mock_docker: Any) -> None:
        import time

        from octop_harness.backends.docker_sandbox import DockerSandbox

        _docker_mod, client, _container = mock_docker
        client.api.exec_create.return_value = {"Id": "exec1"}
        client.api.exec_inspect.side_effect = [
            {"Pid": 42, "ExitCode": None, "Running": True},
            {"Pid": 42, "ExitCode": 137, "Running": False},
        ]

        def slow_start(*_a: Any, **_k: Any) -> bytes:
            time.sleep(2)
            return b"late\n"

        client.api.exec_start.side_effect = slow_start

        sandbox = DockerSandbox(
            workspace_dir=tmp_path,
            command_timeout=1,
            agent_id="t1",
        )
        result = sandbox.execute("sleep 99", timeout=1)
        assert result.exit_code == 124
        assert "timed out" in result.output.lower()
        sandbox.close()


class TestMaterializePath:
    def test_materialize_strips_workspace_prefix(
        self,
        tmp_path: Path,
        mock_docker: Any,
    ) -> None:
        from octop_harness.backends.docker_sandbox import DockerSandbox
        from octop_harness.backends.workspace import BackendWorkspace

        _docker_mod, _client, container = mock_docker
        container.get_archive.return_value = (
            iter([_tar_bytes("deck.pptx", b"pptx")]),
            {},
        )
        sandbox = DockerSandbox(workspace_dir=tmp_path, agent_id="m1")
        ws = BackendWorkspace(sandbox, tmp_path)
        local = ws.materialize_local("/deck.pptx")
        assert local is not None
        assert local == tmp_path / ".harness-materialize" / "deck.pptx"
        assert local.read_bytes() == b"pptx"
        sandbox.close()
