"""Pull the sim trace from local Langfuse and analyze parent vs subagent prompt overlap."""

import base64
import json
import sys
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

HOST = "http://localhost:3000"
PK = "pk-lf-octop-kr2-subagent"
SK = "sk-lf-octop-kr2-subagent"
SESSION = "sim-kr2-trace-1"
OUT = Path(__file__).parent / "trace_analysis.json"


def api(path: str):
    req = urllib.request.Request(f"{HOST}{path}")
    tok = base64.b64encode(f"{PK}:{SK}".encode()).decode()
    req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def system_text(gen_input) -> str:
    """Extract the system/first message text from a generation input."""
    msgs = gen_input
    if isinstance(msgs, dict):
        msgs = msgs.get("messages", [])
    if not isinstance(msgs, list):
        return ""
    for m in msgs:
        if isinstance(m, dict):
            role = m.get("role") or m.get("type") or ""
            if role.lower() in ("system", "systemmessage"):
                c = m.get("content")
                if isinstance(c, list):
                    return "".join(p.get("text", "") for p in c if isinstance(p, dict))
                return str(c or "")
    return ""


def main() -> None:
    traces = api(f"/api/public/traces?sessionId={SESSION}&limit=10").get("data", [])
    if not traces:
        print("NO TRACES for session", SESSION)
        sys.exit(1)
    trace_id = traces[0]["id"]
    print("trace:", trace_id, traces[0].get("name"))

    # paginated observations
    obs = []
    page = 1
    while True:
        batch = api(f"/api/public/observations?traceId={trace_id}&limit=100&page={page}")
        obs.extend(batch.get("data", []))
        if page >= batch.get("meta", {}).get("totalPages", 1):
            break
        page += 1
    print(f"observations: {len(obs)}")

    by_id = {o["id"]: o for o in obs}

    def ancestry(o):
        chain = []
        cur = o
        while cur:
            chain.append(cur.get("name") or cur.get("type"))
            pid = cur.get("parentObservationId")
            cur = by_id.get(pid) if pid else None
        return list(reversed(chain))

    gens = [o for o in obs if o.get("type") == "GENERATION"]
    gens.sort(key=lambda o: o.get("startTime") or "")
    print(f"generations: {len(gens)}")

    # classify: a generation is 'subagent' if any ancestor span is the task tool / subagent graph
    rows = []
    for g in gens:
        chain = ancestry(g)
        chain_s = " > ".join(str(c) for c in chain)
        is_sub = any("task" == str(c) or "anthropolog" in str(c).lower() or "人类学" in str(c) for c in chain[:-1])
        st = system_text(g.get("input"))
        usage = g.get("usageDetails") or g.get("usage") or {}
        rows.append(
            {
                "id": g["id"],
                "side": "subagent" if is_sub else "parent",
                "model": g.get("model"),
                "start": g.get("startTime"),
                "end": g.get("endTime"),
                "latency_ms": g.get("latency"),
                "usage": usage,
                "system_prompt": st,
                "chain": chain_s,
            }
        )

    parents = [r for r in rows if r["side"] == "parent"]
    subs = [r for r in rows if r["side"] == "subagent"]
    print(f"parent generations: {len(parents)}, subagent generations: {len(subs)}")
    for r in rows:
        print(f"  [{r['side']}] {r['model']} sys={len(r['system_prompt'])}ch usage={r['usage']} chain={r['chain'][:120]}")

    result = {"trace_id": trace_id, "generations": rows}
    if parents and subs:
        ps = parents[0]["system_prompt"]
        ss = subs[0]["system_prompt"]
        sm = SequenceMatcher(None, ps, ss)
        blocks = [b for b in sm.get_matching_blocks() if b.size >= 80]
        overlap_chars = sum(b.size for b in blocks)
        result["overlap"] = {
            "parent_sys_chars": len(ps),
            "subagent_sys_chars": len(ss),
            "ratio_of_parent_sys_reused": overlap_chars / max(len(ps), 1),
            "common_prefix_chars": next(
                (i for i, (a, b) in enumerate(zip(ps, ss)) if a != b), min(len(ps), len(ss))
            ),
            "matched_blocks_over_80chars": [
                {"parent_pos": b.a, "sub_pos": b.b, "size": b.size, "text_head": ps[b.a : b.a + 60]}
                for b in blocks
            ],
        }
        print("\n=== PROMPT OVERLAP parent vs subagent ===")
        print(json.dumps(result["overlap"], ensure_ascii=False, indent=2)[:2000])

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
