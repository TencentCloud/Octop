"""Tests for Memory behavior when langgraph is not installed.

These tests mock the absence of langgraph to verify graceful degradation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestWithoutLanggraph:
    """Test that Memory works for non-checkpointer features when langgraph is unavailable."""

    def test_memory_core_features_work_without_checkpointer(self, tmp_path: Path) -> None:
        """Even if _checkpointer is None, memory features still work."""
        from octop_memory.core import Memory

        memory = Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})
        # Forcibly set checkpointer to None (simulating no-langgraph scenario)
        memory._checkpointer = None

        # Memory features still work
        node = memory.store("test content", topic="test")
        assert node.content == "test content"

        results = memory.recall("test")
        assert len(results) >= 1

    def test_checkpointer_methods_raise_import_error(self, tmp_path: Path) -> None:
        """Checkpointer methods raise clear ImportError when langgraph unavailable."""
        from octop_memory.core import Memory

        memory = Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})
        # Simulate langgraph not available
        memory._checkpointer = None

        with patch("octop_memory.core._LANGGRAPH_AVAILABLE", False):
            with pytest.raises(ImportError, match="octop-memory\\[langgraph\\]"):
                memory.get_tuple({"configurable": {"thread_id": "t1"}})

            with pytest.raises(ImportError, match="octop-memory\\[langgraph\\]"):
                memory.list_threads()

            with pytest.raises(ImportError, match="octop-memory\\[langgraph\\]"):
                memory.get_thread_state("t1")

            with pytest.raises(ImportError, match="octop-memory\\[langgraph\\]"):
                memory.delete_thread("t1")

    def test_sqlite_backend_suggests_langgraph_extra(self, tmp_path: Path) -> None:
        """SQLite backend should suggest installing octop-memory[langgraph]."""
        from octop_memory.core import Memory

        memory = Memory(namespace="test", backend_config={"db_path": str(tmp_path / "test.sqlite")})
        memory._checkpointer = None

        with patch("octop_memory.core._LANGGRAPH_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                memory.get_tuple({"configurable": {"thread_id": "t1"}})
            # The SQLite backend should suggest [langgraph], not [langgraph-postgres].
            assert "langgraph-postgres" not in str(exc_info.value)
            assert "octop-memory[langgraph]" in str(exc_info.value)
