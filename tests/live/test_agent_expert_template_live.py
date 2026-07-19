"""Live tests for expert template file copy via :class:`AgentManager`.

Uses bundled templates under ``src/octop/infra/agents/experts/library/`` (exported
expert packs). Requires ``.env`` with ``OPENAI_*`` for agent boot.

Run::

    uv run pytest tests/live/test_agent_expert_template_live.py -m live -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.experts.catalog import Expert, ExpertCatalog, default_library_root
from octop.infra.agents.manager import AgentCreateSpec

pytestmark = pytest.mark.live


def _skill_expert_ids(catalog: ExpertCatalog) -> list[str]:
    ids: list[str] = []
    for summary in catalog.list_summaries():
        expert = catalog.get(summary.id)
        if expert is None:
            continue
        if any("skills/" in path and path.endswith(".md") for path in expert.files):
            ids.append(summary.id)
    return sorted(ids)


def _workspace_rel_path(rel_path: str) -> Path:
    return Path(rel_path.removeprefix("/"))


def _expert_text_contents(catalog: ExpertCatalog, expert_id: str) -> dict[str, str]:
    """Lazy-read expert seed file bodies (``Expert`` no longer eagerly stores them)."""
    return {item["name"]: item["content"] for item in catalog.read_file_contents(expert_id)}


@pytest.fixture(scope="session")
def expert_library() -> ExpertCatalog:
    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()
    assert catalog.list_summaries(), "expert library is empty"
    return catalog


@pytest.fixture(scope="session")
def skill_expert_ids(expert_library: ExpertCatalog) -> list[str]:
    ids = _skill_expert_ids(expert_library)
    assert ids, "expected at least one expert with skills/ in manifest"
    return ids


async def _assert_expert_files_on_disk(
    *,
    ws: Path,
    expert: Expert,
    expert_id: str,
    contents: dict[str, str],
) -> None:
    md_files = [f for f in expert.files if f.endswith(".md")]
    skill_files = [f for f in expert.files if f.startswith("skills/")]
    assert md_files, f"{expert_id}: manifest has no root .md files"
    assert skill_files, f"{expert_id}: manifest has no skills/ files"
    assert contents, f"{expert_id}: no readable text seeds"

    for rel_path, expected in contents.items():
        disk_path = ws / _workspace_rel_path(rel_path)
        assert disk_path.is_file(), f"{expert_id}: missing on disk: {rel_path}"
        actual = disk_path.read_text(encoding="utf-8")
        assert actual == expected, f"{expert_id}: content mismatch for {rel_path}"
        # Package markers (__init__.py) may be newline-only; other seeds must be substantive.
        if Path(rel_path).name != "__init__.py":
            assert len(actual.strip()) > 0, f"{expert_id}: empty file {rel_path}"


async def _assert_expert_files_via_workspace(
    *,
    agent: object,
    expert_id: str,
    contents: dict[str, str],
) -> None:
    """Compare exact bytes via ``adownload_bytes``.

    ``aread_text`` injects a ``System reminder`` for empty/whitespace-only files
    (e.g. package ``__init__.py``), so it is not a faithful copy check.
    """
    workspace = agent.workspace  # type: ignore[attr-defined]
    for rel_path, expected in contents.items():
        rel = rel_path.lstrip("/")
        raw = await workspace.adownload_bytes(rel)
        assert raw is not None, f"{expert_id}: workspace missing {rel}"
        actual = raw.decode("utf-8")
        assert actual == expected, f"{expert_id}: workspace mismatch for {rel}"


@pytest.mark.asyncio
async def test_skill_experts_copy_md_and_skill_files(
    live_agent_manager,
    live_openai_config,
    expert_library: ExpertCatalog,
    skill_expert_ids: list[str],
) -> None:
    """Each bundled skill expert copies every manifest file (md + skill tree)."""
    assert "stock-assistant" in skill_expert_ids
    assert "news-trend" in skill_expert_ids
    assert "wechat-ops" in skill_expert_ids

    for expert_id in skill_expert_ids:
        expert = expert_library.get(expert_id)
        assert expert is not None
        contents = _expert_text_contents(expert_library, expert_id)

        row = await live_agent_manager.create(
            AgentCreateSpec(
                name=f"live-{expert_id}",
                default_model=live_openai_config.default_model,
                template_name=expert_id,
            ),
        )
        try:
            assert live_agent_manager.get_row(row.agent_id).last_state == "running"
            ws = live_agent_manager._paths.agent_workspace(row.agent_id)
            assert (ws / "AGENTS.md").is_file(), f"{expert_id}: harness seed AGENTS.md missing"

            await _assert_expert_files_on_disk(
                ws=ws,
                expert=expert,
                expert_id=expert_id,
                contents=contents,
            )

            agent = live_agent_manager.get_agent(row.agent_id)
            await _assert_expert_files_via_workspace(
                agent=agent,
                expert_id=expert_id,
                contents=contents,
            )

            skill_md = [f for f in expert.files if f.endswith("SKILL.md")]
            for rel in skill_md:
                assert (ws / _workspace_rel_path(rel)).is_file(), (
                    f"{expert_id}: SKILL.md not copied: {rel}"
                )
        finally:
            await live_agent_manager.delete(row.agent_id)


@pytest.mark.asyncio
async def test_wechat_ops_copies_skill_scripts(
    live_agent_manager,
    live_openai_config,
    expert_library: ExpertCatalog,
) -> None:
    """Non-markdown skill assets (scripts, yaml) land in workspace."""
    expert = expert_library.get("wechat-ops")
    assert expert is not None

    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="live-wechat-ops",
            default_model=live_openai_config.default_model,
            template_name="wechat-ops",
        ),
    )
    try:
        ws = live_agent_manager._paths.agent_workspace(row.agent_id)
        contents = _expert_text_contents(expert_library, "wechat-ops")
        for rel in (
            "skills/publisher-multi-platform/scripts/wechat_publish.py",
            "skills/publisher-multi-platform/manifest.yaml",
        ):
            path = ws / rel
            assert path.is_file(), rel
            assert path.stat().st_size > 0
            assert rel in contents, f"missing seed text for {rel}"
            assert path.read_text(encoding="utf-8") == contents[rel]
    finally:
        await live_agent_manager.delete(row.agent_id)


@pytest.mark.asyncio
async def test_stock_assistant_skill_references_copied(
    live_agent_manager,
    live_openai_config,
    expert_library: ExpertCatalog,
) -> None:
    expert = expert_library.get("stock-assistant")
    assert expert is not None

    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="live-stock",
            default_model=live_openai_config.default_model,
            template_name="stock-assistant",
        ),
    )
    try:
        ws = live_agent_manager._paths.agent_workspace(row.agent_id)
        contents = _expert_text_contents(expert_library, "stock-assistant")
        for rel in (
            "SOUL.md",
            "IDENTITY.md",
            "skills/stock-info/SKILL.md",
            "skills/stock-info/references/examples.md",
        ):
            disk = ws / rel
            assert disk.is_file(), rel
            assert rel in contents, f"missing seed text for {rel}"
            assert disk.read_text(encoding="utf-8") == contents[rel]
    finally:
        await live_agent_manager.delete(row.agent_id)


@pytest.mark.asyncio
async def test_expert_agent_can_reply_after_template_copy(
    live_agent_manager,
    live_openai_config,
) -> None:
    row = await live_agent_manager.create(
        AgentCreateSpec(
            name="live-news",
            default_model=live_openai_config.default_model,
            template_name="news-trend",
            system_prompt="Reply with exactly one word: ok",
        ),
    )
    try:
        agent = live_agent_manager.get_agent(row.agent_id)
        reply = await agent.call("ping")
        assert reply is not None
        assert len(str(reply).strip()) > 0
    finally:
        await live_agent_manager.delete(row.agent_id)
