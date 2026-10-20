from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_provider_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "plugins" / "hermes" / "octopmemory" / "__init__.py"
    spec = importlib.util.spec_from_file_location("octopmemory_hermes_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_cli_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "plugins" / "hermes" / "octopmemory" / "cli.py"
    spec = importlib.util.spec_from_file_location("octopmemory_hermes_cli_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_installer_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "plugins" / "hermes" / "octopmemory" / "installer.py"
    spec = importlib.util.spec_from_file_location("octopmemory_hermes_installer_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mod = _load_provider_module()
_cli_mod = _load_cli_module()
_installer_mod = _load_installer_module()
OctopMemoryProvider = _mod.OctopMemoryProvider
register = _mod.register


def test_register_captures_provider() -> None:
    class Ctx:
        def __init__(self) -> None:
            self.provider = None

        def register_memory_provider(self, provider: object) -> None:
            self.provider = provider

    ctx = Ctx()
    register(ctx)

    assert isinstance(ctx.provider, OctopMemoryProvider)


def test_provider_initializes_and_exposes_tools(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()

    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    assert provider.name == "octopmemory"
    assert provider.is_available() is True
    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
    assert {"memory_search", "memory_get"}.issubset(tool_names)


def test_config_schema_exposes_effective_recall_capture_privacy_fields() -> None:
    keys = {field["key"] for field in OctopMemoryProvider().get_config_schema()}

    assert {
        "profile",
        "namespace",
        "db_path",
        "recall.raw_policy",
        "recall.default_max_results",
        "recall.default_corpus",
        "recall.layer_order",
        "capture.include_roles",
        "capture.min_message_chars",
        "capture.include_tool_results",
        "capture.skip_memory_echo",
        "capture.host_files_watcher",
        "host_files_root",
        "host_files_allow",
        "privacy.redact_secrets",
        "privacy.redact_patterns",
        "privacy.store_raw_content",
        "privacy.store_tool_payloads",
    }.issubset(keys)


def test_save_config_expands_dotted_keys_and_coerces_values(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()

    provider.save_config(
        {
            "profile": "privacy",
            "namespace": "hermes__custom",
            "recall.raw_policy": "never",
            "recall.default_max_results": "3",
            "recall.default_corpus": "memory",
            "recall.layer_order": "atom,page,raw",
            "capture.include_roles": "user,tool",
            "capture.min_message_chars": "25",
            "capture.include_tool_results": "true",
            "capture.skip_memory_echo": "false",
            "privacy.redact_secrets": "false",
            "privacy.redact_patterns": "internal-[A-Z]+,secret-[0-9]+",
            "privacy.store_raw_content": "false",
            "privacy.store_tool_payloads": "true",
        },
        str(tmp_path),
    )

    saved = json.loads((tmp_path / "octopmemory.json").read_text(encoding="utf-8"))
    assert saved["profile"] == "privacy"
    assert saved["namespace"] == "hermes__custom"
    assert saved["recall"] == {
        "raw_policy": "never",
        "default_max_results": 3,
        "default_corpus": "memory",
        "layer_order": ["atom", "page", "raw"],
    }
    assert saved["capture"] == {
        "include_roles": ["user", "tool"],
        "min_message_chars": 25,
        "include_tool_results": True,
        "skip_memory_echo": False,
    }
    assert saved["privacy"] == {
        "redact_secrets": False,
        "redact_patterns": ["internal-[A-Z]+", "secret-[0-9]+"],
        "store_raw_content": False,
        "store_tool_payloads": True,
    }


def test_sync_turn_writes_searchable_raw_events(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    provider.sync_turn(
        "Please remember Hermes adapter uses MemoryProvider.",
        "Confirmed: Hermes adapter uses MemoryProvider for memory integration.",
        session_id="sess_1",
    )
    provider.shutdown()

    result = json.loads(
        provider.handle_tool_call(
            "memory_search",
            {"query": "Hermes adapter MemoryProvider", "maxResults": 5},
        )
    )
    assert result["hits"]
    assert result["hits"][0]["path"].startswith("raw/")


def test_memory_get_returns_json_string(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")
    provider.sync_turn("Hermes MemoryProvider source text", "Assistant reply long enough", session_id="sess_1")
    provider.shutdown()

    search = json.loads(provider.handle_tool_call("memory_search", {"query": "Hermes MemoryProvider"}))
    path = search["hits"][0]["path"]
    got = json.loads(provider.handle_tool_call("memory_get", {"path": path, "from": 1, "lines": 20}))

    assert got["path"] == path
    assert "Hermes MemoryProvider" in got["excerpt"]


def test_queue_prefetch_is_noop(tmp_path: Path) -> None:
    # queue_prefetch is an intentional no-op: Hermes queues with the finished
    # turn's message but prefetch on the next turn runs with the new message,
    # so a query-keyed warm cache would never hit. It must not spawn work.
    provider = OctopMemoryProvider()
    assert provider.queue_prefetch("anything") is None
    assert provider._threads == []

    provider.initialize("sess_q", hermes_home=str(tmp_path), platform="cli")
    assert provider.queue_prefetch("still a no-op", session_id="sess_q") is None
    assert provider._threads == []
    provider.shutdown()


def test_on_session_switch_updates_id(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_a", hermes_home=str(tmp_path), platform="cli")

    provider.on_session_switch("sess_b")
    provider.shutdown()

    assert provider._session_id == "sess_b"


def test_shutdown_joins_threads_and_stops_host_files(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_s", hermes_home=str(tmp_path), platform="cli")
    provider.sync_turn(
        "Shutdown should join this Hermes background write thread.",
        "Acknowledged reply that is comfortably long enough.",
        session_id="sess_s",
    )
    assert provider._host_files is not None

    provider.shutdown()

    assert provider._threads == []
    assert provider._host_files is None


def test_prefetch_returns_memory_context(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")
    provider.sync_turn("Hermes prefetch should recall this MemoryProvider fact.", "Acknowledged.", session_id="sess_1")
    provider.shutdown()

    block = provider.prefetch("What did we say about Hermes MemoryProvider?", session_id="sess_1")

    assert "OctopMemory Recall" in block
    assert "MemoryProvider" in block


def test_hermes_host_files_default_to_memories_dir(tmp_path: Path) -> None:
    memories = tmp_path / "memories"
    (memories / "topics").mkdir(parents=True)
    (memories / "USER.md").write_text("User profile says Hermes prefers concise status updates.", encoding="utf-8")
    (memories / "topics" / "billing.md").write_text("Billing topic keeps renewal policy notes.", encoding="utf-8")

    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    try:
        search = json.loads(provider.handle_tool_call("memory_search", {"query": "renewal policy", "maxResults": 5}))
        assert any(hit["path"] == "topics/billing.md" for hit in search["hits"])

        got = json.loads(provider.handle_tool_call("memory_get", {"path": "USER.md"}))
        assert "concise status updates" in got["excerpt"]
    finally:
        provider.shutdown()


def test_on_memory_write_and_pre_compress_are_searchable(tmp_path: Path) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    provider.on_memory_write(
        "add",
        "memory",
        "Release window is Tuesday 14:00 and this Hermes memory write is long enough for default capture.",
        {"tool_name": "memory"},
    )
    contribution = provider.on_pre_compress(
        [{"role": "user", "content": "Compression should preserve the deployment runbook."}]
    )
    provider.shutdown()

    assert "OctopMemory" in contribution
    search = json.loads(provider.handle_tool_call("memory_search", {"query": "Release window Tuesday"}))
    assert search["hits"]


def test_sync_turn_respects_capture_filters(tmp_path: Path) -> None:
    (tmp_path / "octopmemory.json").write_text(
        json.dumps({"capture": {"include_roles": ["user"], "min_message_chars": 80}}),
        encoding="utf-8",
    )
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    provider.sync_turn(
        "Hermes capture filter keeps this long user message because it exceeds the configured length threshold.",
        "Hermes capture filter should drop this long assistant message even though it exceeds threshold.",
        session_id="sess_1",
    )
    provider.shutdown()

    events = provider._require_memory().list_raw(limit=10)
    assert len(events) == 1
    assert events[0].payload["role"] == "user"
    assert "long user message" in events[0].content


def test_sync_turn_respects_privacy_redaction(tmp_path: Path) -> None:
    (tmp_path / "octopmemory.json").write_text(
        json.dumps({"capture": {"min_message_chars": 0}, "privacy": {"redact_secrets": True}}),
        encoding="utf-8",
    )
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    provider.sync_turn(
        "Hermes privacy should redact api_key=supersecret123 before storing raw content.",
        "Acknowledged.",
        session_id="sess_1",
    )
    provider.shutdown()

    contents = [event.content for event in provider._require_memory().list_raw(limit=10)]
    assert any("[REDACTED]" in content for content in contents)
    assert all("supersecret123" not in content for content in contents)


def test_on_memory_write_respects_store_raw_content_false(tmp_path: Path) -> None:
    (tmp_path / "octopmemory.json").write_text(
        json.dumps({"capture": {"min_message_chars": 0}, "privacy": {"store_raw_content": False}}),
        encoding="utf-8",
    )
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")

    provider.on_memory_write(
        "add",
        "memory",
        "Do not persist this private Hermes memory body.",
        {"tool_name": "memory"},
    )

    events = provider._require_memory().list_raw(limit=10)
    assert len(events) == 1
    assert events[0].content == "[raw content disabled by privacy.store_raw_content=false]"
    assert events[0].payload["content_redacted"] is True


def test_provider_cli_search_and_show_use_active_store(tmp_path: Path, capsys) -> None:
    provider = OctopMemoryProvider()
    provider.initialize("sess_1", hermes_home=str(tmp_path), platform="cli")
    provider.sync_turn("Hermes CLI search show sentinel", "Acknowledged.", session_id="sess_1")
    provider.shutdown()

    _cli_mod._octopmemory_command(
        SimpleNamespace(
            octopmemory_command="search",
            query="Hermes CLI search show sentinel",
            max=5,
            corpus="all",
            hermes_home=str(tmp_path),
        )
    )
    search_output = capsys.readouterr().out

    assert "raw/" in search_output
    assert "Hermes CLI search show sentinel" in search_output
    path = next(line.split()[0] for line in search_output.splitlines() if line.startswith("raw/"))

    _cli_mod._octopmemory_command(
        SimpleNamespace(
            octopmemory_command="show",
            path=path,
            from_line=1,
            lines=20,
            corpus="all",
            hermes_home=str(tmp_path),
        )
    )
    show_output = capsys.readouterr().out

    assert path in show_output
    assert "Hermes CLI search show sentinel" in show_output


def test_installer_copies_provider_and_activates_config(tmp_path: Path) -> None:
    from click.testing import CliRunner

    hermes_home = tmp_path / "home"
    hermes_source = tmp_path / "hermes-agent"
    runner = CliRunner()

    result = runner.invoke(
        _installer_mod.main,
        [
            "install",
            "--hermes-home",
            str(hermes_home),
            "--hermes-source",
            str(hermes_source),
            "--no-write-pth",
        ],
    )

    assert result.exit_code == 0, result.output
    plugin_dir = hermes_source / "plugins" / "memory" / "octopmemory"
    assert (plugin_dir / "__init__.py").exists()
    assert (plugin_dir / "cli.py").exists()
    assert (plugin_dir / "plugin.yaml").exists()
    assert (plugin_dir / "README.md").exists()
    assert not (plugin_dir / "installer.py").exists()
    assert "provider: octopmemory" in (hermes_home / "config.yaml").read_text(encoding="utf-8")

    doctor = runner.invoke(
        _installer_mod.main,
        [
            "doctor",
            "--hermes-home",
            str(hermes_home),
            "--hermes-source",
            str(hermes_source),
        ],
    )
    assert doctor.exit_code == 0, doctor.output
