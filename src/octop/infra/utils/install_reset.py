"""Reset Octop application state without deleting the install runtime.

``scripts/install.sh`` puts the virtualenv at ``~/.octop/venv`` and the
launcher at ``~/.octop/bin``. ``init --force`` and ``clean --all`` used to
``rmtree`` the whole home and, with it, the interpreter that was running
the command.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Directory names reserved by the official installer.
RUNTIME_DIR_NAMES = frozenset({"venv", "bin"})


class InstallResetError(Exception):
    """Refusing to wipe a directory that *is* the running install."""


def _runtime_probes() -> list[Path]:
    probes = [Path(sys.prefix), Path(sys.executable)]
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        probes.append(Path(argv0))
    return probes


def _resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _contains_running_runtime(path: Path) -> bool:
    """True when *path* is, or contains, the interpreter running this process."""
    resolved = _resolve(path)
    if resolved is None:
        return False
    for probe in _runtime_probes():
        target = _resolve(probe)
        if target is None:
            continue
        if target == resolved:
            return True
        try:
            target.relative_to(resolved)
        except ValueError:
            continue
        else:
            return True
    return False


def root_is_runtime(root: Path) -> bool:
    """True when *root* is the virtualenv (or lives inside it), not its parent."""
    resolved = _resolve(root)
    if resolved is None or not root.exists():
        return False
    prefix = _resolve(Path(sys.prefix))
    if prefix is None:
        return False
    if resolved == prefix:
        return True
    try:
        resolved.relative_to(prefix)
    except ValueError:
        return False
    return True


def is_runtime_entry(path: Path) -> bool:
    """True for installer runtime dirs and anything holding this process."""
    return path.name in RUNTIME_DIR_NAMES or _contains_running_runtime(path)


def partition_install_root(root: Path) -> tuple[list[Path], list[Path]]:
    """Split *root* into ``(state, runtime)`` children. Missing root → empty."""
    if root_is_runtime(root):
        raise InstallResetError(
            f"{root} is the Octop install runtime. Refusing to delete it. "
            "Repair the CLI with: bash install.sh"
        )
    if not root.is_dir():
        return [], []
    state: list[Path] = []
    runtime: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if is_runtime_entry(child):
            runtime.append(child)
        else:
            state.append(child)
    return state, runtime


def remove_install_entry(path: Path) -> None:
    """Delete one state entry. Symlinks are unlinked, not followed."""
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def wipe_octop_state(root: Path) -> tuple[list[Path], list[Path]]:
    """Delete application state under *root*. Returns ``(removed, kept)``."""
    state, runtime = partition_install_root(root)
    for entry in state:
        remove_install_entry(entry)
    return state, runtime
