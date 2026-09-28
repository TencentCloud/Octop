# -*- coding: utf-8 -*-
"""Seed a demo project through the real HTTP API.

Proves the whole stack end to end -- auth, router, service, repos, migration --
and gives the UI something to show.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8088"
USER = "admin"
PASSWORD = "octopadmin2026"


def call(method: str, path: str, body: object = None, token: str | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}\n{detail}") from exc


print("1) login")
login = call("POST", "/api/auth/login", {"username": USER, "password": PASSWORD})
token = login.get("token") or login.get("access_token")
assert token, f"no token in {login}"
print(f"   ok ({sorted(login)})")

print("2) create project")
project = call(
    "POST",
    "/api/projects",
    {"name": "演示项目 Alpha", "goal": "验证项目域端到端可用"},
    token,
)
pid = project["project_id"]
print(f"   project_id={pid} status={project['status']} kb_id={project['kb_id']}")
if project["kb_id"]:
    print("   KB bound at creation")
else:
    print("   no KB: the knowledge feature is off on this install "
          "(project creation is best-effort about it, kb_id stays NULL)")

print("3) activate")
project = call("PATCH", f"/api/projects/{pid}", {"status": "active"}, token)
print(f"   status={project['status']}")

print("4) create tasks")
tasks = []
for title, priority in (
    ("梳理需求边界", 2),
    ("设计数据结构", 1),
    ("实现接口层", 1),
    ("补测试用例", 0),
):
    task = call(
        "POST",
        f"/api/projects/{pid}/tasks",
        {"title": title, "priority": priority, "description": f"{title}的说明"},
        token,
    )
    tasks.append(task)
    print(f"   {task['task_id']} {task['status']:<6} {task['title']}")

print("5) move them along the state machine")
call("PATCH", f"/api/projects/{pid}/tasks/{tasks[0]['task_id']}", {"status": "doing"}, token)
call("PATCH", f"/api/projects/{pid}/tasks/{tasks[0]['task_id']}", {"status": "review"}, token)
call("PATCH", f"/api/projects/{pid}/tasks/{tasks[1]['task_id']}", {"status": "doing"}, token)
call("PATCH", f"/api/projects/{pid}/tasks/{tasks[3]['task_id']}", {"status": "blocked"}, token)
board = call("GET", f"/api/projects/{pid}/tasks", None, token)
for t in board:
    print(f"   {t['title']:<12} -> {t['status']}")

print("6) timeline (M16 trace)")
events = call("GET", f"/api/projects/{pid}/timeline", None, token)
print(f"   {len(events)} events")
for e in events:
    print(f"   {e['actor']:<10} {e['action']:<22} {json.dumps(e['payload'], ensure_ascii=False)}")

print("7) members")
members = call("GET", f"/api/projects/{pid}/members", None, token)
for m in members:
    print(f"   {m['subject_type']}:{m['subject_id']} role={m['role']}")

print("8) list projects")
listed = call("GET", "/api/projects", None, token)
print(f"   {len(listed)} project(s): {[p['name'] for p in listed]}")

print(f"\nDEMO READY -> {BASE}/projects  (project_id={pid})")
