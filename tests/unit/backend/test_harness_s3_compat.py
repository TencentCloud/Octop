"""Regression tests for the harness object-storage compatibility layer.

Covers the upstream gaps in ``octop.infra.backend.harness_compat``: the
``deepagents-backends`` S3 implementation that harness prefers but cannot drive
on ``deepagents`` 0.7, SigV2 signing in the bundled boto3 backend, and the
protocol ``delete`` that ``CloudStorageBackend`` leaves abstract (all four
object-store kinds). No store is contacted.
"""

from __future__ import annotations

from typing import Any

import pytest
from deepagents.backends.protocol import BackendProtocol, DeleteResult
from harness_agent.backends import resolve_backend

from octop.infra.backend.harness_compat import (
    CosCompatBackend,
    ObsCompatBackend,
    OssCompatBackend,
    SigV4S3Backend,
    harness_compatible_spec,
    is_object_store_spec,
    resolve_backend_spec,
)

# Config values mirror what ``adapter.row_to_backend_spec`` emits per kind.
_SPECS: dict[str, dict[str, Any]] = {
    "s3": {
        "type": "s3",
        "bucket": "octop",
        "access_key_id": "key",
        "secret_access_key": "secret",
        "region": "us-east-1",
        "endpoint_url": "http://127.0.0.1:9",
    },
    "cos": {
        "type": "cos",
        "bucket": "octop",
        "region": "ap-guangzhou",
        "secret_id": "key",
        "secret_key": "secret",
    },
    "oss": {
        "type": "oss",
        "bucket": "octop-test",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        "access_key_id": "key",
        "access_key_secret": "secret",
    },
    "obs": {
        "type": "obs",
        "bucket": "octop-test",
        "endpoint": "obs.cn-north-4.myhuaweicloud.com",
        "access_key_id": "key",
        "secret_access_key": "secret",
    },
}
_EXPECTED = {
    "s3": SigV4S3Backend,
    "cos": CosCompatBackend,
    "oss": OssCompatBackend,
    "obs": ObsCompatBackend,
}
_KINDS = sorted(_SPECS)


@pytest.fixture(params=_KINDS)
def kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def _backend(kind: str) -> Any:
    return resolve_backend_spec(dict(_SPECS[kind]), workspace_dir="/tmp")


def test_object_store_specs_are_recognised() -> None:
    for kind in _KINDS:
        assert is_object_store_spec(_SPECS[kind])
    assert not is_object_store_spec({"type": "filesystem", "root_dir": "/tmp"})
    assert not is_object_store_spec(None)


def test_spec_resolves_to_the_delete_capable_backend(kind: str) -> None:
    # The one assertion that matters: harness' own resolution would hand back a
    # class whose protocol ``delete`` is still the abstract stub.
    backend = _backend(kind)

    assert isinstance(backend, _EXPECTED[kind])
    assert backend.delete.__func__ is not BackendProtocol.delete


def test_s3_spec_uses_sigv4_signing() -> None:
    # SigV2 ("s3") is what upstream hardcodes; SigV4-only stores reject it.
    backend = _backend("s3")

    assert backend._client.meta.config.signature_version == "s3v4"


def test_custom_endpoint_defaults_to_path_style() -> None:
    # Virtual-hosted addressing puts the bucket in the hostname, which a store
    # reached through a plain hostname cannot resolve (InvalidBucketName).
    backend = _backend("s3")

    assert backend._client.meta.config.s3["addressing_style"] == "path"
    assert backend._config.addressing_style == "path"


def test_explicit_addressing_style_wins() -> None:
    spec = {**_SPECS["s3"], "addressing_style": "virtual"}

    backend = resolve_backend_spec(spec, workspace_dir="/tmp")

    assert backend._client.meta.config.s3["addressing_style"] == "virtual"


def test_aws_endpoint_keeps_upstream_addressing_default() -> None:
    # No custom endpoint = AWS' own resolution; leave its default alone.
    spec = {k: v for k, v in _SPECS["s3"].items() if k != "endpoint_url"}

    backend = resolve_backend_spec(spec, workspace_dir="/tmp")

    assert backend._config.addressing_style == "virtual"


