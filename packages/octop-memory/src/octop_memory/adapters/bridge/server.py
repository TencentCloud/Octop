"""Stdio JSON-RPC server entry point.

Spawned by the OpenClaw TS plugin shell as ``octopmemory-bridge``.
Reads one JSON object per line on stdin, writes one JSON object per
line on stdout. Stderr is reserved for human-readable logs (the TS
shell pipes it to OpenClaw's plugin log channel).

Usage::

    octopmemory-bridge \\
        --namespace openclaw__a3f2c891 \\
        --db-path ~/.octopmemory/openclaw__a3f2c891/memory.sqlite \\
        --log-level info

    # PostgreSQL backend: the DSN is read from an environment variable,
    # never passed as a flag (argv is visible in process listings).
    OCTOP_MEMORY_DSN=postgresql://user:pass@host/db octopmemory-bridge \\
        --namespace openclaw__a3f2c891 \\
        --backend postgres \\
        --log-level info

The binary is intentionally simple and synchronous (one request per
turn). Concurrency lives on the TS side — multiple plugin contexts
spawn their own bridge subprocesses, and our Python ``Memory`` is
single-threaded by design (M0..M5 all assume one connection per
``Memory`` instance).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import IO, Any

from octop_memory.adapters.bridge.handlers import ERR_PARSE, Bridge, _error
from octop_memory.application.config import MemoryRuntimeConfig
from octop_memory.application.host_files import DEFAULT_HOST_FILE_GLOBS, HostFilesIndex
from octop_memory.core import Memory

logger = logging.getLogger("octopmemory.bridge")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="octopmemory-bridge",
        description="OpenClaw native memory plugin bridge (Python side).",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "Print a one-line JSON environment report (protocol/version/sqlite/fts5) "
            "and exit. Exits non-zero if FTS5 is unavailable. Ignores all other args."
        ),
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="Namespace identifier (typically '<host>__<user_id_hash[:12]>').",
    )
    parser.add_argument(
        "--db-path",
        required=False,
        help=(
            "Override the SQLite db path. Defaults to ~/.octopmemory/<ns>/memory.sqlite. "
            "Also used for host_files indexing (D51-C) regardless of --backend, "
            "since that index is always SQLite-backed."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=["sqlite", "postgres"],
        default="sqlite",
        help="Memory storage backend for this namespace (default: sqlite).",
    )
    parser.add_argument(
        "--dsn-env",
        default="OCTOP_MEMORY_DSN",
        help=(
            "Name of the environment variable holding the PostgreSQL connection "
            "string, read when --backend=postgres (default: OCTOP_MEMORY_DSN — "
            "same convention as the main octop-memory CLI). The DSN itself is "
            "never accepted as a CLI flag: argv is visible in process listings."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="stderr log verbosity (default: info).",
    )
    parser.add_argument(
        "--host-files-root",
        required=False,
        help=(
            "Workspace dir to watch for host-written real files (D51-C). "
            "When set, the bridge indexes MEMORY.md / USER.md / memory/YYYY-MM-DD.md "
            "and surfaces them via memory_search + memory_get. "
            "Defaults to disabled."
        ),
    )
    parser.add_argument(
        "--host-files-allow",
        action="append",
        default=[],
        help=(
            "Additional relative markdown glob to index under --host-files-root. "
            "May be repeated or comma-separated. Defaults to: " + ", ".join(DEFAULT_HOST_FILE_GLOBS)
        ),
    )
    parser.add_argument(
        "--host-files-poll-interval",
        type=float,
        default=30.0,
        help="Seconds between host-files scans (default 30).",
    )
    parser.add_argument(
        "--config-json",
        required=False,
        help=(
            "Compact JSON runtime policy (recall/capture/privacy/llm/extraction) passed by the "
            "OpenClaw TS shell. llm = OpenAI-compatible endpoint for extraction "
            "({endpoint, model, model_heavy?, api_key_env?, ...}); prefer api_key_env over an "
            "inline api_key — argv is visible in process listings."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Server loop
# ---------------------------------------------------------------------------


def serve(
    bridge: Bridge,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> None:
    """Read line-framed JSON-RPC requests until EOF.

    Exposed as a top-level function so unit tests can drive it with
    in-memory pipes (`io.StringIO`).
    """
    src = stdin or sys.stdin
    sink = stdout or sys.stdout

    for raw_line in src:
        line = raw_line.strip()
        if not line:
            continue
        response = _handle_one(bridge, line)
        sink.write(json.dumps(response, ensure_ascii=False) + "\n")
        sink.flush()


def _handle_one(bridge: Bridge, line: str) -> dict[str, Any]:
    """Parse one line into a JSON-RPC response dict.

    Parse errors return a ``-32700`` envelope with ``id: null`` per
    spec; downstream errors are produced by ``Bridge.handle``.
    """
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        return _error(None, ERR_PARSE, f"could not parse JSON: {exc.msg}")
    if not isinstance(request, dict):
        return _error(None, ERR_PARSE, "request must be a JSON object")
    return bridge.handle(request)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def _run_probe() -> int:
    """Print a one-line JSON environment report and exit.

    Used by the OpenClaw ``setup``/``doctor`` flow to verify, *before*
    wiring anything up, that this interpreter can actually run the
    bridge: the SQLite it links must have FTS5 compiled in, and the
    protocol / package versions must be reported so the TS shell can
    detect drift.

    Deliberately import-light and click-free — it must succeed on a
    bare ``octop-memory`` install (no extras). Exits non-zero when
    FTS5 is unavailable, so callers can branch on the exit code alone.
    """
    import platform
    import sqlite3

    from octop_memory import __version__
    from octop_memory.adapters.bridge import PROTOCOL_VERSION

    fts5 = False
    fts5_error: str | None = None
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE _probe_fts USING fts5(x)")
            fts5 = True
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        fts5_error = str(exc)

    report = {
        "ok": fts5,
        "protocol_version": PROTOCOL_VERSION,
        "octop_memory_version": __version__,
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "sqlite_version": sqlite3.sqlite_version,
        "fts5": fts5,
        "fts5_error": fts5_error,
    }
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if fts5 else 1


def main(argv: list[str] | None = None) -> int:
    # --probe short-circuits before the full parser so it can run
    # without --namespace and without spinning up a Memory/store.
    if "--probe" in (argv if argv is not None else sys.argv[1:]):
        return _run_probe()

    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )

    # host_files indexing (D51-C) is always SQLite-backed, independent of the
    # memory backend choice below — so this path is computed unconditionally.
    db_path = Path(args.db_path) if args.db_path else _default_db_path(args.namespace)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.backend == "postgres":
        dsn = os.environ.get(args.dsn_env)
        if not dsn:
            raise SystemExit(
                f"--backend=postgres requires the {args.dsn_env} environment "
                "variable to hold the PostgreSQL connection string."
            )
        memory = Memory(namespace=args.namespace, backend="postgres", backend_config={"dsn": dsn})
    else:
        memory = Memory(namespace=args.namespace, backend="sqlite", backend_config={"db_path": str(db_path)})

    bridge_config = _parse_bridge_config(args.config_json)

    host_files: HostFilesIndex | None = None
    if args.host_files_root:
        root = Path(args.host_files_root).expanduser().resolve()
        include_globs = _split_csv_args(args.host_files_allow) or list(DEFAULT_HOST_FILE_GLOBS)
        host_files = HostFilesIndex(db_path=db_path, namespace=args.namespace, include_globs=include_globs)
        # First scan synchronously so handshake-time queries see content
        # already, then start the polling loop.
        report = host_files.scan_once(root)
        logger.info(
            "host_files initial scan: scanned=%d indexed=%d removed=%d",
            report.scanned,
            report.indexed,
            report.removed,
        )
        host_files.start_polling(root, interval=args.host_files_poll_interval)

    bridge = Bridge(memory, host_files=host_files, config=bridge_config)
    logger.info(
        "octopmemory bridge started (namespace=%s backend=%s host_files=%s)",
        args.namespace,
        args.backend if args.backend == "postgres" else f"sqlite db={db_path}",
        args.host_files_root or "off",
    )
    try:
        serve(bridge)
    except KeyboardInterrupt:
        logger.info("octopmemory bridge interrupted; exiting cleanly")
    finally:
        if host_files is not None:
            host_files.stop()
    return 0


def _parse_bridge_config(raw: str | None) -> MemoryRuntimeConfig:
    if not raw:
        return MemoryRuntimeConfig()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--config-json is not valid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit("--config-json must decode to an object")
    return MemoryRuntimeConfig(
        profile=loaded.get("profile") if isinstance(loaded.get("profile"), str) else None,
        mode=loaded.get("mode") if isinstance(loaded.get("mode"), str) else None,
        recall=_dict_value(loaded.get("recall")),
        capture=_dict_value(loaded.get("capture")),
        privacy=_dict_value(loaded.get("privacy")),
        llm=_dict_value(loaded.get("llm")),
        extraction=_dict_value(loaded.get("extraction")),
    )


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _split_csv_args(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def _default_db_path(namespace: str) -> Path:
    """Build the default SQLite path for a given namespace.

    Honours ``$OCTOPMEMORY_HOME`` if set (M5 export/import use this
    same env var), else falls back to ``~/.octopmemory/<ns>/memory.sqlite``.
    """
    home = os.environ.get("OCTOPMEMORY_HOME")
    base = Path(home) if home else Path.home() / ".octopmemory"
    return base / namespace / "memory.sqlite"


__all__ = ["main", "serve"]


if __name__ == "__main__":
    raise SystemExit(main())
