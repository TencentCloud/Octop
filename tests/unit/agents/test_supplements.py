"""Packaged supplements are appended onto an expert AGENTS.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.experts.supplements import append_supplements


async def test_append_supplements_adds_each_file_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    alpha = tmp_path / "alpha" / "SKILL.md"
    beta = tmp_path / "beta" / "SKILL.md"
    alpha.parent.mkdir()
    beta.parent.mkdir()
    alpha.write_text("alpha body\n", encoding="utf-8")
    beta.write_text("beta body\n", encoding="utf-8")
    monkeypatch.setattr(
        "octop.infra.agents.experts.supplements.supplement_paths",
        lambda: [alpha, beta],
    )

    class _Workspace:
        def __init__(self) -> None:
            self.files = {
                "AGENTS.md": "# Expert\n\n<!-- octop:supplement:alpha -->\n\nalpha body\n"
            }
            self.writes = 0

        async def aread_text(self, path: str) -> str | None:
            return self.files.get(path)

        async def awrite_text(self, path: str, content: str, *, force: bool = True) -> None:
            self.writes += 1
            self.files[path] = content

    workspace = _Workspace()
    await append_supplements(workspace)
    text = workspace.files["AGENTS.md"]
    assert text.startswith("# Expert\n")
    assert text.count("<!-- octop:supplement:alpha -->") == 1
    assert "<!-- octop:supplement:beta -->" in text
    assert "beta body" in text
    await append_supplements(workspace)
    assert workspace.writes == 1
    assert workspace.files["AGENTS.md"] == text
