"""Harness object-storage backend fixes (upstream gaps — delete once fixed).

Covers the object-store ``kind``s Octop exposes: ``s3`` (also ``custom``),
``cos``, ``oss`` and ``obs``. Three gaps in ``orcakit-harness-agent`` make them
only partly usable:

1. ``backends._build_s3`` prefers ``deepagents_backends.S3Backend`` whenever
   that package imports — and Octop depends on ``orcakit-harness-agent[all]``,
   which pulls it in. Every released ``deepagents-backends`` still targets the
   deepagents 0.5/0.6 protocol: it passes the removed ``files_update=`` keyword
   to ``WriteResult`` / ``EditResult`` and only implements the removed
   ``ls_info`` / ``glob_info`` / ``grep_raw`` names. Under the ``deepagents``
   series harness accepts (0.7.x) every write/edit fails with ``TypeError`` and
   ``ls`` raises ``NotImplementedError``. **``s3`` only** — the other kinds use
   their vendor SDKs and are unaffected.
2. The bundled boto3 backend signs with SigV2 (``signature_version="s3"``).
   Stores without SigV2 support reject the ``ListObjectsV2`` calls behind
   ``ls`` / ``glob`` / ``grep`` with ``SignatureDoesNotMatch``. ``S3Config``
   has no ``signature_version`` field and ``_build_client`` never reads its
   ``extra`` dict, so this cannot be corrected through a spec — only in code.
   **``s3`` only** — likewise a vendor-SDK concern for the others.
3. ``CloudStorageBackend`` — the shared base of all four — leaves the protocol's
   ``delete`` abstract (it offers ``delete_object`` / ``delete_prefix``
   primitives instead), so the agent file tools' delete path raises
   ``NotImplementedError``. This one applies to **every** kind.

The fix stays on public API: each ``*CompatBackend`` subclasses the matching
harness backend — overriding ``_build_client`` only where the signing bug
applies — and then the caller hands harness a ready instance, because
``HarnessAgentConfig.backend`` accepts any ``BackendProtocol`` object and
``resolve_backend`` returns an instance unchanged. These types are never
composite-wrapped, so an instance behaves exactly like the spec it replaces.

Inheriting from the harness backends also keeps the private tree helpers
(``delete_path`` / ``mkdir_path`` / ``move_path``) that ``BackendWorkspace``
uses for dashboard mutations.

Delete this module and its call sites once a newer ``orcakit-harness-agent``
resolves a working object-storage backend on its own. Regression coverage lives
in ``tests/unit/backend/test_harness_s3_compat.py``;
``docs/agent-backend-file-io.md`` §14 records the gaps and the removal
condition.
"""

from __future__ import annotations

from typing import Any

from deepagents.backends.protocol import DeleteResult
from harness_agent.backends import (
    cos_backend,
    obs_backend,
    oss_backend,
    resolve_backend,
    s3_backend,
)

_OBJECT_STORE_KINDS = frozenset({"s3", "cos", "oss", "obs"})


class _ProtocolDelete:
    """Protocol ``delete`` for object stores (upstream leaves it abstract).

    ``CloudStorageBackend`` provides the ``delete_object`` / ``delete_prefix``
    primitives but never implements the protocol method, so this follows the
    conventions of its ``read`` / ``write``: storage primitives for the work,
    outcome in a ``DeleteResult``.
    """

    def delete(self, file_path: str) -> DeleteResult:
        """Delete *file_path*, recursively when it names a directory prefix."""
        try:
            if self._get_file_data(file_path) is not None:  # type: ignore[attr-defined]
                self.delete_object(file_path)  # type: ignore[attr-defined]
                return DeleteResult(path=file_path)
            if self._prefix_has_objects(file_path):  # type: ignore[attr-defined]
                self.delete_prefix(file_path)  # type: ignore[attr-defined]
                return DeleteResult(path=file_path)
        except self._storage_error_types() as exc:  # type: ignore[attr-defined]
            return DeleteResult(error=f"Error deleting {file_path!r}: {exc}")
        return DeleteResult(error=f"Error: File '{file_path}' not found")


class SigV4S3Backend(_ProtocolDelete, s3_backend.S3Backend):
    """Bundled S3 backend that signs with SigV4 and implements ``delete``."""

    @staticmethod
    def _build_client(config: s3_backend.S3Config) -> Any:
        """Build the boto3 client with SigV4.

        Mirrors ``harness_agent.backends.s3_backend.S3Backend._build_client``;
        only ``signature_version`` differs (upstream hardcodes the SigV2
        ``"s3"``, which SigV4-only stores reject).
        """
        import boto3
        import botocore.config

        kwargs: dict[str, Any] = {
            "aws_access_key_id": config.access_key_id,
            "aws_secret_access_key": config.secret_access_key,
        }
        if config.region:
            kwargs["region_name"] = config.region
        if config.endpoint_url:
            kwargs["endpoint_url"] = config.endpoint_url
        kwargs["config"] = botocore.config.Config(
            signature_version="s3v4",
            s3={"addressing_style": config.addressing_style},
        )
        return boto3.client("s3", **kwargs)


