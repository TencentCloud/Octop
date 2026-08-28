#!/usr/bin/env bash
# =============================================================================
# 修复 orcakit-harness-agent 中 _Agent 类的 MRO 顺序问题
#
# 问题: harness_agent/acp/server.py 中 `class _Agent(Agent, HarnessACPAgent)`
# 导致 Agent（Protocol 基类）的空实现优先于 HarnessACPAgent 的实际实现，
# 使 ACP initialize / session/new 返回 null。
#
# 用法:
#   # 在宿主机上修复运行中的容器
#   docker exec <container_name> bash /docker/patch-harness-agent-mro.sh
#
#   # 或在容器内直接执行
#   bash /docker/patch-harness-agent-mro.sh
#
# 上游修复发布后可删除此脚本。
# =============================================================================
set -euo pipefail

SERVER_PY="$(find /app/.venv/lib -path '*/harness_agent/acp/server.py' -print -quit 2>/dev/null || true)"

if [ -z "$SERVER_PY" ] || [ ! -f "$SERVER_PY" ]; then
    echo "[patch] ERROR: harness_agent/acp/server.py not found"
    exit 1
fi

if ! grep -q 'class _Agent(Agent, HarnessACPAgent):' "$SERVER_PY"; then
    echo "[patch] SKIP: $SERVER_PY 已修复或模式不匹配"
    exit 0
fi

sed -i 's/class _Agent(Agent, HarnessACPAgent):/class _Agent(HarnessACPAgent, Agent):/' "$SERVER_PY"
echo "[patch] OK: 已修复 MRO 顺序 in $SERVER_PY"
echo "[patch] 请重启 Octop 服务使修复生效"
