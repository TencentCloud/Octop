from __future__ import annotations

from types import SimpleNamespace

import pytest

from octop.infra.agents.experts.composer_files import (
    ComposerWorkspacePatch,
    apply_composer_workspace_patch,
    composer_copies_from_payload,
    composer_patch_from_payload,
    normalize_composer_relpath,
)
from octop.infra.errors import ErrorCode, OctopError


@pytest.mark.parametrize(
    "name, expected",
    [
        ("AGENTS.md", "AGENTS.md"),
        ("/SOUL.md", "SOUL.md"),
        ("skills/demo/SKILL.md", "skills/demo/SKILL.md"),
        ("agents/reviewer.md", "agents/reviewer.md"),
        ("skills/demo", "skills/demo"),
    ],
)
def test_normalize_composer_relpath_accepts_editable_paths(name: str, expected: str) -> None:
    allow_dir = name.rstrip("/").count("/") == 1 and name.startswith("skills/")
    assert normalize_composer_relpath(name, allow_skill_dir=allow_dir) == expected


@pytest.mark.parametrize(
    "name",
    [".octop/secret", "../AGENTS.md", "skills/../x", "etc/passwd", ""],
)
def test_normalize_composer_relpath_rejects_unsafe_paths(name: str) -> None:
    with pytest.raises(OctopError) as exc:
        normalize_composer_relpath(name, allow_skill_dir=True)
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


def test_composer_patch_from_payload_roundtrip() -> None:
    patch = composer_patch_from_payload(
        file_overrides=[{"name": "AGENTS.md", "content": "hello"}],
        omit_files=["skills/old"],
        hub_skills=[{"skill_name": "writer", "display_name": "Writer"}],
    )
    assert patch.file_overrides == (("AGENTS.md", "hello"),)
    assert patch.omit_files == ("skills/old",)
    assert patch.hub_skills[0].skill_name == "writer"
    assert ComposerWorkspacePatch().is_empty()
    assert patch.is_empty() is False


class _FakeWorkspace:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(
            files
            or {
                "AGENTS.md": b"old",
                "skills/old/SKILL.md": b"gone",
            }
        )

    async def adelete(self, path: str) -> None:
        if path in self.files:
            del self.files[path]
            return
        prefix = path if path.endswith("/") else f"{path}/"
        for key in list(self.files):
            if key == path or key.startswith(prefix):
                del self.files[key]

    async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
        for path, content in pairs:
            self.files[path] = content

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

    async def amkdir(self, _path: str) -> None:
        return None

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
async def test_apply_composer_workspace_patch_writes_and_omits() -> None:
    workspace = _FakeWorkspace()
    await apply_composer_workspace_patch(
        workspace,
        composer_patch_from_payload(
            file_overrides=[{"name": "AGENTS.md", "content": "new guide"}],
            omit_files=["skills/old"],
            hub_skills=None,
        ),
    )
    assert workspace.files["AGENTS.md"] == b"new guide"
    assert "skills/old/SKILL.md" not in workspace.files


def test_composer_copies_from_payload_rejects_unsafe_source() -> None:
    with pytest.raises(OctopError) as exc:
        composer_copies_from_payload([{"agent_id": "../x", "slug": "demo"}])
    assert exc.value.code == ErrorCode.SLASH_BAD_ARGS


@pytest.mark.asyncio
async def test_hub_skill_failure_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(_name: str) -> list[tuple[str, bytes]]:
        raise RuntimeError("marketplace down")

    monkeypatch.setattr(
        "octop.infra.skills.skillhub_market.download_skillhub_package",
        boom,
    )
    workspace = _FakeWorkspace()
    report = await apply_composer_workspace_patch(
        workspace,
        composer_patch_from_payload(
            file_overrides=[{"name": "AGENTS.md", "content": "kept"}],
            omit_files=None,
            hub_skills=[{"skill_name": "writer"}],
        ),
    )
    assert workspace.files["AGENTS.md"] == b"kept"
    assert report.hub_skill_errors == ["writer"]
    assert report.as_api_fields() == {"hub_skill_errors": ["writer"]}


@pytest.mark.asyncio
async def test_apply_copies_full_skill_directory() -> None:
    source = _FakeWorkspace(
        {
            "skills/writer/SKILL.md": b"# Writer\n",
            "skills/writer/refs/note.md": b"extra",
        }
    )
    dest = _FakeWorkspace({"AGENTS.md": b"keep"})
    report = await apply_composer_workspace_patch(
        dest,
        ComposerWorkspacePatch(),
        copies=(("writer", source),),
    )
    assert dest.files["skills/writer/SKILL.md"] == b"# Writer\n"
    assert dest.files["skills/writer/refs/note.md"] == b"extra"
    assert report.copy_skill_errors == []


@pytest.mark.asyncio
async def test_copy_skill_failure_is_reported_not_raised() -> None:
    dest = _FakeWorkspace({"AGENTS.md": b"keep"})
    report = await apply_composer_workspace_patch(
        dest,
        ComposerWorkspacePatch(),
        copies=(("missing", _FakeWorkspace({})),),
    )
    assert report.copy_skill_errors == ["missing"]
    assert dest.files["AGENTS.md"] == b"keep"
