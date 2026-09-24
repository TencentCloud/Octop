"""迁移配置：从 octop.db channels 表 + 旧两桥配置 → ~/.nong-gateway/config.json

用法:
    python3 tools/迁移配置.py            # dry-run，只打印计划
    python3 tools/迁移配置.py --write    # 实际写出（0600）

做了什么:
1. 读 octop.db 的 channels 表，把元宝凭据（app_key/app_secret/bot 名）转成 credentials[]，
   agentId 用行里的 agent_id；channel 行保持/置为停用（防双消费者）。
2. Kimi token：若旧 KCP_HOME 有 token 文件则并入（kind=kimi）；没有就留占位，用户手填。
3. agents 段：默认拒绝——每个 credential 的 agentId 写一条 {"groupMode":"mention"}，
   要开口再 --set 或手改。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path

HOME = Path(os.environ.get("NONGGW_HOME", str(Path.home() / ".nong-gateway")))
OCTOP_HOME = Path(os.environ.get("OCTOP_HOME", "/data/wwlst/octop"))


def load_channels() -> list[dict]:
    db = OCTOP_HOME / "octop.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT agent_id, name, kind, config_json, enabled FROM channels").fetchall()
    finally:
        con.close()
    out = []
    for agent_id, name, kind, cfg_json, enabled in rows:
        cfg = json.loads(cfg_json or "{}")
        out.append({"agent_id": agent_id, "name": name, "kind": kind,
                    "cfg": cfg, "enabled": enabled})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    creds = []
    for row in load_channels():
        if row["kind"] != "yuanbao":
            continue
        c = row["cfg"]
        creds.append({
            "kind": "yuanbao",
            "agentId": row["agent_id"],
            "appKey": c.get("app_key", ""),
            "appSecret": c.get("app_secret", ""),
            "apiDomain": c.get("api_domain", ""),
            "wsUrl": c.get("ws_url", ""),
            "botNames": [row["name"]],
        })

    kimi_token = ""
    for cand in (HOME / "token", Path.home() / ".kimi-claw-py/plugin/token"):
        if cand.is_file():
            kimi_token = cand.read_text(encoding="utf-8").strip()
            break
    if kimi_token:
        creds.append({"kind": "kimi", "agentId": "assistant", "token": kimi_token})

    agents = {c["agentId"]: {"groupMode": "mention"} for c in creds}
    config = {
        "host": "octop",
        "octopHome": str(OCTOP_HOME),
        "credentials": creds,
        "agents": agents,
        "defaultPolicy": "deny",
    }

    print(json.dumps(config, ensure_ascii=False, indent=2)[:2000])
    total = len(creds)
    if not args.write:
        print(f"\n(dry-run) 共 {total} 条凭据。加 --write 落盘 {HOME/'config.json'}（0600）")
        return 0
    HOME.mkdir(parents=True, exist_ok=True)
    p = HOME / "config.json"
    p.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    print(f"\n已写出 {p}（0600），{total} 条凭据。记得把 octop.db channels 表保持停用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
