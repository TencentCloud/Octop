"""Reusable test doubles for octop."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deepagents.backends.protocol import (
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
)
from harness_agent.backends.workspace import BackendWorkspace
from harness_gateway.channel import BaseChannel
from harness_gateway.models import InboundMessage, MessageEvent


class FakeHarnessAgent:
    """Minimal stand-in for ``harness_agent.HarnessAgent``.

    Yields a programmable list of chunk dicts, then ``state_snapshot``.
    The ``request`` argument is captured into ``last_request`` for
    inspection.
    """

    def __init__(
        self,
        chunks: list[dict[str, Any]] | None = None,
        raise_on_stream: BaseException | None = None,
        *,
        workspace_dir: Path | None = None,
        virtual_mode: bool = True,
    ) -> None:
        self.chunks = chunks or []
        self.raise_on_stream = raise_on_stream
        self.last_request: dict[str, Any] | None = None
        self.closed = False
        if workspace_dir is not None:
            self.use_workspace_dir(workspace_dir, virtual_mode=virtual_mode)
        else:
            self._workspace_dir = Path(tempfile.mkdtemp(prefix="octop-fake-ws-"))
            self._backend = _FakeBackend()
            self._workspace = BackendWorkspace(self._backend, self._workspace_dir)
        self.config = SimpleNamespace(mcp_server_configs={}, skills_disabled=frozenset())
        self._mcp_tools: list[Any] = []
        self._mcp_tool_name_set: frozenset[str] = frozenset()

    def use_workspace_dir(self, workspace_dir: Path, *, virtual_mode: bool = False) -> None:
        """Bind workspace I/O to a real ``local_shell`` backend on disk.

        The fake mirrors production's ``root_dir="/"`` behaviour by honoring
        absolute paths as-is: ``BackendWorkspace`` resolves paths under
        ``workspace_dir`` and the disk backend writes them there. ``virtual_mode``
        is forced off so absolute paths are not re-rooted under ``root_dir``
        (which would nest writes under ``workspace_dir/tmp/...``).
        """
        from deepagents.backends.local_shell import LocalShellBackend

        self._workspace_dir = workspace_dir
        workspace_dir.mkdir(parents=True, exist_ok=True)
        self._backend = LocalShellBackend(root_dir=str(workspace_dir), virtual_mode=False)
        self._workspace = BackendWorkspace(self._backend, workspace_dir)

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        self.last_request = request
        if self.raise_on_stream is not None:
            raise self.raise_on_stream
        for chunk in self.chunks:
            yield chunk
        yield {"type": "state_snapshot", "data": {}}

    def close(self) -> None:
        self.closed = True

    @property
    def backend(self) -> Any:
        """Return an in-memory fake backend for workspace operations."""
        return self._backend

    @property
    def workspace(self) -> BackendWorkspace:
        return self._workspace

    def is_bootstrapped(self) -> bool:
        return True

    def append_mcp_tools(self, extra_tools: list[Any]) -> None:
        """Mirror harness ``append_mcp_tools`` (no graph recompile in tests)."""
        if not extra_tools:
            return
        existing = {str(getattr(t, "name", "") or "") for t in self._mcp_tools}
        new_tools = [
            tool for tool in extra_tools if str(getattr(tool, "name", "") or "") not in existing
        ]
        if not new_tools:
            return
        self._mcp_tools = list(new_tools) + list(self._mcp_tools)
        self._mcp_tool_name_set = frozenset(
            str(getattr(t, "name", "") or "") for t in self._mcp_tools if getattr(t, "name", None)
        )

    def inject_mcp_tools(self, extra_tools: list[Any]) -> None:
        """Alias for :meth:`append_mcp_tools` (gateway in-process MCP injection)."""
        self.append_mcp_tools(extra_tools)

    async def seed_default_subagent(self) -> None:
        """Mirror harness init_workspace default subagent seed."""
        content = """---
name: General Purpose
description: General-purpose agent
---

