#!/usr/bin/env bash
# verify_openclaw.sh — OctopMemory OpenClaw plugin installation verifier
#
# Usage:
#   bash scripts/verify_openclaw.sh
#   bash scripts/verify_openclaw.sh --namespace my_project
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
NAMESPACE="openclaw__default"
OPENCLAW_CONFIG="${HOME}/.openclaw/openclaw.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      NAMESPACE="$2"; shift 2 ;;
    --config)
      OPENCLAW_CONFIG="$2"; shift 2 ;;
    *)
      echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

DB_PATH="${OCTOPMEMORY_HOME:-${HOME}/.octopmemory}/${NAMESPACE}/memory.sqlite"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

ok() {
  echo "  ✅ $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  ❌ $1"
  FAIL=$((FAIL + 1))
}

section() {
  echo ""
  echo "── $1 ──────────────────────────────────────────"
}

# ---------------------------------------------------------------------------
# Check 1: bridge is available and FTS5 support works
# ---------------------------------------------------------------------------
section "检查 1：Python bridge 探测"

if ! command -v octopmemory-bridge &>/dev/null; then
  fail "octopmemory-bridge 不在 PATH 中（请运行 uv tool install 'octop-memory[cli]'）"
else
  PROBE_OUTPUT=$(octopmemory-bridge --probe 2>/dev/null || true)
  if echo "$PROBE_OUTPUT" | grep -q '"ok": *true'; then
    ok "bridge 可用"
  else
    fail "bridge 探测失败（输出：${PROBE_OUTPUT}）"
  fi

  if echo "$PROBE_OUTPUT" | grep -q '"fts5": *true'; then
    ok "FTS5 支持正常"
  else
    fail "FTS5 不支持（请使用 uv 安装以获得带 FTS5 的 Python）"
  fi

  # Extract version information.
  HM_VERSION=$(echo "$PROBE_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('octop_memory_version','unknown'))" 2>/dev/null || echo "unknown")
  ok "octop-memory 版本：${HM_VERSION}"
fi

# ---------------------------------------------------------------------------
# Check 2: openclaw.json config field validation
# ---------------------------------------------------------------------------
section "检查 2：openclaw.json 配置文件"

if [[ ! -f "$OPENCLAW_CONFIG" ]]; then
  fail "配置文件不存在：${OPENCLAW_CONFIG}（请先运行 openclaw octopmemory setup）"
else
  ok "配置文件存在：${OPENCLAW_CONFIG}"

  # Check slot.
  SLOT=$(python3 -c "
import json, sys
with open('${OPENCLAW_CONFIG}') as f:
    d = json.load(f)
print(d.get('plugins', {}).get('slots', {}).get('memory', ''))
" 2>/dev/null || echo "")
  if [[ "$SLOT" == "octopmemory" ]]; then
    ok "slot = octopmemory"
  else
    fail "slot 字段缺失或错误（当前值：${SLOT}）"
  fi

  # Check namespace.
  NS=$(python3 -c "
import json
with open('${OPENCLAW_CONFIG}') as f:
    d = json.load(f)
cfg = d.get('plugins', {}).get('entries', {}).get('octopmemory', {}).get('config', {})
print(cfg.get('namespace', ''))
" 2>/dev/null || echo "")
  if [[ -n "$NS" ]]; then
    ok "namespace = ${NS}"
  else
    fail "namespace 字段缺失"
  fi

  # Check bridgeCommand.
  BRIDGE_CMD=$(python3 -c "
import json
with open('${OPENCLAW_CONFIG}') as f:
    d = json.load(f)
cfg = d.get('plugins', {}).get('entries', {}).get('octopmemory', {}).get('config', {})
print(cfg.get('bridge', {}).get('command', ''))
" 2>/dev/null || echo "")
  if [[ -n "$BRIDGE_CMD" ]]; then
    ok "bridgeCommand = ${BRIDGE_CMD}"
  else
    fail "bridgeCommand 字段缺失"
  fi

  # Check profile.
  PROFILE=$(python3 -c "
import json
with open('${OPENCLAW_CONFIG}') as f:
    d = json.load(f)
cfg = d.get('plugins', {}).get('entries', {}).get('octopmemory', {}).get('config', {})
print(cfg.get('profile', ''))
" 2>/dev/null || echo "")
  if [[ -n "$PROFILE" ]]; then
    ok "profile = ${PROFILE}"
  else
    fail "profile 字段缺失"
  fi
fi

# ---------------------------------------------------------------------------
# Check 3: memory.sqlite database exists
# ---------------------------------------------------------------------------
section "检查 3：SQLite 数据库"

if [[ -f "$DB_PATH" ]]; then
  ok "数据库文件存在：${DB_PATH}"

  # Check whether the raw_events table has data.
  RAW_COUNT=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('${DB_PATH}')
    # Find raw_events tables with a namespace prefix.
    tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%raw_events'\").fetchall()
    total = 0
    for (t,) in tables:
        total += conn.execute(f'SELECT COUNT(*) FROM \"{t}\"').fetchone()[0]
    print(total)
    conn.close()
except Exception as e:
    print(0)
" 2>/dev/null || echo "0")

  if [[ "$RAW_COUNT" -gt 0 ]]; then
    ok "raw_events 表有 ${RAW_COUNT} 条记录（记忆已写入）"
  else
    echo "  ⚠️  raw_events 表为空（请先与 OpenClaw 进行一次对话）"
  fi
else
  echo "  ⚠️  数据库文件不存在：${DB_PATH}（请先运行 setup 并与 OpenClaw 对话）"
fi

# ---------------------------------------------------------------------------
# Check 4: search smoke test, if the bridge is available
# ---------------------------------------------------------------------------
section "检查 4：搜索功能冒烟测试"

if command -v openclaw &>/dev/null; then
  SEARCH_OUTPUT=$(openclaw octopmemory search "test" 2>/dev/null || true)
  if [[ -n "$SEARCH_OUTPUT" ]]; then
    ok "搜索命令执行成功"
  else
    echo "  ⚠️  搜索返回空结果（数据库可能为空，属正常现象）"
  fi
else
  echo "  ⚠️  openclaw CLI 不在 PATH 中，跳过搜索测试"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "══════════════════════════════════════════════════"
echo "  验证结果：✅ ${PASS} 通过  ❌ ${FAIL} 失败"
echo "══════════════════════════════════════════════════"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "  请参考 docs/integrations.md 中的「共同验证与排错」解决上述问题。"
  exit 1
fi

echo ""
echo "  🎉 所有检查通过！OctopMemory 插件已正确安装。"
echo "  数据库路径：${DB_PATH}"
echo "  Namespace：${NAMESPACE}"
