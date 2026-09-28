# -*- coding: utf-8 -*-
"""Final post-rebase verification of the local deployment."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8088"
home = Path(os.environ.get("OCTOP_HOME") or (Path.home() / ".octop"))

conn = sqlite3.connect(str(home / "octop.db"))
names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
print("schema version =", conn.execute("SELECT version FROM _schema_version").fetchone()[0])
print("project tables =", sum(1 for t in (
    "projects", "project_members", "project_tasks", "project_comments",
    "node_mark_logs", "requirement_nodes", "project_rooms",
    "project_room_members", "project_artifacts", "timeline_events") if t in names), "/10")
print("upstream user_role table present =", "user_role" in names)
conn.close()


def call(method: str, path: str, body: object = None, token: str | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


tok = call("POST", "/api/auth/login", {"username": "admin", "password": "octopadmin2026"})["access_token"]
projects = call("GET", "/api/projects", None, tok)
print(f"\nGET /api/projects -> {len(projects)} project(s)")
for p in projects:
    tasks = call("GET", f"/api/projects/{p['project_id']}/tasks", None, tok)
    events = call("GET", f"/api/projects/{p['project_id']}/timeline", None, tok)
    members = call("GET", f"/api/projects/{p['project_id']}/members", None, tok)
    print(
        f"  {p['project_id']}  {p['name']:<16} status={p['status']:<7} "
        f"kb={p['kb_id']}  tasks={len(tasks)}  events={len(events)}  members={len(members)}"
    )
print("\nDEPLOY OK ->", BASE)
