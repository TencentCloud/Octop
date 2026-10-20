"""Tests for ``octop_harness.backends.resolve_backend``."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from deepagents.backends import CompositeBackend, LocalShellBackend
from deepagents.middleware.filesystem import supports_execution

from octop_harness.backends import (
    DEFAULT_BACKEND_SPEC,
    MountedCompositeBackend,
    resolve_backend,
    spec_supports_execution,
)
from octop_harness.backends.workspace import BackendWorkspace


class TestDefaultSpec:
    def test_default_backend_spec(self) -> None:
        assert DEFAULT_BACKEND_SPEC == {
            "type": "local_shell",
            "root_dir": "/",
            "virtual_mode": True,
        }

    def test_none_resolves_to_local_shell_root(self) -> None:
        """resolve_backend(None) without workspace keeps a bare host-rooted shell."""
        backend = resolve_backend(None)
        assert isinstance(backend, LocalShellBackend)

    def test_none_with_workspace_scopes_artifacts(self, tmp_path: Path) -> None:
        backend = resolve_backend(None, workspace_dir=tmp_path)
        assert isinstance(backend, MountedCompositeBackend)
        assert backend.artifacts_root == str(tmp_path.resolve())
        assert isinstance(backend.default, LocalShellBackend)
        assert str(backend.cwd) == "/"
        assert supports_execution(backend)

    def test_host_root_spec_with_workspace_scopes_artifacts(self, tmp_path: Path) -> None:
        backend = resolve_backend(dict(DEFAULT_BACKEND_SPEC), workspace_dir=tmp_path)
        assert isinstance(backend, MountedCompositeBackend)
        assert backend.artifacts_root == str(tmp_path.resolve())

        history = tmp_path / "conversation_history" / "thread.md"
        result = backend.write(str(history), "context summary")
        assert result.error is None
        assert history.read_text(encoding="utf-8") == "context summary"

    def test_system_files_path_scopes_artifacts_under_prefix(self, tmp_path: Path) -> None:
        backend = resolve_backend(
            dict(DEFAULT_BACKEND_SPEC),
            workspace_dir=tmp_path,
            system_files_path=".octop",
        )
        assert isinstance(backend, MountedCompositeBackend)
        assert backend.artifacts_root == str((tmp_path / ".octop").resolve())

        history = tmp_path / ".octop" / "conversation_history" / "thread.md"
        result = backend.write(str(history), "context summary")
        assert result.error is None
        assert history.read_text(encoding="utf-8") == "context summary"

    def test_custom_root_dir_scopes_artifacts_via_virtual_path(self, tmp_path: Path) -> None:
        """Non-host root_dir must still offload under the workspace (virtual path)."""
        root = tmp_path / "home"
        ws = root / ".octop" / "workspaces" / "NBR8CP"
        ws.mkdir(parents=True)

        backend = resolve_backend(
            {
                "type": "local_shell",
                "root_dir": str(root),
                "virtual_mode": True,
            },
            workspace_dir=ws,
            system_files_path=".octop",
        )
        assert isinstance(backend, MountedCompositeBackend)
        assert backend.artifacts_root == "/.octop/workspaces/NBR8CP/.octop"

        history_key = f"{backend.artifacts_root}/conversation_history/thread.md"
        result = backend.write(history_key, "context summary")
        assert result.error is None
        host_file = ws / ".octop" / "conversation_history" / "thread.md"
        assert host_file.read_text(encoding="utf-8") == "context summary"

    def test_host_root_composite_keeps_workspace_mutations(self, tmp_path: Path) -> None:
        backend = resolve_backend(dict(DEFAULT_BACKEND_SPEC), workspace_dir=tmp_path)
        workspace = BackendWorkspace(backend, tmp_path)
        workspace.mkdir("source")
        source = tmp_path / "source" / "note.txt"
        source.write_text("ok", encoding="utf-8")
        workspace.move("source", "moved")
        assert (tmp_path / "moved" / "note.txt").read_text(encoding="utf-8") == "ok"
        workspace.delete("moved")
        assert not (tmp_path / "moved").exists()


class TestSpecSupportsExecution:
    """``spec_supports_execution`` must predict ``supports_execution`` from the spec alone."""

    def test_none_is_shell_capable(self) -> None:
        assert spec_supports_execution(None) is True

    def test_local_shell_string(self) -> None:
        assert spec_supports_execution("local_shell") is True

    def test_filesystem_string(self) -> None:
        assert spec_supports_execution("filesystem") is False

    def test_composite_follows_default_not_routes(self) -> None:
        spec = {
            "type": "composite",
            "default": "filesystem",
            "routes": {"/tmp/": "local_shell"},
        }
        assert spec_supports_execution(spec) is False

    def test_composite_with_shell_default(self) -> None:
        spec = {"type": "composite", "default": {"type": "local_shell"}}
        assert spec_supports_execution(spec) is True

    def test_backend_instance(self, tmp_path: Path) -> None:
        backend = resolve_backend({"type": "local_shell", "root_dir": str(tmp_path)})
        assert spec_supports_execution(backend) is True

    @pytest.mark.parametrize(
        "spec",
        [
            None,
            "local_shell",
            "filesystem",
            "state",
            {"type": "local_shell", "root_dir": "/"},
            {"type": "composite", "default": "filesystem", "routes": {"/x/": "local_shell"}},
        ],
    )
    def test_matches_resolved_backend(self, spec: object, tmp_path: Path) -> None:
        resolved = resolve_backend(spec, workspace_dir=tmp_path)
        assert spec_supports_execution(spec) is supports_execution(resolved)


class TestStringForms:
    def test_filesystem_string(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        backend = resolve_backend("filesystem", workspace_dir=tmp_path)
        assert isinstance(backend, FilesystemBackend)

    def test_state_string(self) -> None:
        from deepagents.backends import StateBackend

        backend = resolve_backend("state")
        assert isinstance(backend, StateBackend)


class TestDictForms:
    def test_filesystem_with_explicit_root(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend

        backend = resolve_backend({"type": "filesystem", "root_dir": str(tmp_path)})
        assert isinstance(backend, FilesystemBackend)

    def test_local_shell_with_explicit_workspace_no_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Passing ``workspace_dir`` (non-'/') should NOT trigger the warning."""
        from deepagents.backends import LocalShellBackend

        with caplog.at_level(logging.WARNING):
            backend = resolve_backend("local_shell", workspace_dir=tmp_path)
        assert isinstance(backend, LocalShellBackend)
        assert not any("rooted at '/'" in rec.message for rec in caplog.records)

    def test_local_shell_default_root_warns(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Default root is '/', which DOES trigger the warning."""
        from deepagents.backends import LocalShellBackend

        from octop_harness.backends import _HOST_ROOT_WARNED

        # The warning is once per workspace for the process. An earlier test
        # may already have built a host-root shell with no workspace.
        _HOST_ROOT_WARNED.clear()
        with caplog.at_level(logging.WARNING):
            backend = resolve_backend("local_shell")
            resolve_backend("local_shell")
        assert isinstance(backend, LocalShellBackend)
        matching = [rec for rec in caplog.records if "rooted at '/'" in rec.message]
        assert len(matching) == 1

    def test_local_shell_root_slash_warns(
        self,
        caplog: pytest.LogCaptureFixture,
        tmp_path: Path,
    ) -> None:
        """Explicitly setting root_dir='/' triggers the warning (includes workspace)."""
        from octop_harness.backends import _HOST_ROOT_WARNED

        _HOST_ROOT_WARNED.clear()
        with caplog.at_level(logging.WARNING):
            resolve_backend(
                {"type": "local_shell", "root_dir": "/"},
                workspace_dir=tmp_path,
            )
            resolve_backend(
                {"type": "local_shell", "root_dir": "/"},
                workspace_dir=tmp_path,
            )
        matching = [rec.message for rec in caplog.records if "rooted at '/'" in rec.message]
        assert len(matching) == 1
        assert f"workspace={tmp_path}" in matching[0]

    def test_local_shell_explicit_root_no_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from deepagents.backends import LocalShellBackend

        from octop_harness.backends.bwrap_shell import (
            BubbledLocalShellBackend,
            HarnessLocalShellBackend,
            can_use_bubbled_shell,
        )

        with caplog.at_level(logging.WARNING):
            backend = resolve_backend({"type": "local_shell", "root_dir": str(tmp_path)})
        assert isinstance(backend, HarnessLocalShellBackend)
        assert isinstance(backend, LocalShellBackend)
        assert isinstance(backend, BubbledLocalShellBackend) is can_use_bubbled_shell(
            virtual_mode=True,
            root_dir=tmp_path,
        )
        if isinstance(backend, BubbledLocalShellBackend):
            assert backend._bwrap_path
        # Specifically the "rooted at /" warning should not fire.
        assert not any("rooted at '/'" in rec.message for rec in caplog.records)


class TestComposite:
    def test_composite_recursively_resolves_subspecs(self, tmp_path: Path) -> None:
        from deepagents.backends import FilesystemBackend, StateBackend

        backend = resolve_backend(
            {
                "type": "composite",
                "default": "state",
                "routes": {
                    "/workspace/": {"type": "filesystem", "root_dir": str(tmp_path)},
                },
            },
        )
        assert isinstance(backend, MountedCompositeBackend)
        assert isinstance(backend, CompositeBackend)
        # Composite stores the resolved subbackends — peek inside to make sure
        # the recursion did the right thing.
        assert isinstance(backend.default, StateBackend)  # type: ignore[attr-defined]
        routes = backend.routes  # type: ignore[attr-defined]
        assert isinstance(routes["/workspace/"], FilesystemBackend)

    def test_composite_with_workspace_defaults_artifacts_root(self, tmp_path: Path) -> None:
        from deepagents.backends import LocalShellBackend

        backend = resolve_backend(
            {
                "type": "composite",
                "default": {"type": "local_shell", "root_dir": "/", "virtual_mode": True},
                "routes": {},
            },
            workspace_dir=tmp_path,
        )
        assert isinstance(backend, MountedCompositeBackend)
        assert backend.artifacts_root == str(tmp_path.resolve())
        # Sub-backend must not be double-wrapped.
        assert isinstance(backend.default, LocalShellBackend)
        assert str(backend.cwd) == "/"

    def test_composite_explicit_artifacts_root_preserved(self, tmp_path: Path) -> None:
        custom = str((tmp_path / "custom-artifacts").resolve())
        backend = resolve_backend(
            {
                "type": "composite",
                "default": "state",
                "routes": {},
                "artifacts_root": custom,
            },
            workspace_dir=tmp_path,
        )
        assert backend.artifacts_root == custom

    def test_composite_missing_default_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a 'default'"):
            resolve_backend({"type": "composite", "routes": {}})

    def test_composite_routes_must_be_dict(self) -> None:
        with pytest.raises(ValueError, match="routes"):
            resolve_backend({"type": "composite", "default": "state", "routes": []})


class TestErrors:
    def test_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend type"):
            resolve_backend("teleporter")

    def test_dict_without_type(self) -> None:
        with pytest.raises(ValueError, match="'type' key"):
            resolve_backend({"root_dir": "/"})

    def test_invalid_spec_kind(self) -> None:
        with pytest.raises(ValueError, match=r"(Backend spec must be|BackendProtocol)"):
            resolve_backend(42)

    def test_instance_passed_through(self) -> None:
        from deepagents.backends import StateBackend

        sentinel = StateBackend()
        assert resolve_backend(sentinel) is sentinel


class TestRemoteBackendsImportError:
    """When ``deepagents-backends`` isn't importable, the factory must surface
    a helpful error rather than a generic ``ModuleNotFoundError``."""

    def test_s3_uses_bundled_backend_without_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("boto3", reason="boto3 not installed; skipping S3Backend test")
        from octop_harness.backends.s3_backend import S3CompatBackend

        monkeypatch.setitem(sys.modules, "deepagents_backends", None)
        backend = resolve_backend(
            {
                "type": "s3",
                "bucket": "test-bucket",
                "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            }
        )
        assert isinstance(backend, S3CompatBackend)

    def test_s3_uses_bundled_backend_when_deepagents_backends_present(self) -> None:
        pytest.importorskip("boto3", reason="boto3 not installed; skipping S3Backend test")
        from octop_harness.backends.s3_backend import S3Backend

        backend = resolve_backend(
            {
                "type": "s3",
                "bucket": "test-bucket",
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "s3_force_path_style": True,
            }
        )
        assert isinstance(backend, S3Backend)
        assert backend._config.addressing_style == "path"
        assert "s3_force_path_style" not in backend._config.extra

    def test_s3_write_result_compatible_with_deepagents_07(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("boto3", reason="boto3 not installed; skipping S3Backend test")
        backend = resolve_backend(
            {
                "type": "s3",
                "bucket": "test-bucket",
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            }
        )
        monkeypatch.setattr(backend, "_get_file_data", lambda _path: None)
        monkeypatch.setattr(backend, "_put_file_data", lambda _path, _data: None)
        result = backend.write("/.harness-probe-x.txt", "harness-backend-probe")
        assert result.error is None
        assert result.path == "/.harness-probe-x.txt"

    def test_postgres_without_psycopg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "psycopg", None)
        with pytest.raises(ImportError, match="psycopg"):
            resolve_backend({"type": "postgres", "host": "127.0.0.1"})

    def test_postgres_uses_bundled_backend(self) -> None:
        pytest.importorskip("psycopg")
        from octop_harness.backends.postgres import PostgresBackend

        backend = resolve_backend(
            {
                "type": "postgres",
                "host": "127.0.0.1",
                "user": "postgres",
                "password": "postgres",
                "database": "postgres",
            }
        )
        assert isinstance(backend, PostgresBackend)
        assert backend._config.host == "127.0.0.1"
