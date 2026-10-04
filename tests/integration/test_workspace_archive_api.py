"""Workspace archives must leave the shared HTTP event loop responsive."""

from __future__ import annotations

import asyncio
import io
import threading
import zipfile
from typing import Any

import pytest

from octop.infra.backup import workspace_archive


@pytest.mark.parametrize("stage", ["compress", "finalize", "extract", "clear"])
async def test_workspace_archive_keeps_other_requests_responsive(
    env_with_agent: Any,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    client, server, auth, agent_id = env_with_agent
    workspace = server.app_runtime.agent_registry.get_agent(agent_id).workspace
    await workspace.aupload_bytes("archive-notes.txt", b"original notes")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("archive-notes.txt", b"restored notes")
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    observed: list[tuple[bool, bool]] = []

    def check_responsiveness() -> None:
        if observed:
            return
        # Keep this archive stage busy until a separate, real HTTP request finishes.
        # Inline execution prevents the loop from processing that request.
        other_request = asyncio.run_coroutine_threadsafe(
            client.get("/api/settings/timezone", headers=auth), loop
        )
        try:
            response = other_request.result(timeout=3)
            responsive = response.status_code == 200
        except TimeoutError:
            responsive = False
        finally:
            other_request.cancel()
        observed.append((threading.get_ident() != loop_thread, responsive))

    if stage in ("compress", "finalize"):
        if stage == "compress":
            original_write = zipfile.ZipFile.writestr

            def write(archive: zipfile.ZipFile, *args: Any, **kwargs: Any) -> None:
                check_responsiveness()
                original_write(archive, *args, **kwargs)

            monkeypatch.setattr(zipfile.ZipFile, "writestr", write)
        else:
            original_close = zipfile.ZipFile.close

            def close(archive: zipfile.ZipFile) -> None:
                if archive.mode == "w" and archive.fp is not None:
                    check_responsiveness()
                original_close(archive)

            monkeypatch.setattr(zipfile.ZipFile, "close", close)

        response = await client.get(f"/api/agents/{agent_id}/workspace/archive", headers=auth)
        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.read("archive-notes.txt") == b"original notes"
    else:
        function_name = "_iter_zip_entries" if stage == "extract" else "_clear_local_workspace"
        original = getattr(workspace_archive, function_name)

        def blocking_stage(*args: Any, **kwargs: Any) -> Any:
            check_responsiveness()
            return original(*args, **kwargs)

        monkeypatch.setattr(workspace_archive, function_name, blocking_stage)
        response = await client.post(
            f"/api/agents/{agent_id}/workspace/archive",
            params={"mode": "merge" if stage == "extract" else "replace"},
            files={"file": ("workspace.zip", buffer.getvalue(), "application/zip")},
            headers=auth,
        )
        assert response.status_code == 200, response.text
        assert response.json()["imported"] == 1
        assert await workspace.adownload_bytes("archive-notes.txt") == b"restored notes"

    assert observed == [(True, True)], f"archive {stage} blocked the shared HTTP event loop"
