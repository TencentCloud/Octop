"""macOS native capture to the existing workspace attachment store."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from octop.infra.gateway.media.inbound_store import (
    INBOUND_EXTENSION_MEDIA_TYPES,
    write_inbound,
)

CaptureMode = Literal["scan", "photo", "album"]
_capture_lock = asyncio.Lock()


def helper_path() -> Path:
    configured = os.environ.get("OCTOP_NATIVE_CAPTURE_HELPER")
    return (
        Path(configured).expanduser()
        if configured
        else Path(__file__).parents[4]
        / "native/capture/OctopCapture.app/Contents/MacOS/OctopCapture"
    )


def capture_available() -> bool:
    return sys.platform == "darwin" and helper_path().is_file()


async def capture_from_composer(
    workspace: Any, mode: CaptureMode = "scan", *, max_bytes: int | None = None
) -> dict[str, Any]:
    if not await asyncio.to_thread(capture_available):
        return {"status": "unavailable", "files": []}
    if _capture_lock.locked():
        return {"status": "busy", "files": []}
    async with _capture_lock:
        return await _capture(workspace, mode, max_bytes)


async def _capture(workspace: Any, mode: CaptureMode, max_bytes: int | None) -> dict[str, Any]:
    session = uuid4().hex
    with tempfile.TemporaryDirectory(prefix="octop-capture-") as staging:
        process = await asyncio.create_subprocess_exec(str(helper_path()), mode, staging)
        try:
            await asyncio.wait_for(process.wait(), timeout=600)
        except TimeoutError:
            return {"status": "timeout", "files": []}
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        root = Path(staging)
        result_path = root / "result.json"
        if process.returncode != 0 or not result_path.is_file():
            return {"status": "error", "files": []}
        try:
            result = json.loads(await asyncio.to_thread(result_path.read_text))
            if result["status"] in ("cancelled", "error"):
                return {"status": result["status"], "files": []}
            if result["status"] != "ok" or not isinstance(result["files"], list):
                return {"status": "error", "files": []}
            # Validate all references before writing any workspace attachments.
            originals = [_output_file(root, name) for name in result["files"]]
            if any(file.suffix.lower() not in INBOUND_EXTENSION_MEDIA_TYPES for file in originals):
                return {"status": "error", "files": []}
            previews = result.get("previews", {})
            for name in result["files"]:
                if preview_name := previews.get(name):
                    _output_file(root, preview_name)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {"status": "error", "files": []}
        files = []
        for original in originals:
            name = original.name
            stored = await write_inbound(
                workspace,
                await asyncio.to_thread(_read_output, original, max_bytes),
                filename=f"capture-{session}-{name}",
                media_type=INBOUND_EXTENSION_MEDIA_TYPES[original.suffix.lower()],
                max_bytes=max_bytes,
            )
            preview_path = None
            if preview_name := previews.get(name):
                preview = _output_file(root, preview_name)
                thumbnail = await write_inbound(
                    workspace,
                    await asyncio.to_thread(_read_output, preview, max_bytes),
                    filename=f"capture-{session}-{preview_name}",
                    media_type="image/png",
                    max_bytes=max_bytes,
                )
                preview_path = thumbnail.path
            files.append(
                {
                    **asdict(stored),
                    "preview_path": preview_path,
                }
            )
        return {"status": "ok", "files": files}


def _output_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError("Invalid native capture output path")
    path = root / name
    if path.parent != root or path.is_symlink() or not path.is_file():
        raise ValueError("Invalid native capture output path")
    return path


def _read_output(path: Path, max_bytes: int | None) -> bytes:
    # write_inbound performs the standard upload-limit error mapping. Read at
    # most one byte beyond the limit so oversized imports cannot exhaust memory.
    with path.open("rb") as source:
        return source.read(max_bytes + 1) if max_bytes is not None else source.read()
