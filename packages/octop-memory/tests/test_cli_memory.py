"""Tests for the memory CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from octop_memory.adapters.cli import main
from octop_memory.core import Memory


class TestMemoryStore:
    def test_store_leaf_node(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "memory",
                "store",
                "--content",
                "User prefers Python",
                "--topic",
                "preferences",
            ],
        )
        assert result.exit_code == 0
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        tree = mem.get_tree()
        assert len(tree) == 1
        assert tree[0].content == "User prefers Python"
        assert tree[0].topic == "preferences"

    def test_store_with_parent(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        # Parent must be a branch (or root) — leaf cannot have children.
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "--json",
                "memory",
                "store",
                "--content",
                "Programming preferences",
                "--topic",
                "prefs",
                "--level",
                "branch",
            ],
        )
        assert result.exit_code == 0
        parent_data = json.loads(result.output)
        parent_id = parent_data["data"]["id"]
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "memory",
                "store",
                "--content",
                "Likes TDD",
                "--topic",
                "prefs",
                "--parent",
                parent_id,
            ],
        )
        assert result.exit_code == 0

    def test_store_json_output(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "--json",
                "memory",
                "store",
                "--content",
                "Test memory",
                "--topic",
                "test",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert "id" in data["data"]

    def test_store_from_stdin(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "memory",
                "store",
                "--content",
                "-",
                "--topic",
                "test",
            ],
            input="Memory from stdin",
        )
        assert result.exit_code == 0
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        tree = mem.get_tree()
        assert any(n.content == "Memory from stdin" for n in tree)


class TestMemoryTree:
    def test_tree_empty(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "memory", "tree"],
        )
        assert result.exit_code == 0

    def test_tree_json_output(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        mem.store("A test memory", topic="test")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "--json", "memory", "tree"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert len(data["data"]["nodes"]) >= 1


class TestMemoryRecall:
    def test_recall_finds_stored(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        mem.store("User likes sushi for lunch", topic="food")
        mem.store("User prefers Python", topic="code")
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--db", db_path, "--namespace", "test", "memory", "recall", "sushi"],
        )
        assert result.exit_code == 0
        assert "sushi" in result.output

    def test_recall_json_output(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        mem = Memory(namespace="test", backend_config={"db_path": db_path})
        mem.store("User likes testing", topic="dev")
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--db",
                db_path,
                "--namespace",
                "test",
                "--json",
                "memory",
                "recall",
                "testing",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
