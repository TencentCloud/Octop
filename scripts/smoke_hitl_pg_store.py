"""Smoke test for HitlPendingPostgresStore (migration 026).

Usage (run from the repository root)::

    OCTOP_TEST_DSN="host=127.0.0.1 dbname=octop_test user=octop password=..." \
        python scripts/smoke_hitl_pg_store.py

The target database must already have 026_hitl_pending_store.pg.sql applied.
Requires psycopg[binary]>=3.2 and psycopg_pool>=3.2.
"""

import importlib.util
import os
import sys
import types

# Fake package hierarchy.
for mod_name in ("octop", "octop.infra", "octop.infra.gateway", "octop.infra.gateway.hitl"):
    m = types.ModuleType(mod_name)
    m.__path__ = []
    m.__package__ = mod_name
    sys.modules[mod_name] = m

# Load store.py first (dependency of pg_store).
spec_store = importlib.util.spec_from_file_location(
    "octop.infra.gateway.hitl.store", "src/octop/infra/gateway/hitl/store.py"
)
store_mod = importlib.util.module_from_spec(spec_store)
sys.modules["octop.infra.gateway.hitl.store"] = store_mod
spec_store.loader.exec_module(store_mod)

# Load pg_store.
spec = importlib.util.spec_from_file_location(
    "octop.infra.gateway.hitl.pg_store", "src/octop/infra/gateway/hitl/pg_store.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules["octop.infra.gateway.hitl.pg_store"] = mod
spec.loader.exec_module(mod)

store = mod.HitlPendingPostgresStore(
    (os.environ.get("OCTOP_TEST_DSN") or sys.exit("missing OCTOP_TEST_DSN")).strip()
)
print("Pool opened OK\n")

# Repeated runs must start from a clean slate: leftover rows let the
# idempotent-register path below reuse a record whose submission id was
# already consumed, which would fail the mark_form_consumed assertion.
with store._pool.connection() as _conn:
    _conn.execute("DELETE FROM hitl_pending_records")
print("Table reset OK\n")

# 1. register — returns HitlPendingRecord
rec = store.register(
    thread_id="t1",
    agent_id="a1",
    user_id=1001,
    session_key="s1",
    channel_type="test",
    action_requests=[{"tool": "deploy", "args": {}}],
    review_configs=None,
)
assert rec.pending_id and len(rec.pending_id) == 4
print(f"1. register          -> pending_id={rec.pending_id}, user_id={rec.user_id}  ✓")

# 2. get
r = store.get(rec.pending_id)
assert r is not None and r.status == "pending" and r.user_id == 1001
print(f"2. get               -> status={r.status}, user_id={r.user_id}  ✓")

# 3. get_pending (valid)
r2 = store.get_pending(rec.pending_id, "s1", "a1")
assert r2 is not None
print(f"3. get_pending(ok)   -> {r2.pending_id}  ✓")

# 4. get_pending (bad session)
r3 = store.get_pending(rec.pending_id, "bad", "a1")
assert r3 is None
print("4. get_pending(bad)  -> None  ✓")

# 5. resolve_for_session
r4 = store.resolve_for_session("s1", agent_id="a1")
assert r4 is not None and r4.pending_id == rec.pending_id
print(f"5. resolve_for_ses   -> {r4.pending_id}  ✓")

# 6. idempotent register — same slot + same actions returns existing record
rec2 = store.register(
    thread_id="t1",
    agent_id="a1",
    user_id=1001,
    session_key="s1",
    channel_type="test",
    action_requests=[{"tool": "deploy", "args": {}}],
    review_configs=None,
)
assert rec2.pending_id == rec.pending_id
print(f"6. idempotent reg    -> same={rec.pending_id == rec2.pending_id}  ✓")

# 7. mark_form_consumed
ok1 = store.mark_form_consumed(rec.pending_id, "sub-001")
ok2 = store.mark_form_consumed(rec.pending_id, "sub-001")
assert ok1 is True and ok2 is False
print(f"7. form_consumed     -> 1st={ok1}, 2nd={ok2}  ✓")

# 8. expire_pending_for_thread
rec3 = store.register(
    thread_id="t2",
    agent_id="a2",
    user_id=2001,
    session_key="s2",
    channel_type="test",
    action_requests=[{"tool": "x"}],
    review_configs=None,
)
store.expire_pending_for_thread("t2")
r5 = store.get(rec3.pending_id)
assert r5 is not None and r5.status == "expired"
print(f"8. expire_thread     -> status={r5.status}  ✓")

# 9. mark_resolved
rec4 = store.register(
    thread_id="t3",
    agent_id="a3",
    user_id=3001,
    session_key="s3",
    channel_type="test",
    action_requests=[{"tool": "y"}],
    review_configs=None,
)
store.mark_resolved(rec4.pending_id, "approved")
r6 = store.get(rec4.pending_id)
assert r6 is not None and r6.status == "approved"
print(f"9. mark_resolved     -> status={r6.status}  ✓")

# 10. cancel_pending_by_form_id
rec5 = store.register(
    thread_id="t4",
    agent_id="a4",
    user_id=4001,
    session_key="s4",
    channel_type="test",
    action_requests=[{"tool": "z"}],
    review_configs=None,
    form_context={"form_id": "form-001", "schema_version": 1},
)
cancelled = store.cancel_pending_by_form_id("form-001")
r7 = store.get(rec5.pending_id)
assert cancelled is True and r7.status == "expired"
print(f"10. cancel_by_form_id -> cancelled={cancelled}, status={r7.status}  ✓")

# 11. pending_thread_ids
pids = store.pending_thread_ids("a1", any_user=True)
assert "t1" in pids
print(f"11. pending_tids      -> {set(pids)}  ✓")

# 12. append_ask_answer
rec6 = store.register(
    thread_id="t6",
    agent_id="a6",
    user_id=6001,
    session_key="s6",
    channel_type="test",
    action_requests=[{"tool": "ask"}],
    review_configs=None,
)
store.append_ask_answer(rec6.pending_id, "answer1")
store.append_ask_answer(rec6.pending_id, "answer2")
r8 = store.get(rec6.pending_id)
assert r8.ask_answers == ["answer1", "answer2"] and r8.ask_question_index == 2
print(f"12. append_ask_answer -> {r8.ask_answers}  ✓")

# 13. _gc
store._gc()
print("13. _gc               -> OK  ✓")

store.close()
print("\n=== ALL 13 SMOKE TESTS PASSED ===")
