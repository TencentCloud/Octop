"""Store facts, build a tree and recall prompt context using the public API.

Run from a development checkout: uv run python examples/basic_usage.py
All data is synthetic and the temporary database is removed on exit.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from octop_memory import Memory, MemoryService
from octop_memory.storage.backends.sqlite import SqliteMemoryBackend


def main() -> None:
    with TemporaryDirectory(prefix="octop-memory-example-") as directory:
        backend = SqliteMemoryBackend(namespace="demo", db_path=Path(directory) / "memory.sqlite")
        try:
            memory = Memory(namespace="demo", backend=backend)
            root = memory.store("Project knowledge", level="root")
            preferences = memory.store("Preferences", level="branch", parent_id=root.id)
            architecture = memory.store("Architecture", level="branch", parent_id=root.id)

            # Public store() creates an AtomCard and a leaf reference together.
            memory.store("User prefers Python", topic="language", parent_id=preferences.id)
            memory.store("User runs pytest before committing", topic="workflow", parent_id=preferences.id)
            memory.store("Project uses SQLite storage", topic="database", parent_id=architecture.id)

            print("=== Memory tree ===")
            for node in memory.get_tree():
                print(f"[{node.level}] {node.content}")

            print("\n=== Recall facts about Python ===")
            for node in memory.recall("Python"):
                print(node.content)

            # FTS matches stored words; prompt recall needs no model client.
            print("\n=== Prompt context for SQLite storage ===")
            result = MemoryService(memory).recall("SQLite storage")
            print(result.rendered or "(no snippets)")
        finally:
            backend.close()


if __name__ == "__main__":
    main()
