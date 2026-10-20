"""CJK FTS segmentation (fts_text v2) — index + query + migration.

Regression suite for the unicode61 Han-run bug: contiguous Chinese text
used to be indexed as one giant token, so natural-language Chinese
queries (and even English words embedded in a Han run) matched nothing.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from octop_memory import Memory
from octop_memory.application.host_files import HostFilesIndex
from octop_memory.storage.backends.fts_text import FTS_TEXT_VERSION, fts_match_phrase, segment_cjk
from octop_memory.types import AtomCard


@pytest.fixture()
def memory(tmp_path: Path) -> Memory:
    return Memory(namespace="cjk", backend="sqlite", backend_config={"db_path": str(tmp_path / "m.sqlite")})


# ---------------------------------------------------------------------------
# Unit: segmentation helpers
# ---------------------------------------------------------------------------


class TestSegmentCjk:
    def test_han_run_gets_per_char_spaces(self) -> None:
        assert segment_cjk("部署方案") == " 部  署  方  案 "

    def test_ascii_untouched(self) -> None:
        assert segment_cjk("plain ascii-text_123") == "plain ascii-text_123"

    def test_mixed_keeps_latin_words_whole(self) -> None:
        out = segment_cjk("从docker切换")
        assert out is not None
        assert "docker" in out.split()

    def test_none_passthrough(self) -> None:
        assert segment_cjk(None) is None

    def test_match_phrase_escapes_quotes(self) -> None:
        assert fts_match_phrase('say "hi"') == '"say ""hi"""'


# ---------------------------------------------------------------------------
# Raw events / atom-backed tree projection in natural Chinese
# ---------------------------------------------------------------------------


class TestChineseRecall:
    def test_raw_substring_word(self, memory: Memory) -> None:
        memory.add_raw("用户决定把部署方案从docker切换到裸机部署因为性能问题", event_type="user_message")
        assert len(memory.search_raw("部署")) == 1
        assert len(memory.search_raw("性能问题")) == 1

    def test_raw_embedded_latin_word(self, memory: Memory) -> None:
        memory.add_raw("用户决定把部署方案从docker切换到裸机部署", event_type="user_message")
        assert len(memory.search_raw("docker")) == 1

    def test_raw_no_false_positive(self, memory: Memory) -> None:
        memory.add_raw("用户决定把部署方案从docker切换到裸机部署", event_type="user_message")
        assert memory.search_raw("不存在词汇") == []

    def test_atom_backed_tree_projection_chinese(self, memory: Memory) -> None:
        leaf = memory.store("用户偏好深色主题界面", topic="偏好")
        hits = memory.recall("深色主题")
        assert len(hits) == 1
        assert hits[0].atom_id == leaf.atom_id

    def test_atom_chinese(self, memory: Memory) -> None:
        event = memory.add_raw("我们决定数据库用sqlite不用postgres", event_type="user_message")
        now = datetime.now(UTC)
        memory.add_atom(
            AtomCard(
                id="atm_1",
                entity_id="ent_1",
                candidate_id="cand_1",
                raw_event_ids=[event.id],
                assertion="数据库选型用sqlite不用postgres",
                verbatim_quote="数据库用sqlite不用postgres",
                quote_event_id=event.id,
                search_terms=["数据库", "sqlite"],
                occurred_at=now,
                confidence="high",
                importance="high",
                created_at=now,
            )
        )
        assert len(memory.search_atoms("数据库")) == 1
        assert len(memory.search_atoms("sqlite")) == 1

    def test_english_phrase_behaviour_preserved(self, memory: Memory) -> None:
        memory.add_raw("we hit a performance issue in the deploy pipeline", event_type="user_message")
        assert len(memory.search_raw("performance issue")) == 1
        assert memory.search_raw("issue performance") == []  # phrase = adjacency, as before


# ---------------------------------------------------------------------------
# Legacy database migration (pre-v2 index → rebuilt on open)
# ---------------------------------------------------------------------------


class TestLegacyMigration:
    def test_v1_database_rebuilt_on_open(self, tmp_path: Path) -> None:
        db = tmp_path / "legacy.sqlite"
        m = Memory(namespace="t", backend="sqlite", backend_config={"db_path": str(db)})
        m.add_raw("用户决定把部署方案从docker切换到裸机部署", event_type="user_message")
        m.backend.close()

        # Downgrade to the v1 state: unsegmented FTS rows, unsegmented
        # trigger body, no version marker.
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO t_raw_events_fts(t_raw_events_fts) VALUES ('delete-all')")
        conn.execute("INSERT INTO t_raw_events_fts(rowid, content) SELECT rowid, content FROM t_raw_events")
        conn.execute("DELETE FROM t_meta WHERE key='fts_text_version'")
        conn.execute("DROP TRIGGER IF EXISTS t_raw_events_ai")
        conn.execute(
            "CREATE TRIGGER t_raw_events_ai AFTER INSERT ON t_raw_events BEGIN "
            "INSERT INTO t_raw_events_fts(rowid, content) VALUES (new.rowid, new.content); END"
        )
        conn.commit()
        conn.close()

        m2 = Memory(namespace="t", backend="sqlite", backend_config={"db_path": str(db)})
        # Old rows searchable after the automatic rebuild...
        assert len(m2.search_raw("部署")) == 1
        # ...and new writes go through the segmented trigger.
        m2.add_raw("会议改到周五下午", event_type="user_message")
        assert len(m2.search_raw("周五")) == 1
        row = m2.backend._conn.execute("SELECT value FROM t_meta WHERE key='fts_text_version'").fetchone()
        assert row[0] == FTS_TEXT_VERSION
        m2.backend.close()

    def test_reopen_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "m.sqlite"
        for _ in range(3):
            m = Memory(namespace="t", backend="sqlite", backend_config={"db_path": str(db)})
            m.backend.close()
        m = Memory(namespace="t", backend="sqlite", backend_config={"db_path": str(db)})
        m.add_raw("幂等性检查通过", event_type="user_message")
        assert len(m.search_raw("幂等")) == 1
        m.backend.close()


# ---------------------------------------------------------------------------
# Host files index
# ---------------------------------------------------------------------------


class TestHostFilesChinese:
    def test_chinese_search_in_memory_md(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "MEMORY.md").write_text("项目决定改用裸机部署方案", encoding="utf-8")
        index = HostFilesIndex(db_path=tmp_path / "hf.sqlite", namespace="hf")
        index.scan_once(workspace)
        hits = index.search("部署方案")
        assert [h.path for h in hits] == ["MEMORY.md"]
        index.stop()
