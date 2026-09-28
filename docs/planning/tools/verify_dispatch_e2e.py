# -*- coding: utf-8 -*-
"""End-to-end dispatch verification against the running server.

Now that a provider and running agents exist, dispatch can be verified for real
-- including the part that was previously untestable: whether an agent turn
actually runs and produces output.

Uses urllib, not PowerShell, because Invoke-RestMethod returns a JSON array as a
single pipeline object (that bug already ate the demo tasks once).
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8088"
USER, PASSWORD = "admin", "octopadmin2026"

_failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        _failures.append(label)
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}{(' -- ' + detail) if detail else ''}")


def call(method: str, path: str, body: object = None, token: str | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw


def main() -> int:
    _, login = call("POST", "/api/auth/login", {"username": USER, "password": PASSWORD})
    tok = login["access_token"]

    print("1) runtime inventory")
    _, agents = call("GET", "/api/agents", None, tok)
    agents = agents if isinstance(agents, list) else agents.get("agents", [])
    for a in agents:
        print(f"     {a.get('agent_id')}  {a.get('name')}  kind={a.get('kind')}  state={a.get('state')}")
    _, teams = call("GET", "/api/teams", None, tok)
    teams = teams if isinstance(teams, list) else teams.get("teams", [])
    for t in teams:
        print(f"     team {t.get('team_id')}  {t.get('name')}")

    running = [a for a in agents if a.get("state") == "running"]
    plain = [a for a in running if a.get("kind") != "team-host"]
    host = [a for a in running if a.get("kind") == "team-host"]
    check("at least one running expert", bool(plain), str([a.get("agent_id") for a in plain]))
    check("at least one running team host", bool(host), str([a.get("agent_id") for a in host]))

    print("\n2) fresh project + task for the dispatch test")
    _, project = call("POST", "/api/projects", {"name": "派单验收", "goal": "验证 T2.5"}, tok)
    pid = project["project_id"]
    call("PATCH", f"/api/projects/{pid}", {"status": "active"}, tok)
    print(f"     project {pid}")

    print("\n3) error paths (no agent turn involved)")
    _, t0 = call("POST", f"/api/projects/{pid}/tasks", {"title": "未指派"}, tok)
    st, body = call("POST", f"/api/projects/{pid}/tasks/{t0['task_id']}:dispatch", {}, tok)
    check("unassigned task rejected", st == 400, f"HTTP {st} {json.dumps(body, ensure_ascii=False)[:140]}")

    _, t1 = call(
        "POST",
        f"/api/projects/{pid}/tasks",
        {"title": "指派给不存在的专家", "assignee_type": "agent", "assignee_id": "NOPE00"},
        tok,
    )
    st, body = call("POST", f"/api/projects/{pid}/tasks/{t1['task_id']}:dispatch", {}, tok)
    code = body.get("error", {}).get("code") if isinstance(body, dict) else None
    check("unknown agent rejected", st == 404, f"HTTP {st} code={code}")

    st, body = call("POST", f"/api/projects/{pid}/tasks/NOPE00:dispatch", {}, tok)
    code = body.get("error", {}).get("code") if isinstance(body, dict) else None
    check("unknown task rejected", st == 404, f"HTTP {st} code={code}")
    check("`:dispatch` suffix routes correctly", st != 404 or code == "PROJECT_TASK_NOT_FOUND",
          f"got HTTP {st} code={code}")

    print("\n4) REAL dispatch to a running expert")
    if not plain:
        check("real dispatch", False, "no running expert to dispatch to")
    else:
        aid = plain[0]["agent_id"]
        _, task = call(
            "POST",
            f"/api/projects/{pid}/tasks",
            {
                "title": "写一段 20 字的项目简介",
                "description": "用中文写，只输出正文。",
                "assignee_type": "agent",
                "assignee_id": aid,
            },
            tok,
        )
        tid = task["task_id"]
        print(f"     task {tid} -> agent {aid}")
        started = time.time()
        st, body = call("POST", f"/api/projects/{pid}/tasks/{tid}:dispatch", {}, tok)
        elapsed = time.time() - started
        check("dispatch returned 2xx", 200 <= st < 300, f"HTTP {st} {json.dumps(body, ensure_ascii=False)[:200] if not isinstance(body,str) else body[:200]}")

        if 200 <= st < 300:
            fresh = call("GET", f"/api/projects/{pid}/tasks", None, tok)[1]
            row = next((t for t in fresh if t["task_id"] == tid), None)
            check("task.thread_id written back", bool(row and row.get("thread_id")), str(row and row.get("thread_id")))
            events = call("GET", f"/api/projects/{pid}/timeline", None, tok)[1]
            actions = [e["action"] for e in events if e.get("task_id") == tid]
            check("timeline records the dispatch", any(a.endswith("dispatched") for a in actions), str(actions))
            print(f"     dispatch took {elapsed:.1f}s")

            print("\n5) did the agent actually produce output?")
            tid_thread = row.get("thread_id") if row else None
            if tid_thread:
                msgs = []
                for _ in range(12):
                    time.sleep(5)
                    st2, detail = call("GET", f"/api/agents/{aid}/threads/{tid_thread}/messages", None, tok)
                    if st2 == 200 and isinstance(detail, list) and len(detail) > 1:
                        msgs = detail
                        break
                print(f"     thread has {len(msgs)} message(s) after waiting")
                for m in msgs[:4]:
                    text = str(m.get("content") or m.get("text") or "")[:120].replace("\n", " ")
                    print(f"       [{m.get('role')}] {text}")
                check("agent produced a reply", len(msgs) > 1, "only the prompt is present")
                if len(msgs) > 1:
                    joined = json.dumps(msgs, ensure_ascii=False)
                    check("AC-09: prompt carries title", "20 字" in joined or "项目简介" in joined)
                    check("AC-09: prompt carries description", "只输出正文" in joined)

    print("\n6) team dispatch")
    if not host:
        check("team dispatch", False, "no running team host")
    else:
        hid = host[0]["agent_id"]
        _, task = call(
            "POST",
            f"/api/projects/{pid}/tasks",
            {"title": "两人各说一句", "description": "简短即可", "assignee_type": "team", "assignee_id": hid},
            tok,
        )
        st, body = call("POST", f"/api/projects/{pid}/tasks/{task['task_id']}:dispatch", {}, tok)
        check("team dispatch accepted", 200 <= st < 300, f"HTTP {st}")

    print()
    if _failures:
        print(f"{len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print("  -", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
