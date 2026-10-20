"""Public maintenance-document contracts, independent of dates and Git history."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "README.md",
    ROOT / "README_CN.md",
    ROOT / "docs" / "integrations.md",
    *sorted((ROOT / "docs" / "agent").glob("*.md")),
    ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md",
    ROOT / ".github" / "pull_request_template.md",
    ROOT / "plugins" / "openclaw" / "octopmemory" / "README.md",
    ROOT / "plugins" / "hermes" / "octopmemory" / "README.md",
    ROOT / "plugins" / "hermes" / "octopmemory" / "after-install.md",
]


def test_documentation_keeps_harness_and_one_integration_guide() -> None:
    assert {path.name for path in (ROOT / "docs").glob("*.md")} == {"integrations.md"}
    assert {path.name for path in (ROOT / "docs" / "agent").glob("*.md")} == {
        "HANDOFF.md",
        "PROJECT_MAP.md",
        "DECISIONS.md",
        "TEST_MATRIX.md",
        "KNOWN_RISKS.md",
        "GLOSSARY.md",
        "README_AUDIT.md",
    }
    assert not (ROOT / "CLAUDE.md").exists()
    assert (ROOT / "AGENTS.md").read_text(encoding="utf-8").startswith("# AGENTS.md\n")


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda path: path.name)
def test_public_docs_have_no_calendar_log_or_personal_paths(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    forbidden_patterns = {
        "calendar date": r"\b20\d{2}(?:[-/]\d{1,2}[-/]\d{1,2}|年\d{1,2}月\d{1,2}日|\d{4})\b",
        "personal home path": r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^\s/\\]+[/\\]",
        "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "access token": r"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,})\b",
    }
    for label, pattern in forbidden_patterns.items():
        # Report the category and path, never echo potentially sensitive matches.
        assert not re.search(pattern, text), f"{path.relative_to(ROOT)}: {label}"


@pytest.mark.parametrize("path", PUBLIC_FILES, ids=lambda path: path.name)
def test_public_doc_local_links_exist(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    targets = re.findall(r"\]\(([^)]+)\)", text)
    targets += re.findall(r"""(?:src|href)=["']([^"']+)["']""", text)
    for target in targets:
        parsed = urlsplit(target)
        repository_prefix = "/TencentCloud/octop-memory/blob/main/"
        if parsed.netloc == "github.com" and parsed.path.startswith(repository_prefix):
            destination = ROOT / unquote(parsed.path.removeprefix(repository_prefix))
        elif parsed.scheme or parsed.netloc or not parsed.path:
            continue
        else:
            destination = path.parent / unquote(parsed.path)
        destination = destination.resolve()
        assert destination.is_relative_to(ROOT), f"{path.relative_to(ROOT)}: link outside repository"
        assert destination.exists(), f"{path.relative_to(ROOT)}: broken local link {target}"
