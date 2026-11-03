#!/usr/bin/env python3
"""Cluster Doctor Patrol Server — lightweight HTTP server for cluster health data.

Serves static files from the skill project root and exposes three read-only
API endpoints backed by the JSONL history written by cluster_patrol_record.py.

Endpoints:
  GET /api/cluster-data    → full record array (JSON)
  GET /api/cluster-summary → aggregated cluster health statistics (JSON)
  GET /api/health          → liveness / data-file check (JSON)

Usage:
    python3 scripts/cluster_patrol_server.py              # default port 8766
    python3 scripts/cluster_patrol_server.py --port 9090
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PATROL_FILE = Path.home() / ".lightclaw" / "stats" / "cluster-doctor.jsonl"

# Number of recent records included in the score_trend array.
_TREND_POINTS = 48

# All grades emitted by cluster_score.sh, in ascending severity order.
_GRADES = ("healthy", "minor", "warning", "critical")


class ClusterPatrolHandler(SimpleHTTPRequestHandler):
    """Extend static file serving with cluster-specific API endpoints."""

    def do_GET(self) -> None:
        if self.path == "/api/cluster-data":
            self._serve_cluster_data()
        elif self.path == "/api/cluster-summary":
            self._serve_cluster_summary()
        elif self.path == "/api/health":
            self._json_response(
                {
                    "status": "ok",
                    "patrol_file": str(PATROL_FILE),
                    "exists": PATROL_FILE.exists(),
                }
            )
        else:
            super().do_GET()

    # ------------------------------------------------------------------
    # Data layer
    # ------------------------------------------------------------------

    def _read_jsonl(self) -> list[dict]:
        """Read all valid records from the JSONL history file."""
        records: list[dict] = []
        if not PATROL_FILE.exists():
            return records
        with PATROL_FILE.open(encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if stripped:
                    with contextlib.suppress(json.JSONDecodeError):
                        records.append(json.loads(stripped))
        return records

    # ------------------------------------------------------------------
    # API handlers
    # ------------------------------------------------------------------

    def _serve_cluster_data(self) -> None:
        """Return all patrol records as a JSON array."""
        self._json_response(self._read_jsonl())

    def _serve_cluster_summary(self) -> None:
        """Return aggregated cluster health statistics for the dashboard."""
        records = self._read_jsonl()
        total = len(records)
        if total == 0:
            self._json_response({"total": 0, "message": "no data"})
            return

        # Accumulate grade distribution across all records.
        grade_counts: dict[str, int] = dict.fromkeys(_GRADES, 0)
        scores: list[int] = []

        for rec in records:
            grade = rec.get("cluster_grade") or ""
            if grade in grade_counts:
                grade_counts[grade] += 1
            score = rec.get("cluster_score")
            if isinstance(score, int | float):
                scores.append(int(score))

        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        min_score = min(scores) if scores else None

        latest = records[-1]

        # Per-node grade distribution comes from the latest snapshot only —
        # aggregating across records would double-count the same nodes.
        node_grade_dist: dict[str, int] = dict.fromkeys(_GRADES, 0)
        for node in latest.get("nodes", []):
            ng = node.get("grade") or ""
            if ng in node_grade_dist:
                node_grade_dist[ng] += 1

        # Score trend: last _TREND_POINTS records, oldest-first for charting.
        trend_slice = records[-_TREND_POINTS:]
        score_trend = [
            {
                "ts": r.get("ts", ""),
                "ts_local": r.get("ts_local", ""),
                "score": r.get("cluster_score"),
            }
            for r in trend_slice
        ]

        # Per-node time-series for score and raw_metrics.
        # Build a dict keyed by node-id; each entry has parallel arrays for ts + metrics.
        node_trends: dict[str, dict] = {}
        for rec in trend_slice:
            ts = rec.get("ts", "")
            ts_local = rec.get("ts_local", "")
            for node in rec.get("nodes", []):
                nid = node.get("node") or node.get("name") or ""
                if not nid:
                    continue
                if nid not in node_trends:
                    node_trends[nid] = {
                        "node": nid,
                        "name": node.get("name") or nid,
                        "ts": [],
                        "ts_local": [],
                        "score": [],
                        "cpu_cloud_avg_pct": [],
                        "mem_pct": [],
                        "mem_cloud_avg_pct": [],
                        "disk_root_pct": [],
                        "load_ratio": [],
                    }
                entry = node_trends[nid]
                entry["ts"].append(ts)
                entry["ts_local"].append(ts_local)
                entry["score"].append(node.get("score"))
                raw = node.get("raw_metrics") or {}
                entry["cpu_cloud_avg_pct"].append(raw.get("cpu_cloud_avg_pct"))
                entry["mem_pct"].append(raw.get("mem_pct"))
                entry["mem_cloud_avg_pct"].append(raw.get("mem_cloud_avg_pct"))
                entry["disk_root_pct"].append(raw.get("disk_root_pct"))
                entry["load_ratio"].append(raw.get("load_ratio"))

        self._json_response(
            {
                "total": total,
                "latest_cluster_score": latest.get("cluster_score"),
                "latest_cluster_grade": latest.get("cluster_grade"),
                "avg_cluster_score": avg_score,
                "min_cluster_score": min_score,
                "weakest_node": latest.get("weakest_node") or None,
                "latest_node_count": latest.get("node_count") or 0,
                "grade_distribution": grade_counts,
                "node_grade_distribution": node_grade_dist,
                "score_trend": score_trend,
                "node_trends": list(node_trends.values()),
                "latest": latest,
                "earliest_ts": records[0].get("ts") if records else None,
                "latest_ts": latest.get("ts") if records else None,
            }
        )

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _json_response(self, data: dict | list, status: int = 200) -> None:
        """Write a JSON HTTP response with permissive CORS headers."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress per-request API logs to keep console output readable.
        if "/api/" not in (args[0] if args else ""):
            super().log_message(format, *args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster Doctor Patrol Server")
    parser.add_argument("--port", type=int, default=8766, help="Listening port (default 8766)")
    args = parser.parse_args()

    # Serve static assets relative to the skill project root (parent of scripts/).
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    server = HTTPServer(("0.0.0.0", args.port), ClusterPatrolHandler)

    print("\033[1;36mCluster Doctor Patrol Server\033[0m")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Dashboard:  \033[32mhttp://localhost:{args.port}/docs/cluster-dashboard.html\033[0m")
    print(f"  API:        http://localhost:{args.port}/api/cluster-data")
    print(f"  数据文件:   {PATROL_FILE}")
    print(f"  项目目录:   {project_root}")
    print()
    print("  \033[1mCtrl+C 停止\033[0m")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    main()
