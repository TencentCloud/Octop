"""The composer's literal glob escapes must survive workspace normalization."""

from pathlib import Path

import pytest
from deepagents.backends.filesystem import FilesystemBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.api.routers import workspace


@pytest.mark.parametrize(
    ("filename", "decoy", "pattern"),
    [
        ("report[1].md", "report1.md", "**/*report[[]1[]]*"),
        ("draft{final}.md", "draftfinal.md", "**/*draft[{]final[}]*"),
        ("docs/report[1].md", "docs/report1.md", "**/docs/report[[]1[]]*"),
    ],
)
async def test_literal_mention_globs_reach_workspace_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str, decoy: str, pattern: str
) -> None:
    for name in (filename, decoy):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
    ws = BackendWorkspace(FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True), tmp_path)

    async def running_workspace(*args: object, **kwargs: object) -> BackendWorkspace:
        return ws

    monkeypatch.setattr(workspace, "require_running_workspace", running_workspace)
    rows = await workspace.glob_files(
        "agent", pattern, path="/", from_workspace=True, as_user=None, user=None, server=None
    )
    assert [row["path"] for row in rows] == [filename]
