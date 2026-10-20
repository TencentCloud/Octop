"""Install/activate helpers for the standalone Hermes MemoryProvider installer.

Backs ``installer.py``'s ``install``/``doctor`` commands. Kept ``click``-free
(framework concerns stay in the CLI layer) and stdlib-only, so it introduces
no dependency beyond what this package already needs at runtime.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PLUGIN_ID = "octopmemory"
REQUIRED_PLUGIN_FILES = ("__init__.py", "cli.py", "plugin.yaml", "README.md")
DEFAULT_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def hermes_venv_python(hermes_source: Path) -> Path:
    """Path to the Python interpreter inside a Hermes source checkout's venv."""
    return hermes_source / "venv" / "bin" / "python"


def missing_plugin_files(source_dir: Path) -> list[str]:
    """Return the required plugin files absent from ``source_dir`` (empty = valid)."""
    return [name for name in REQUIRED_PLUGIN_FILES if not (source_dir / name).exists()]


def activate_provider(config_path: Path, provider: str = PLUGIN_ID) -> Path | None:
    """Set ``memory.provider`` in ``config.yaml``, backing up any existing file.

    Returns the backup path (``<config>.pre-octopmemory``) when an existing
    config was backed up, else ``None``.
    """
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    backup_path: Path | None = None
    if config_path.exists():
        backup_path = config_path.with_name(config_path.name + ".pre-octopmemory")
        backup_path.write_text(existing, encoding="utf-8")
    updated = set_memory_provider(existing, provider)
    config_path.write_text(updated, encoding="utf-8")
    return backup_path


def set_memory_provider(config_text: str, provider: str) -> str:
    """Return ``config_text`` with ``memory.provider`` set to ``provider``.

    Line-based on purpose: octop-memory avoids a yaml dependency for config
    mutation. Handles missing file, missing ``memory:`` block, existing
    ``provider:`` (in-place replace preserving indent), and no trailing
    newline.
    """
    lines = config_text.splitlines()
    if not lines:
        return f"memory:\n  provider: {provider}\n"

    memory_idx = next((idx for idx, line in enumerate(lines) if line == "memory:"), None)
    if memory_idx is None:
        suffix = "" if config_text.endswith("\n") else "\n"
        return config_text + suffix + f"memory:\n  provider: {provider}\n"

    block_end = len(lines)
    for idx in range(memory_idx + 1, len(lines)):
        line = lines[idx]
        if line and not line.startswith((" ", "\t")):
            block_end = idx
            break

    for idx in range(memory_idx + 1, block_end):
        if lines[idx].lstrip().startswith("provider:"):
            indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())] or "  "
            lines[idx] = f"{indent}provider: {provider}"
            return "\n".join(lines) + "\n"

    lines.insert(memory_idx + 1, f"  provider: {provider}")
    return "\n".join(lines) + "\n"


def read_memory_provider(config_text: str) -> str | None:
    """Return the ``memory.provider`` value from ``config_text``, or ``None``."""
    lines = config_text.splitlines()
    memory_idx = next((idx for idx, line in enumerate(lines) if line == "memory:"), None)
    if memory_idx is None:
        return None
    for line in lines[memory_idx + 1 :]:
        if line and not line.startswith((" ", "\t")):
            return None
        stripped = line.strip()
        if stripped.startswith("provider:"):
            value = stripped.partition(":")[2].strip()
            return value.strip("\"'") or None
    return None


def python_site_packages(python: Path) -> Path | None:
    """Return an existing site-packages dir for ``python``, or ``None``."""
    python = python.resolve()
    if not python.is_file():
        return None
    code = "import json, site; print(json.dumps(site.getsitepackages()))"
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        paths = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(paths, list):
        return None
    for item in paths:
        candidate = Path(str(item))
        if candidate.exists():
            return candidate
    return None


def python_can_import_octop_memory(python: Path) -> bool:
    """True if ``python`` can ``import octop_memory``."""
    python = python.resolve()
    if not python.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(python), "-c", "import octop_memory"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


__all__ = [
    "DEFAULT_HERMES_HOME",
    "PLUGIN_ID",
    "REQUIRED_PLUGIN_FILES",
    "activate_provider",
    "hermes_venv_python",
    "missing_plugin_files",
    "python_can_import_octop_memory",
    "python_site_packages",
    "read_memory_provider",
    "set_memory_provider",
]