class CosCompatBackend(_ProtocolDelete, cos_backend.CosBackend):
    """Tencent COS backend with the protocol ``delete`` implemented."""


class OssCompatBackend(_ProtocolDelete, oss_backend.OssBackend):
    """Alibaba OSS backend with the protocol ``delete`` implemented."""


class ObsCompatBackend(_ProtocolDelete, obs_backend.ObsBackend):
    """Huawei OBS backend with the protocol ``delete`` implemented."""


def _build_object_store(kind: str, config: dict[str, Any]) -> Any:
    """Construct the delete-capable backend for *kind* from spec *config*.

    Config construction mirrors ``harness_agent.backends``' own builders, so a
    converted instance is configured exactly like the spec it replaces, apart
    from the addressing style default described below.
    """
    if kind == "s3":
        return SigV4S3Backend(s3_backend.S3Config.from_kwargs(**_s3_config(config)))
    if kind == "cos":
        return CosCompatBackend(cos_backend.CosConfig(**config))
    if kind == "oss":
        return OssCompatBackend(oss_backend.OssConfig(**config))
    if kind == "obs":
        return ObsCompatBackend(obs_backend.ObsConfig(**config))
    raise ValueError(f"unsupported object store kind {kind!r}")


def _s3_config(config: dict[str, Any]) -> dict[str, Any]:
    """Apply Octop's addressing-style default for ``type="s3"`` specs.

    Upstream defaults to virtual-hosted addressing, which puts the bucket in the
    hostname (``<bucket>.<endpoint host>``). That only works when the endpoint is
    an AWS domain or when the operator has set up wildcard DNS (MinIO needs
    ``MINIO_DOMAIN``); against a plain hostname it fails with
    ``InvalidBucketName`` because the store parses the bucket out of ``Host``.
    IP endpoints are unaffected — botocore forces path style there anyway.

    A custom endpoint means a self-hosted S3-compatible store, where path style
    is the form every implementation accepts, so default to it. A spec with no
    endpoint is left to AWS' own default, and an explicit
    ``config_json.addressing_style`` always wins.
    """
    if not config.get("endpoint_url") or "addressing_style" in config:
        return config
    return {**config, "addressing_style": "path"}


def _convert(node: Any) -> Any:
    """Replace every object-store spec in *node* with a working instance.

    Recurses through ``composite`` trees so an object store used as a ``routes``
    entry or ``default`` is fixed too. Non-dict nodes and unrelated backend
    types are returned unchanged, so harness still resolves them exactly as
    before.
    """
    if not isinstance(node, dict):
        return node
    kind = str(node.get("type") or "").lower()
    if kind in _OBJECT_STORE_KINDS:
        return _build_object_store(kind, {k: v for k, v in node.items() if k != "type"})
    if "default" not in node and "routes" not in node:
        return node
    converted = dict(node)
    if "default" in node:
        converted["default"] = _convert(node["default"])
    routes = node.get("routes")
    if isinstance(routes, dict):
        converted["routes"] = {prefix: _convert(sub) for prefix, sub in routes.items()}
    return converted


def is_object_store_spec(spec: Any) -> bool:
    """True when *spec* is an object-store spec this module converts."""
    return isinstance(spec, dict) and str(spec.get("type") or "").lower() in _OBJECT_STORE_KINDS


def harness_compatible_spec(spec: Any) -> Any:
    """Return *spec* with object-store nodes replaced by working instances.

    Use for values harness resolves itself (notably
    ``HarnessAgentConfig.backend``): everything except an object-store spec is
    returned as-is, so harness keeps doing its own resolution for other backend
    types.
    """
    return _convert(spec)


def resolve_backend_spec(spec: Any, *, workspace_dir: Any = None) -> Any:
    """Resolve *spec* into a harness backend, fixing object-store nodes."""
    return resolve_backend(_convert(spec), workspace_dir=workspace_dir)


__all__ = [
    "CosCompatBackend",
    "ObsCompatBackend",
    "OssCompatBackend",
    "SigV4S3Backend",
    "harness_compatible_spec",
    "is_object_store_spec",
    "resolve_backend_spec",
]
