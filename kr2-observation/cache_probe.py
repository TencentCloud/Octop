"""缓存探针：A/A 重放 + 前缀扩展重放，测 GLM(tokenhub) 前缀缓存行为。

用法: .venv/bin/python cache_probe.py
结论(2026-07-16 实测):
  相同请求 x3          → cached_tokens: 0 / 2,624 / 17,024 (异步分块提交, 64-token块)
  暖缓存后重放 turn2   → cached_tokens: 17,088/17,291 (前缀匹配有效!)
  时延: 冷 6.5s → 暖 2.9s (-55%)
  → 原始 agent 运行中父第2轮的 0 命中不是客户端问题(工具序列化逐字节稳定),
    是服务端命中不稳定(提交延迟/多副本无亲和路由)。
"""
import json, sqlite3, time, urllib.request
from pathlib import Path

CTX = Path(__file__).parent / "context"

def load_payload(raw_file):
    d = json.loads((CTX / raw_file).read_text())
    msgs = d["input"]["messages"] if isinstance(d["input"], dict) else d["input"]
    conv, tools = [], []
    for m in msgs:
        if m.get("role") == "tool" and isinstance(m.get("content"), dict):
            tools.append(m["content"])
        else:
            e = {"role": m["role"], "content": m.get("content") or ""}
            if m.get("tool_calls"):
                e["tool_calls"] = [{"id": tc["id"], "type": "function",
                                    "function": {"name": tc["name"],
                                                 "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                                   for tc in m["tool_calls"]]
            if m.get("tool_call_id"):
                e["tool_call_id"] = m["tool_call_id"]
            conv.append(e)
    return conv, tools

def call(conv, tools, tag):
    con = sqlite3.connect(f"file:{Path.home()/'.octop/octop.db'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    p = con.execute("SELECT base_url, api_key FROM providers WHERE enabled=1").fetchone()
    body = json.dumps({"model": "glm-5.2", "messages": conv, "tools": tools,
                       "max_tokens": 16, "temperature": 0}).encode()
    req = urllib.request.Request(p["base_url"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {p['api_key']}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    u = out.get("usage", {})
    print(f"[{tag}] {time.perf_counter()-t0:.2f}s prompt={u.get('prompt_tokens')} "
          f"cached={u.get('prompt_tokens_details', {}).get('cached_tokens')}")

if __name__ == "__main__":
    c1, t1 = load_payload("parent-turn1.raw.json")
    c2, t2 = load_payload("parent-turn2.raw.json")
    for i in range(3):
        call(c1, t1, f"turn1 A/A #{i+1}")
        time.sleep(2)
    call(c2, t2, "turn2 前缀扩展重放")
