"""Safe read/write helpers for the small JSON config files under ``OCTOP_HOME``.

Leaf module (AGENTS.md §5): stdlib only, no ``infra`` imports. Callers translate
:class:`JsonFileCorruptError` into ``OctopError`` via
``octop.infra.errors.corrupt_config_error``.

Both helpers exist because of issue #730: four call sites used to treat an
unparseable ``config.json`` as an empty dict and then wrote that back, silently
destroying every other key. One trailing comma plus one ``octop run --port``
wiped the ``database`` section and flipped a running PostgreSQL instance back to
a greenfield SQLite one, with no warning in the log. A torn write from a crash or
a full disk creates the same precondition without any user error, so writes here
are atomic too.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["JsonFileCorruptError", "read_json_object", "write_json_atomic"]


def _default_file_mode() -> int:
    """The mode a plain ``write_text`` would produce (``0o666 & ~umask``).

    POSIX has no get-only umask call, so read it by set-and-restore. Matches the
    two pre-existing config.json writers (``db/rebind.py``, ``backup/auto.py``)
    instead of leaving ``mkstemp``'s 0600, which would make a root-created
    config.json unreadable to the service user after
    ``octop service start --scope system``.
    """
    mask = os.umask(0o022)
    os.umask(mask)
    return 0o666 & ~mask


class JsonFileCorruptError(ValueError):
    """A JSON file exists but cannot be parsed into an object.

    Carries the path and the parser position only — never the file contents or
    any value from them, since ``config.json`` holds database credentials and
    secrets (precedent: ``octop.config`` refuses to log raw env values).
    """

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{path} is not valid JSON ({detail})")


def read_json_object(path: Path) -> dict[str, Any] | None:
    """Return the JSON object at ``path``, or ``None`` when the file is absent.

    Raises :class:`JsonFileCorruptError` when the file exists but is not valid
    JSON or is not a JSON object. Callers must **not** fall back to an empty
    dict: merging into ``{}`` and writing back is what destroys every other
    setting. An absent file is legitimate (first run) and yields ``None``.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise JsonFileCorruptError(path, "not valid UTF-8") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonFileCorruptError(path, f"line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(parsed, dict):
        raise JsonFileCorruptError(path, f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` as pretty JSON via temp file + ``os.replace``.

    Readers never observe a partially written file, so an interrupted write
    cannot leave the truncated JSON that :func:`read_json_object` then refuses
    to merge. The temp file is unique per call (``mkstemp``), so concurrent
    writers cannot share one ``.tmp`` name.

    Permissions follow the file being replaced, or the process umask for a new
    file — a config write must never silently tighten or loosen the mode of a
    file the user already had.
    """
    payload = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode: int | None = None
    if os.name == "posix" and path.exists():
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        if os.name == "posix":
            os.chmod(tmp_name, _default_file_mode() if existing_mode is None else existing_mode)
        os.replace(tmp_name, path)
    except BaseException:  # also covers KeyboardInterrupt / SystemExit
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
