"""Turn-start SYSTEM / CONTEXT synthesis — must match harness injection SoT."""

from __future__ import annotations

from harness_agent.backends.workspace import DEFAULT_MEMORY_FILES

from octop.infra.trajectory.turn_context import (
    build_turn_start_chunks,
    filter_turn_skill_names,
    memory_file_order,
)


def test_memory_file_order_matches_harness_default_memory_files() -> None:
    assert memory_file_order() == list(DEFAULT_MEMORY_FILES)
    assert "USER.md" in memory_file_order()
    assert "SOUL.md" in memory_file_order()


def test_build_turn_start_includes_system_and_memory_skills_mcp() -> None:
    chunks = build_turn_start_chunks(
        include_system=True,
        system_prompt="You are Octop.\nBe helpful.",
        workspace_files=[
            ("AGENTS.md", "# Rules\nDo not invent APIs."),
            ("USER.md", "Name: Ada"),
        ],
        skills=["bash", "read"],
        mcp_servers=["github"],
    )
    kinds = [c["type"] for c in chunks]
    assert kinds == ["system", "context", "context", "context", "context"]
    assert chunks[0]["label"] == "Initial System Prompt"
    assert "You are Octop" in chunks[0]["content"]
    assert chunks[1]["source"] == "memory"
    assert chunks[1]["label"] == "AGENTS.md"
    assert chunks[2]["label"] == "USER.md"
    assert chunks[3]["source"] == "skills"
    assert "bash" in chunks[3]["content"]
    assert chunks[4]["source"] == "mcp"
    assert "github" in chunks[4]["content"]


def test_build_turn_start_skips_system_when_already_present() -> None:
    chunks = build_turn_start_chunks(
        include_system=False,
        system_prompt="You are Octop.",
        workspace_files=[],
        skills=["bash"],
        mcp_servers=None,
    )
    assert all(c["type"] != "system" for c in chunks)
    assert len(chunks) == 1
    assert chunks[0]["source"] == "skills"


def test_build_turn_start_skips_empty_system_prompt() -> None:
    """Empty DB/config prompt must not invent a SYSTEM row."""
    chunks = build_turn_start_chunks(
        include_system=True,
        system_prompt="  ",
        workspace_files=[("SOUL.md", "# Persona")],
        skills=None,
        mcp_servers=None,
    )
    assert [c["type"] for c in chunks] == ["context"]
    assert chunks[0]["label"] == "SOUL.md"
    assert chunks[0]["source"] == "memory"


def test_build_turn_start_emits_explicit_empty_skills_allowlist() -> None:
    chunks = build_turn_start_chunks(
        include_system=False,
        system_prompt=None,
        workspace_files=[],
        skills=[],
        mcp_servers=None,
        skills_filter_present=True,
    )
    assert len(chunks) == 1
    assert chunks[0]["source"] == "skills"
    assert chunks[0]["content"] == "(none)"


def test_filter_turn_skill_names_honours_allowlist_and_disabled() -> None:
    enabled = [
        {"name": "Bash", "slug": "bash"},
        {"name": "Read", "slug": "read"},
        {"name": "Write", "slug": "write"},
    ]
    assert filter_turn_skill_names(enabled, turn_skills=None, skills_filter_present=False) == [
        "Bash",
        "Read",
        "Write",
    ]
    # Allow-list may use slug (harness identity keys).
    assert filter_turn_skill_names(
        enabled, turn_skills=["read", "missing"], skills_filter_present=True
    ) == ["Read"]
    assert filter_turn_skill_names(enabled, turn_skills=[], skills_filter_present=True) == []