# General Purpose
"""
        await self._workspace.aupload_bytes(
            "agents/general-purpose.md",
            content.encode("utf-8"),
        )

    def list_subagent_summaries(self) -> list[dict[str, Any]]:
        import asyncio
        import concurrent.futures

        async def _collect() -> list[dict[str, Any]]:
            from octop.infra.utils.frontmatter import parse_frontmatter

            paths: set[str] = set()
            agents_dir = self._workspace_dir / "agents"
            if agents_dir.is_dir():
                for fpath in agents_dir.glob("*.md"):
                    paths.add(f"agents/{fpath.name}")

            glob_result = await self._workspace.aglob("agents/*.md", ".")
            matches = getattr(glob_result, "matches", None) or []
            for m in matches:
                p = str(getattr(m, "path", m.get("path") if isinstance(m, dict) else "") or "")
                if p:
                    paths.add(p)
            out: list[dict[str, Any]] = []
            for path in sorted(paths):
                text = await self._workspace.aread_text(path)
                if not text:
                    fpath = self._workspace_dir / path
                    if fpath.is_file():
                        text = fpath.read_text(encoding="utf-8")
                if not text:
                    continue
                meta, _ = parse_frontmatter(text)
                slug = Path(path).stem
                row: dict[str, Any] = {
                    "slug": slug,
                    "name": str(meta.get("name") or slug),
                    "description": str(meta.get("description") or ""),
                    "path": path if path.startswith("agents/") else f"agents/{Path(path).name}",
                }
                if meta.get("emoji"):
                    row["emoji"] = meta["emoji"]
                out.append(row)
            return out

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_collect())

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(_collect())).result()

    def set_skills_disabled(
        self,
        disabled: set[str] | frozenset[str] | list[str] | None,
    ) -> None:
        """Hot-update disabled skills (mirrors harness_agent.HarnessAgent)."""
        self.config.skills_disabled = frozenset(str(x) for x in (disabled or ()))

    async def list_skill_summaries(self) -> list[dict[str, Any]]:
        """Mirror harness skill catalog: list workspace + builtin ``SKILL.md`` manifests.

        Skills are written via ``agent.workspace`` (the in-memory fake backend for
        tests, or the real disk-backed backend). Enumerate from whichever store holds
        them so the listed summaries match what the routers persisted.
        """
        from octop.infra.utils.frontmatter import parse_frontmatter

        collected: dict[str, str] = {}

        # In-memory fake backend store (skills are written here by the routers).
        files = getattr(self._backend, "_files", None)
        if isinstance(files, dict):
            for fpath, data in files.items():
                if not fpath.endswith(".md"):
                    continue
                if "/skills/" not in fpath and not fpath.startswith("_builtin_skills/"):
                    continue
                if isinstance(data, bytes):
                    try:
                        collected[fpath] = data.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                elif isinstance(data, str):
                    collected[fpath] = data

        # Real disk-backed workspace (e.g. when use_workspace_dir was called).
        for root in ("skills", "_builtin_skills"):
            disk_root = self._workspace_dir / root
            if disk_root.is_dir():
                for fpath in disk_root.rglob("*.md"):
                    rel = f"{root}/{fpath.relative_to(disk_root)}"
                    if rel not in collected:
                        try:
                            collected[rel] = fpath.read_text(encoding="utf-8")
                        except (OSError, UnicodeDecodeError):
                            continue

        disabled = frozenset(str(x) for x in getattr(self.config, "skills_disabled", frozenset()))
        # Merge by slug, mirroring the harness catalog: a workspace skill
        # overrides a builtin of the same slug (later roots win).
        merged: dict[str, dict[str, Any]] = {}
        for path in sorted(collected):
            meta, _ = parse_frontmatter(collected[path])
            # Slug is the skill directory name (parent of SKILL.md), matching the
            # harness catalog where ``skills/<slug>/SKILL.md`` is the layout.
            slug = Path(path).parent.name
            if not slug or slug.startswith("."):
                continue
            # Mirror harness: skip soft-deleted skills (``removed: true`` frontmatter).
            if meta.get("removed"):
                continue
            kind = "builtin" if path.startswith("_builtin_skills/") else "workspace"
            if slug in merged and not (merged[slug]["kind"] == "builtin" and kind == "workspace"):
                continue
            name = str(meta.get("name") or slug)
            is_disabled = slug in disabled or name in disabled
            row: dict[str, Any] = {
                "slug": slug,
                "name": name,
                "description": str(meta.get("description") or ""),
                "path": path,
                "kind": kind,
                "enabled": not is_disabled,
                "disabled": is_disabled,
            }
            # Mirror harness: emoji lives under metadata.{octop,lightclaw,orca,harness}.
            metadata = meta.get("metadata") or {}
            if isinstance(metadata, dict):
                for key in ("octop", "lightclaw", "orca", "harness"):
                    ext = metadata.get(key) or {}
                    if isinstance(ext, dict) and "emoji" in ext:
                        row["emoji"] = str(ext["emoji"])
                        break
            merged[slug] = row
        return sorted(
            merged.values(),
            key=lambda row: (0 if row["kind"] == "builtin" else 1, str(row["slug"])),
        )


class _FakeBackend:
    """In-memory backend supporting the harness BackendProtocol surface used by Octop routers."""

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    # --- legacy helpers (media backend) ---

    async def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data

    async def read_bytes(self, path: str) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]

    # --- BackendProtocol surface used by skills / workspace routers ---

    async def aupload_files(self, uploads: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        results = []
        for path, data in uploads:
            self._files[path] = data
            results.append(FileUploadResponse(path=path, error=None))
        return results

    async def aread(self, path: str) -> ReadResult:
        if path not in self._files:
            return ReadResult(error="not_found", file_data=None)
        try:
            content = self._files[path].decode("utf-8")
            return ReadResult(error=None, file_data={"content": content, "encoding": "utf-8"})
        except UnicodeDecodeError:
            return ReadResult(
                error=None, file_data={"content": self._files[path], "encoding": "binary"}
            )

    async def als(self, path: str) -> LsResult:
        prefix = path.rstrip("/") + "/"
        entries = []
        now = datetime.now(UTC).isoformat()
        seen_dirs: set[str] = set()
        for fpath, data in self._files.items():
            if not fpath.startswith(prefix):
                continue
            rel = fpath[len(prefix) :]
            if "/" in rel:
                subdir = prefix + rel.split("/")[0]
                if subdir not in seen_dirs:
                    seen_dirs.add(subdir)
                    entries.append({"path": subdir, "is_dir": True, "size": 0, "modified_at": now})
            else:
                entries.append(
                    {"path": fpath, "is_dir": False, "size": len(data), "modified_at": now}
                )
        return LsResult(error=None, entries=entries)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        results = []
        for path in paths:
            if path in self._files:
                results.append(
                    FileDownloadResponse(path=path, content=self._files[path], error=None)
                )
            else:
                results.append(FileDownloadResponse(path=path, content=b"", error="not_found"))
        return results

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        import fnmatch

        now = datetime.now(UTC).isoformat()
        matches = []
        for fpath, data in self._files.items():
            fname = fpath.rsplit("/", 1)[-1]
            if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(fpath, pattern):
                matches.append(
                    {"path": fpath, "is_dir": False, "size": len(data), "modified_at": now}
                )
        return GlobResult(error=None, matches=matches)

    async def agrep(self, pattern: str, path: str = "/") -> GrepResult:
        import re

        matches = []
        try:
            rx = re.compile(pattern)
        except re.error:
            return GrepResult(error=f"invalid pattern: {pattern}", matches=None)
        for fpath, data in self._files.items():
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append({"path": fpath, "line": lineno, "text": line})
        return GrepResult(error=None, matches=matches)


class LoopbackChannel(BaseChannel):
    """In-memory channel: tests push InboundMessage and collect MessageEvents."""

    channel_kind = "loopback"

    def __init__(self, channel_id: str = "loopback-1", **kwargs: Any) -> None:
        async def _noop_processor(
            msg: InboundMessage,
        ) -> AsyncIterator[MessageEvent]:
            return
            yield  # make it an async generator

        super().__init__(kwargs.get("processor", _noop_processor))
        self.channel_id = channel_id
        self._inbound: list[InboundMessage] = []
        self._outbound: list[MessageEvent] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send_text(self, session_id: str, text: str, **kwargs: Any) -> None:
        pass

    async def _send_content(self, session_id: str, content: Any, **kwargs: Any) -> None:
        pass

    async def _send_media(self, session_id: str, media_key: str, **kwargs: Any) -> None:
        pass

    def parse_inbound(self, payload: Any) -> InboundMessage | None:
        return None