def test_non_object_store_specs_resolve_unchanged() -> None:
    backend = resolve_backend_spec({"type": "filesystem", "root_dir": "/tmp"}, workspace_dir="/tmp")

    assert type(backend).__name__ == "FilesystemBackend"


def test_agent_config_spec_keeps_non_object_store_specs_untouched() -> None:
    # Non-object-store specs must reach harness as specs: it still has to apply
    # its own per-type handling (docker names its sandbox from the spec dict).
    docker = {"type": "docker", "image": "python:3.12-slim"}

    assert harness_compatible_spec(docker) is docker


def test_agent_config_spec_converts_nested_object_store() -> None:
    spec = {
        "type": "composite",
        "default": {"type": "filesystem", "root_dir": "/tmp"},
        "routes": {"/data": dict(_SPECS["s3"]), "/cos": dict(_SPECS["cos"])},
    }

    converted = harness_compatible_spec(spec)

    assert converted["default"] == spec["default"]
    assert isinstance(converted["routes"]["/data"], SigV4S3Backend)
    assert isinstance(converted["routes"]["/cos"], CosCompatBackend)
    # A composite carrying instance routes still resolves through harness.
    assert resolve_backend(converted, workspace_dir="/tmp") is not None


def test_delete_reports_missing_path(kind: str) -> None:
    backend = _backend(kind)
    backend._get_file_data = lambda path: None
    backend._prefix_has_objects = lambda path: False

    result = backend.delete("/missing.md")

    assert isinstance(result, DeleteResult)
    assert result.path is None
    assert result.error is not None and "not found" in result.error


def test_delete_file_removes_single_object(kind: str) -> None:
    backend = _backend(kind)
    calls: list[tuple[str, str]] = []
    backend._get_file_data = lambda path: {"content": "x"}
    backend.delete_object = lambda path: calls.append(("object", path))
    backend.delete_prefix = lambda path: calls.append(("prefix", path)) or 1

    result = backend.delete("/a.md")

    assert (result.path, result.error) == ("/a.md", None)
    assert calls == [("object", "/a.md")]


def test_delete_directory_removes_prefix(kind: str) -> None:
    backend = _backend(kind)
    calls: list[tuple[str, str]] = []
    backend._get_file_data = lambda path: None
    backend._prefix_has_objects = lambda path: True
    backend.delete_object = lambda path: calls.append(("object", path))
    backend.delete_prefix = lambda path: calls.append(("prefix", path)) or 2

    result = backend.delete("/dir")

    assert (result.path, result.error) == ("/dir", None)
    assert calls == [("prefix", "/dir")]


def test_delete_surfaces_storage_errors(kind: str) -> None:
    backend = _backend(kind)

    def boom(path: str) -> Any:
        raise OSError("connection reset")

    backend._get_file_data = boom

    result = backend.delete("/a.md")

    assert result.path is None
    assert result.error is not None and "connection reset" in result.error


def test_backends_keep_harness_workspace_mutation_helpers(kind: str) -> None:
    # Subclassing the harness backends (rather than reimplementing them) is what
    # keeps BackendWorkspace's dashboard mutations working.
    backend = _backend(kind)

    for helper in ("delete_path", "mkdir_path", "move_path"):
        assert callable(getattr(backend, helper, None)), helper


def test_module_leaves_harness_internals_untouched() -> None:
    # The fix must stay on public API: no patching of upstream builders, so an
    # unshimmed harness keeps behaving exactly as before for every caller.
    import harness_agent.backends as harness_backends

    builders = {
        name: getattr(harness_backends, name, None)
        for name in ("_build_s3", "_build_cos", "_build_oss", "_build_obs")
    }
    for kind in _KINDS:
        resolve_backend_spec(dict(_SPECS[kind]), workspace_dir="/tmp")
        harness_compatible_spec(dict(_SPECS[kind]))

    assert {name: getattr(harness_backends, name, None) for name in builders} == builders


@pytest.mark.parametrize("kind", _KINDS)
def test_conversion_is_repeatable(kind: str) -> None:
    # browse / probe / manager may convert the same spec several times.
    first = harness_compatible_spec(dict(_SPECS[kind]))
    second = harness_compatible_spec(first)

    assert type(first) is type(second)
