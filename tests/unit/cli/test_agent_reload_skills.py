"""`agent reload` should surface the workspace skill inventory (#1933).

Reload returns ok even when freshly written SKILL.md files only take effect
from the next turn; the CLI now prints what the workspace exposes so the
operator gets a verification hook instead of a blind ok.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[3] / "src" / "octop" / "cli" / "commands" / "agent.py"


def _ensure_octop_stub() -> None:
    """Minimal stand-ins for the two `octop.*` symbols agent.py imports."""
    root = Path(__file__).resolve().parent / "_stub_octop"
    pkgs = {
        "octop/__init__.py": "",
        "octop/cli/__init__.py": "",
        "octop/cli/support/__init__.py": "",
        "octop/cli/support/errors.py": (
            "class OctopError(Exception):\n"
            "    def __init__(self, message, code=None):\n"
            "        super().__init__(message)\n"
            "        self.code = code\n\n\n"
            "def fail_octop(exc):\n"
            "    raise SystemExit(str(exc))\n"
        ),
        "octop/infra/__init__.py": "",
        "octop/infra/errors.py": (
            "class ErrorCode:\n"
            "    AGENT_NOT_FOUND = 'agent_not_found'\n\n\n"
            "class OctopError(Exception):\n"
            "    def __init__(self, message, code=None):\n"
            "        super().__init__(message)\n"
            "        self.code = code\n"
        ),
    }
    for rel, body in pkgs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(body, encoding="utf-8")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def load_agent_cli():
    _ensure_octop_stub()
    spec = importlib.util.spec_from_file_location("agent_cli_under_test", FILES)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_cli_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "octop-home"
    skills = home / "agents" / "agt-1" / ".octop" / "skills"
    (skills / "alpha-skill").mkdir(parents=True)
    (skills / "alpha-skill" / "SKILL.md").write_text(
        "---\nname: alpha-skill\n---\nbody\n", encoding="utf-8"
    )
    (skills / "beta-skill").mkdir(parents=True)
    (skills / "beta-skill" / "SKILL.md").write_text(
        "---\nname: beta-skill\n---\nbody\n", encoding="utf-8"
    )
    # tombstoned skill: the router marks removals as `removed: true` frontmatter
    removed = skills / "gone-skill"
    removed.mkdir(parents=True)
    (removed / "SKILL.md").write_text("---\nremoved: true\n---\n", encoding="utf-8")
    # top-level workspace skills dir also counts
    top = home / "agents" / "agt-1" / "skills" / "top-skill"
    top.mkdir(parents=True)
    (top / "SKILL.md").write_text("---\nname: top-skill\n---\n", encoding="utf-8")
    monkeypatch.setenv("OCTOP_HOME", str(home))
    return home


def test_reload_lists_workspace_skills(fake_home, capsys):
    mod = load_agent_cli()
    mod._print_workspace_skills("agt-1")
    out = capsys.readouterr().out
    assert "skills in workspace (3)" in out
    assert "alpha-skill" in out and "beta-skill" in out and "top-skill" in out
    assert "gone-skill" not in out  # tombstone filtered


def test_reload_silent_when_no_skills(tmp_path, monkeypatch, capsys):
    (tmp_path / "octop-home" / "agents" / "empty-agent").mkdir(parents=True)
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "octop-home"))
    mod = load_agent_cli()
    mod._print_workspace_skills("empty-agent")
    assert capsys.readouterr().out == ""
