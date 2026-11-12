"""@ mention file index lists through the workspace backend and stays bounded."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.backend.mention_index import (
    clear_mention_index_cache,
    collect_mention_paths,
    list_workspace_mention_paths,
)


@pytest.fixture(autouse=True)
def _clear_mention_cache() -> None:
    clear_mention_index_cache()


class _Result:
    def __init__(self, entries: list[dict[str, object]]) -> None:
        self.entries = entries


class _Workspace:
    def __init__(self, tree: dict[str, list[dict[str, object]]]) -> None:
        self.tree = tree
        self.calls: list[str] = []

    async def als(self, path: str) -> _Result:
        self.calls.append(path)
        return _Result(self.tree.get(path, []))


async def test_index_skips_heavy_dirs_and_keeps_nested_files() -> None:
    workspace = _Workspace(
        {
            ".": [
                {"path": "SOUL.md", "is_dir": False},
                {"path": "docs", "is_dir": True},
                {"path": "node_modules", "is_dir": True},
                {"path": ".octop", "is_dir": True},
            ],
            "docs": [
                {"path": "docs/api.md", "is_dir": False},
            ],
        }
    )

    paths, truncated = await list_workspace_mention_paths(workspace)

    assert paths == ["SOUL.md", "docs/api.md"]
    assert truncated is False
    assert "node_modules" not in workspace.calls
    assert ".octop" not in workspace.calls


async def test_index_reanchors_basename_rows() -> None:
    workspace = _Workspace(
        {
            ".": [{"path": "docs", "is_dir": True}],
            "docs": [{"path": "api.md", "is_dir": False}],
        }
    )

    paths, truncated = await list_workspace_mention_paths(workspace)

    assert paths == ["docs/api.md"]
    assert truncated is False


async def test_index_stops_at_the_file_cap() -> None:
    workspace = _Workspace(
        {
            ".": [{"path": f"f{index}.txt", "is_dir": False} for index in range(5)],
        }
    )

    paths, truncated = await list_workspace_mention_paths(workspace, limit=2)

    assert len(paths) == 2
    assert truncated is True


async def test_index_stops_at_the_directory_cap() -> None:
    workspace = _Workspace(
        {
            ".": [
                {"path": "a.txt", "is_dir": False},
                {"path": "nested", "is_dir": True},
            ],
            "nested": [
                {"path": "nested/b.txt", "is_dir": False},
                {"path": "nested/deeper", "is_dir": True},
            ],
            "nested/deeper": [
                {"path": "nested/deeper/c.txt", "is_dir": False},
            ],
        }
    )

    paths, truncated = await list_workspace_mention_paths(workspace, max_dirs=2)

    assert paths == ["a.txt", "nested/b.txt"]
    assert truncated is True
    assert "nested/deeper" not in workspace.calls


async def test_missing_als_does_not_scan_the_host_tree(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")

    class _Bare:
        def __init__(self, root: Path) -> None:
            self.workspace_dir = root
            self.backend = object()

    paths, truncated = await collect_mention_paths(_Bare(tmp_path))

    assert paths == []
    assert truncated is False
    assert (tmp_path / "secret.txt").is_file()


async def test_collect_uses_als_and_ignores_extra_host_files(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("x", encoding="utf-8")
    workspace = _Workspace({".": [{"path": "keep.txt", "is_dir": False}]})
    workspace.workspace_dir = tmp_path  # type: ignore[attr-defined]

    paths, truncated = await collect_mention_paths(workspace)

    assert paths == ["keep.txt"]
    assert truncated is False


async def test_collect_coalesces_concurrent_calls_and_then_uses_the_cache() -> None:
    import asyncio

    workspace = _Workspace({".": [{"path": "SOUL.md", "is_dir": False}]})

    first, second = await asyncio.gather(
        collect_mention_paths(workspace),
        collect_mention_paths(workspace),
    )
    third = await collect_mention_paths(workspace)

    assert first == second == third == (["SOUL.md"], False)
    assert workspace.calls == ["."]


async def test_collect_refreshes_after_the_cache_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "octop.infra.backend.mention_index.time.monotonic",
        lambda: clock["now"],
    )
    workspace = _Workspace({".": [{"path": "SOUL.md", "is_dir": False}]})

    await collect_mention_paths(workspace)
    clock["now"] = 131.0
    await collect_mention_paths(workspace)

    assert workspace.calls == [".", "."]
