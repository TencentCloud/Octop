"""Packaged supplements are installed as workspace skills."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.experts.supplements import install_supplements


async def test_install_supplements_copies_each_skill_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    alpha = tmp_path / "alpha" / "SKILL.md"
    beta = tmp_path / "beta" / "SKILL.md"
    alpha.parent.mkdir()
    beta.parent.mkdir()
    alpha.write_text("alpha body\n", encoding="utf-8", newline="\n")
    beta.write_text("beta body\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(
        "octop.infra.agents.experts.supplements.supplement_paths",
        lambda: [alpha, beta],
    )

    class _Workspace:
        def __init__(self) -> None:
            self.files = {"skills/alpha/SKILL.md": b"kept\n"}
            self.uploads = 0

        async def aexists(self, path: str) -> bool:
            return path in self.files

        async def aupload_many(self, pairs: list[tuple[str, bytes]]) -> None:
            self.uploads += 1
            for path, data in pairs:
                self.files[path] = data

    workspace = _Workspace()
    await install_supplements(workspace)
    assert workspace.files["skills/alpha/SKILL.md"] == b"kept\n"
    assert workspace.files["skills/beta/SKILL.md"] == b"beta body\n"
    await install_supplements(workspace)
    assert workspace.uploads == 1
