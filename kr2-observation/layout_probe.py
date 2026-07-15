"""布局探针：用 cached_tokens 反推 GLM 服务端把 tools/system/user 拼成什么顺序。

方法：焐热一个基准请求的缓存，然后逐项改变请求的某一部分，看命中掉到哪里。
若"换 system 不换 tools"仍命中 ≈ 工具区大小 → 工具区在 system 之前。
若"改第 1 个工具一个词"命中归零 → 严格前缀匹配，位移敏感（用户的质疑点）。
"""

import copy
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

CTX = Path(__file__).parent / "context"

# 真实的 16 个工具 schema（取自父 agent 请求）
raw = json.loads((CTX / "parent-turn1.raw.json").read_text())
msgs = raw["input"]["messages"] if isinstance(raw["input"], dict) else raw["input"]
TOOLS = [m["content"] for m in msgs if m.get("role") == "tool" and isinstance(m.get("content"), dict)]
assert len(TOOLS) == 16, len(TOOLS)

SYS_A = "你是测试助手 Alpha。你的任务是协助进行缓存布局实验。请始终简短回复。" * 3
SYS_B = "# 角色：Beta 观察员\n完全不同的另一个身份，负责记录气象数据并输出简报格式。" * 3
USER = "请只回复两个字：收到"

con = sqlite3.connect(f"file:{Path.home()/'.octop/octop.db'}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
P = con.execute("SELECT base_url, api_key FROM providers WHERE enabled=1").fetchone()


def call(tools, system, user, tag):
    body = {"model": "glm-5.2",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": 16, "temperature": 0}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(P["base_url"].rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {P['api_key']}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    u = out.get("usage", {})
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", "?")
    print(f"  [{tag}] prompt={u.get('prompt_tokens'):>6}  cached={cached:>6}  {time.perf_counter()-t0:.1f}s")
    return u.get("prompt_tokens"), cached


print("== 基线尺寸 ==")
no_tool_tokens, _ = call(None, SYS_A, USER, "无工具, sysA        ")
time.sleep(3)

print("\n== 焐热基准: 16工具 + sysA (重复到命中平台) ==")
full = None
for i in range(4):
    full, cached = call(TOOLS, SYS_A, USER, f"warm #{i+1}          ")
    time.sleep(4)
tools_region = full - no_tool_tokens
print(f"  → 全请求 {full} tok, 其中工具区 ≈ {tools_region} tok, system+user ≈ {no_tool_tokens} tok")

probes = []

print("\n== 探针1: 同16工具 + 完全不同的 sysB ==")
time.sleep(3)
probes.append(("P1 换system不换工具", call(TOOLS, SYS_B, USER, "16工具, sysB        ")[1]))

print("\n== 探针2: 抽掉第9个工具task(学子agent) + sysB ==")
time.sleep(3)
t15 = TOOLS[:8] + TOOLS[9:]
probes.append(("P2 前8同后分叉      ", call(t15, SYS_B, USER, "15工具(无task), sysB")[1]))

print("\n== 探针3: 第1个工具改一个词 + sysA ==")
time.sleep(3)
t_mut = copy.deepcopy(TOOLS)
t_mut[0]["function"]["description"] = t_mut[0]["function"]["description"].replace(
    "structured task list", "structured TODO list", 1)
probes.append(("P3 首工具改1词(位移)", call(t_mut, SYS_A, USER, "首工具变异, sysA    ")[1]))

print("\n== 探针4: 交换前两个工具顺序 + sysA ==")
time.sleep(3)
t_swap = [TOOLS[1], TOOLS[0]] + TOOLS[2:]
probes.append(("P4 前两工具换序     ", call(t_swap, SYS_A, USER, "换序, sysA          ")[1]))

print("\n== 探针5: 同16工具+sysA, 只换user ==")
time.sleep(3)
probes.append(("P5 只换user消息     ", call(TOOLS, SYS_A, "换个说法：请回复'好的'两个字", "16工具, sysA, userB ")[1]))

print("\n========== 汇总 ==========")
print(f"工具区尺寸 ≈ {tools_region} tok | 前8工具估算 ≈ {int(tools_region*14536/20000)} tok (按字符比例)")
for name, c in probes:
    print(f"  {name}: cached = {c}")
