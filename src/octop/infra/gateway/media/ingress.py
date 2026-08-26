"""IM ingress media → agent workspace ``inbound/`` via :class:`BackendWorkspace`."""

from __future__ import annotations

from pathlib import Path

from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.media import MediaBackend

from octop.infra.gateway.media.constants import OUTBOUND_DIR
from octop.infra.gateway.media.inbound_store import inbound_rel_path, validate_inbound_size


class AgentBackedMediaBackend(MediaBackend):
    """harness-gateway ``MediaBackend`` adapter backed by ``agent.workspace``."""

    def __init__(self, workspace: BackendWorkspace, *, max_bytes: int | None = None) -> None:
        self._workspace = workspace
        self._max_bytes = max_bytes

    async def save(self, data: bytes, key: str) -> None:
        validate_inbound_size(data, max_bytes=self._max_bytes)
        await self._workspace.aupload_bytes(inbound_rel_path(key), data)

    async def read(self, key: str) -> bytes:
        rel = inbound_rel_path(key)
        data = await self._workspace.adownload_bytes(rel)
        if data is None:
            raise FileNotFoundError(f"Backend download returned no data for {rel!r}")
        return data

    async def exists(self, key: str) -> bool:
        return await self._workspace.aexists(inbound_rel_path(key))

    def get_local_path(self, key: str) -> Path | None:
        return self._workspace.materialize_local(inbound_rel_path(key))

    @property
    def outbound_dir(self) -> str:
        return f"/{OUTBOUND_DIR}"

    @property
    def inbound_dir(self) -> str:
        return "/inbound"

    @staticmethod
    def _inbound_fragment(key: str) -> str:
        """Backward-compatible alias used in tests."""
        return inbound_rel_path(key)
