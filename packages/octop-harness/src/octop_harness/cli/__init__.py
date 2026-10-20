"""Harness Agent CLI — terminal interface.

Install with: pip install octop-harness[cli]
"""

from __future__ import annotations

from pathlib import Path

from octop_harness._version import __version__


def _check_cli_deps() -> None:
    """Raise ImportError if CLI dependencies are missing.

    Uses ImportError (not SystemExit) so importing ``octop_harness.cli.main``
    during test collection cannot abort the whole pytest session.
    The CLI entrypoint converts this into a friendly ``SystemExit``.
    """
    missing = []
    for mod in ("click", "rich", "prompt_toolkit", "dotenv"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise ImportError(
            f"Missing CLI dependencies: {', '.join(missing)}.\nInstall them with: pip install octop-harness[cli]"
        )


def load_dotenv_files(project_dir: Path, *, override: bool = False) -> Path | None:
    """Load the first .env file found (project dir → global ~/.octop-harness/).

    Args:
        project_dir: The current working directory to check for a project .env.
        override: If True, overwrite existing env vars (reload semantics).
                  If False (default), existing env vars take precedence.

    Returns:
        The Path of the .env file that was loaded, or None if none found.
    """
    from dotenv import load_dotenv

    candidates = [
        project_dir / ".env",
        Path.home() / ".octop-harness" / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=override)
            return path
    return None


__all__ = ["__version__", "_check_cli_deps", "load_dotenv_files"]
