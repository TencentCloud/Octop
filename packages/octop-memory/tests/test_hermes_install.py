"""Unit tests for the Hermes standalone installer's install/activate helpers.

These pure functions back ``octop-memory-hermes install/doctor``
(``plugins/hermes/octopmemory/install_lib.py``). Testing them directly
covers the config-mutation edge cases without driving the full CLI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from octopmemory import install_lib as hi

REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_DIR = REPO_ROOT / "plugins" / "hermes" / "octopmemory"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-hermes-plugin.sh"

# Deliberately absent from the standalone plugin repo: it ships the Hermes-native
# `plugins install <git-url>` form, which has no copy+.pth installer. install_lib
# exists only to back installer.py, so it goes with it.
INSTALLER_ONLY_FILES = frozenset({"installer.py", "install_lib.py"})


class TestSetMemoryProvider:
    def test_empty_config_creates_block(self) -> None:
        assert hi.set_memory_provider("", "octopmemory") == "memory:\n  provider: octopmemory\n"

    def test_no_memory_block_appends(self) -> None:
        out = hi.set_memory_provider("model:\n  name: gpt\n", "octopmemory")
        assert out == "model:\n  name: gpt\nmemory:\n  provider: octopmemory\n"

    def test_no_memory_block_without_trailing_newline(self) -> None:
        out = hi.set_memory_provider("model:\n  name: gpt", "octopmemory")
        assert out == "model:\n  name: gpt\nmemory:\n  provider: octopmemory\n"

    def test_replaces_existing_provider_preserving_indent(self) -> None:
        out = hi.set_memory_provider("memory:\n    provider: honcho\n", "octopmemory")
        assert out == "memory:\n    provider: octopmemory\n"

    def test_inserts_provider_into_existing_memory_block(self) -> None:
        out = hi.set_memory_provider("memory:\n  memory_enabled: true\n", "octopmemory")
        assert "memory_enabled: true" in out
        assert "  provider: octopmemory" in out

    def test_provider_insert_stops_at_next_top_level_key(self) -> None:
        out = hi.set_memory_provider("memory:\n  memory_enabled: true\nmodel:\n  name: gpt\n", "octopmemory")
        # provider goes under memory:, not appended after model:
        lines = out.splitlines()
        assert lines.index("  provider: octopmemory") < lines.index("model:")


class TestReadMemoryProvider:
    def test_reads_provider(self) -> None:
        assert hi.read_memory_provider("memory:\n  provider: octopmemory\n") == "octopmemory"

    def test_strips_quotes(self) -> None:
        assert hi.read_memory_provider('memory:\n  provider: "honcho"\n') == "honcho"

    def test_none_when_no_memory_block(self) -> None:
        assert hi.read_memory_provider("model:\n  name: gpt\n") is None

    def test_none_when_provider_unset(self) -> None:
        assert hi.read_memory_provider("memory:\n  memory_enabled: true\n") is None

    def test_roundtrip_with_set(self) -> None:
        text = hi.set_memory_provider("model:\n  name: gpt\n", "octopmemory")
        assert hi.read_memory_provider(text) == "octopmemory"


class TestActivateProvider:
    def test_creates_config_without_backup(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yaml"
        backup = hi.activate_provider(config)
        assert backup is None
        assert hi.read_memory_provider(config.read_text(encoding="utf-8")) == "octopmemory"

    def test_backs_up_existing_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yaml"
        config.write_text("memory:\n  provider: honcho\n", encoding="utf-8")
        backup = hi.activate_provider(config)
        assert backup is not None and backup.exists()
        assert "honcho" in backup.read_text(encoding="utf-8")
        assert hi.read_memory_provider(config.read_text(encoding="utf-8")) == "octopmemory"


class TestMissingPluginFiles:
    def test_all_present(self, tmp_path: Path) -> None:
        for name in hi.REQUIRED_PLUGIN_FILES:
            (tmp_path / name).write_text("x", encoding="utf-8")
        assert hi.missing_plugin_files(tmp_path) == []

    def test_reports_missing(self, tmp_path: Path) -> None:
        (tmp_path / "__init__.py").write_text("x", encoding="utf-8")
        missing = hi.missing_plugin_files(tmp_path)
        assert set(missing) == {"cli.py", "plugin.yaml", "README.md"}


class TestPythonProbes:
    def test_site_packages_none_for_nonexistent(self, tmp_path: Path) -> None:
        assert hi.python_site_packages(tmp_path / "nope" / "python") is None

    def test_can_import_false_for_nonexistent(self, tmp_path: Path) -> None:
        assert hi.python_can_import_octop_memory(tmp_path / "nope" / "python") is False


def _build_script_file_list() -> list[str]:
    """Names in the ``files=( ... )`` array of scripts/build-hermes-plugin.sh."""
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"^files=\((.*?)^\)", text, re.MULTILINE | re.DOTALL)
    assert match is not None, f"could not find a files=( ... ) array in {BUILD_SCRIPT}"
    return [line.strip() for line in match.group(1).splitlines() if line.strip() and not line.strip().startswith("#")]


class TestStandalonePluginRepoManifest:
    """Guard the monorepo -> standalone Hermes plugin repo copy against drift.

    The provider ships through two channels with *different* inclusion rules:
    the wheel packages the whole ``octopmemory/`` directory automatically,
    while ``build-hermes-plugin.sh`` copies a hand-maintained allowlist. A new
    module added to the provider therefore lands in the wheel silently and is
    silently dropped from the standalone repo — where it surfaces as an
    ImportError no monorepo test would ever hit.
    """

    @pytest.mark.parametrize("name", sorted(_build_script_file_list()))
    def test_listed_file_exists(self, name: str) -> None:
        assert (PROVIDER_DIR / name).is_file(), (
            f"build-hermes-plugin.sh copies {name!r}, but it does not exist in {PROVIDER_DIR}. "
            f"The script runs under `set -e`, so this would fail the build."
        )

    def test_every_shipped_file_is_listed(self) -> None:
        listed = set(_build_script_file_list())
        actual = {
            path.name
            for path in PROVIDER_DIR.iterdir()
            if path.is_file() and not path.name.endswith(".pyc") and path.name not in INSTALLER_ONLY_FILES
        }
        missing = actual - listed
        assert not missing, (
            f"{sorted(missing)} live in {PROVIDER_DIR} but are not copied by build-hermes-plugin.sh. "
            f"Add them to its files=() array, or add them to INSTALLER_ONLY_FILES if they are "
            f"deliberately excluded from the standalone plugin repo."
        )

    def test_required_plugin_files_are_all_shipped(self) -> None:
        listed = set(_build_script_file_list())
        assert set(hi.REQUIRED_PLUGIN_FILES) <= listed, (
            f"the standalone repo must contain every file doctor requires; "
            f"missing: {sorted(set(hi.REQUIRED_PLUGIN_FILES) - listed)}"
        )
