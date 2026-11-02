#!/usr/bin/env python3
"""Record one cluster health scan result into the JSONL history file.

Reads cluster_score.sh JSON output from stdin (or --input file), injects
timestamp and cluster_name, then appends exactly one JSONL line to
~/.lightclaw/stats/cluster-doctor.jsonl.

Designed to run at the tail of each heartbeat scan.  All errors are written
to stderr only — the caller (heartbeat) is never disrupted.

Usage:
    cluster_score.sh nodes.txt | python3 cluster_patrol_record.py \\
        --cluster-name my-cluster [--rotate]

    python3 cluster_patrol_record.py \\
        --cluster-name my-cluster \\
        --input /tmp/score.json \\
        --rotate
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import pathlib
import sys
from datetime import UTC, datetime, timedelta

STATS_DIR = pathlib.Path.home() / ".lightclaw" / "stats"
HISTORY_FILE = STATS_DIR / "cluster-doctor.jsonl"
# Number of days to keep in the main JSONL; older records are archived to .gz.
_RETENTION_DAYS = int(os.environ.get("PATROL_RETENTION_DAYS", "7"))


def _now_timestamps() -> tuple[str, str]:
    """Return (utc_iso, local_display) for the current moment."""
    utc = datetime.now(UTC)
    local = datetime.now()
    return (
        utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        local.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _rotate(history_file: pathlib.Path, retention_days: int) -> None:
    """Archive records older than retention_days to a compressed backup.

    Lines that fail JSON parsing are kept to avoid silent data loss.
    """
    if not history_file.exists():
        return

    cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    keep: list[str] = []
    archive: list[str] = []

    with history_file.open(encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
                if rec.get("ts", "") >= cutoff:
                    keep.append(stripped)
                else:
                    archive.append(stripped)
            except json.JSONDecodeError:
                keep.append(stripped)

    if not archive:
        return

    backup = history_file.parent / "cluster-doctor.old.jsonl.gz"
    with gzip.open(backup, "at", encoding="utf-8") as gz:
        gz.write("\n".join(archive) + "\n")

    tmp = history_file.with_suffix(".tmp")
    tmp.write_text(
        "\n".join(keep) + ("\n" if keep else ""),
        encoding="utf-8",
    )
    tmp.replace(history_file)

    print(
        f"[cluster_patrol_record] rotated: archived {len(archive)} records"
        f" older than {retention_days}d",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append a cluster patrol result to the JSONL history."
    )
    parser.add_argument(
        "--cluster-name",
        default="",
        help="Human-readable cluster name (stored in every JSONL record).",
    )
    parser.add_argument(
        "--input",
        help="Path to a JSON file produced by cluster_score.sh; reads stdin when omitted.",
    )
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Run retention rotation after appending (removes records older than PATROL_RETENTION_DAYS).",
    )
    args = parser.parse_args()

    # Read JSON input from file or stdin.
    try:
        if args.input:
            raw = pathlib.Path(args.input).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        score_data: dict = json.loads(raw)
    except Exception as exc:
        print(
            f"[cluster_patrol_record] ERROR: failed to parse input JSON: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)  # Non-fatal: never block the heartbeat.

    ts, ts_local = _now_timestamps()
    record: dict = {
        "ts": ts,
        "ts_local": ts_local,
        "cluster_name": args.cluster_name,
        "cluster_score": score_data.get("cluster_score"),
        "cluster_grade": score_data.get("cluster_grade"),
        "weakest_node": score_data.get("weakest_node"),
        "node_count": score_data.get("node_count"),
        "nodes": score_data.get("nodes", []),
    }

    try:
        STATS_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(
            f"[cluster_patrol_record] ERROR: failed to write JSONL: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    if args.rotate:
        try:
            _rotate(HISTORY_FILE, _RETENTION_DAYS)
        except Exception as exc:
            print(
                f"[cluster_patrol_record] WARN: rotation failed (non-fatal): {exc}",
                file=sys.stderr,
            )

    score = record.get("cluster_score", "?")
    grade = record.get("cluster_grade", "?")
    weakest = record.get("weakest_node") or "none"
    print(
        f"[cluster_patrol_record] OK: score={score} grade={grade}"
        f" weakest={weakest} → {HISTORY_FILE}"
    )


if __name__ == "__main__":
    main()
