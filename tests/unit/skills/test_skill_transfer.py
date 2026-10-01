from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.skills.skill_transfer import (
    SkillTransferNotFound,
    copy_workspace_skill_to_workspace,
)


class _MemWorkspace:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})

    async def aread_text(self, path: str) -> str | None:
        raw = self.files.get(path)
        return None if raw is None else raw.decode("utf-8")

    async def adownload_bytes(self, path: str) -> bytes | None:
        return self.files.get(path)

    async def aexists(self, path: str) -> bool:
        if path in self.files:
            return True
        prefix = path.rstrip("/") + "/"
        return any(key.startswith(prefix) for key in self.files)

    async def adelete(self, path: str) -> None:
        prefix = path if path.endswith("/") else f"{path}/"
        for key in list(self.files):
            if key == path or key.startswith(prefix):
                del self.files[key]

    async def amkdir(self, _path: str) -> None:
        return None

    async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        for path, content in pairs:
            self.files[path] = content

    async def als(self, path: str) -> SimpleNamespace:
        prefix = path.rstrip("/") + "/"
        children: dict[str, bool] = {}
        for key in self.files:
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            name = rest.split("/", 1)[0]
            children[name] = "/" in rest
        return SimpleNamespace(
            entries=[
                SimpleNamespace(path=f"{path.rstrip('/')}/{name}", is_dir=is_dir)
                for name, is_dir in children.items()
            ]
        )


@pytest.mark.asyncio
async def test_copy_workspace_skill_copies_sibling_files() -> None:
    source = _MemWorkspace(
        {
            "skills/pack/SKILL.md": b"---\nname: pack\n---\n# Pack\n",
            "skills/pack/refs/note.md": b"keep me",
        }
    )
    dest = _MemWorkspace()
    slug = await copy_workspace_skill_to_workspace(
        source=source,
        destination=dest,
        slug="pack",
    )
    assert slug == "pack"
    assert dest.files["skills/pack/SKILL.md"].startswith(b"---")
    assert dest.files["skills/pack/refs/note.md"] == b"keep me"


@pytest.mark.asyncio
async def test_copy_workspace_skill_missing_source() -> None:
    with pytest.raises(SkillTransferNotFound):
        await copy_workspace_skill_to_workspace(
            source=_MemWorkspace(),
            destination=_MemWorkspace(),
            slug="missing",
        )
