# -*- coding: utf-8 -*-
"""Verify the freshly bootstrapped ~/.octop SQLite control plane."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TABLES = (
    "projects",
    "project_members",
    "project_tasks",
    "project_comments",
    "node_mark_logs",
    "requirement_nodes",
    "project_rooms",
    "project_room_members",
    "project_artifacts",
    "timeline_events",
)

home = Path(os.environ.get("OCTOP_HOME") or (Path.home() / ".octop"))
db = home / "octop.db"
print(f"db: {db}  exists={db.exists()}  size={db.stat().st_size if db.exists() else 0:,}")

conn = sqlite3.connect(str(db))
version = conn.execute("SELECT version FROM _schema_version").fetchone()[0]
print(f"schema version = {version}")

names = {
    r[0]
    for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
}
present = sorted(t for t in TABLES if t in names)
missing = sorted(t for t in TABLES if t not in names)
print(f"project tables present = {len(present)}/10")
print(f"  {present}")
if missing:
    print(f"  MISSING: {missing}")
    raise SystemExit(1)

users = conn.execute("SELECT username, role FROM users").fetchall()
print(f"users = {users}")
conn.close()
print("OK")
