#!/usr/bin/env bash
# =============================================================================
# e2e_openclaw_test.sh — OpenClaw + octop-memory end-to-end verifier
#
# Purpose: verify the full octop-memory plugin flow on a machine with OpenClaw installed:
#   1. Check bridge availability with octopmemory-bridge --probe.
#   2. Validate openclaw.json config fields.
#   3. Verify memory.sqlite exists and is readable.
#   4. Verify the raw_events table has data after at least one AI conversation.
#   5. Start the dashboard and check API responses.
#   6. Inspect the namespaces exposed by the dashboard.
#
# Usage:
#   bash scripts/e2e_openclaw_test.sh
#   bash scripts/e2e_openclaw_test.sh --skip-dashboard   # Skip dashboard tests.
#   bash scripts/e2e_openclaw_test.sh --db-path /custom/path/memory.sqlite
# =============================================================================

set -euo pipefail

# ── Color output ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}  ✅ $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; FAILED=$((FAILED + 1)); }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
info() { echo -e "${BLUE}  ℹ️  $1${NC}"; }
section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

FAILED=0
SKIP_DASHBOARD=false
DB_PATH="${OCTOPMEMORY_DB:-$HOME/.octopmemory/openclaw__default/memory.sqlite}"
NAMESPACE="openclaw__default"
DASHBOARD_PORT=17860  # Use a non-standard port to avoid conflicts.
DASHBOARD_PID=""

# ── Argument parsing ───────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-dashboard) SKIP_DASHBOARD=true; shift ;;
    --db-path) DB_PATH="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   octop-memory × OpenClaw 端到端验证                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
info "db_path   = $DB_PATH"
info "namespace = $NAMESPACE"

# ── Cleanup ────────────────────────────────────────────────────────────────
cleanup() {
  if [[ -n "$DASHBOARD_PID" ]] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    kill "$DASHBOARD_PID" 2>/dev/null || true
    info "已停止 dashboard 进程 (PID=$DASHBOARD_PID)"
  fi
}
trap cleanup EXIT

# =============================================================================
# Step 1: check bridge availability
# =============================================================================
section "步骤 1：Bridge 可用性检查"

if command -v octopmemory-bridge &>/dev/null; then
  pass "octopmemory-bridge 在 PATH 中找到"
  PROBE_OUTPUT=$(octopmemory-bridge --probe 2>/dev/null || true)
  if echo "$PROBE_OUTPUT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip().split('\n')[-1]); assert d.get('ok') and d.get('fts5')" 2>/dev/null; then
    pass "bridge --probe 返回 ok=true, fts5=true"
    BRIDGE_VERSION=$(echo "$PROBE_OUTPUT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip().split('\n')[-1]); print(d.get('octop_memory_version','?'))" 2>/dev/null || echo "?")
    info "octop-memory 版本: $BRIDGE_VERSION"
  else
    fail "bridge --probe 失败或 FTS5 不支持"
    info "输出: $PROBE_OUTPUT"
  fi
else
  fail "octopmemory-bridge 未找到，请运行: uv tool install 'octop-memory[cli]'"
fi

# =============================================================================
# Step 2: check openclaw.json config
# =============================================================================
section "步骤 2：openclaw.json 配置检查"

OPENCLAW_JSON="$HOME/.openclaw/openclaw.json"
if [[ -f "$OPENCLAW_JSON" ]]; then
  pass "openclaw.json 存在: $OPENCLAW_JSON"

  # Check required fields.
  for field in "namespace" "profile" "bridge"; do
    if python3 -c "
import json, sys
with open('$OPENCLAW_JSON') as f:
    d = json.load(f)
plugins = d.get('plugins', {})
entries = plugins.get('entries', {})
memory_config = entries.get('octopmemory', {}).get('config', {})
assert '$field' in memory_config, f'缺少字段: $field'
print(memory_config.get('$field', ''))
" 2>/dev/null; then
      pass "配置字段 '$field' 存在"
    else
      fail "配置字段 '$field' 缺失"
    fi
  done

  # Check slot.
  SLOT=$(python3 -c "
import json
with open('$OPENCLAW_JSON') as f:
    d = json.load(f)
print(d.get('plugins', {}).get('slots', {}).get('memory', ''))
" 2>/dev/null || echo "")
  if [[ "$SLOT" == "octopmemory" ]]; then
    pass "plugins.slots.memory = octopmemory"
  else
    fail "plugins.slots.memory 不是 octopmemory（当前: '$SLOT'）"
  fi
else
  warn "openclaw.json 不存在，请运行: openclaw octopmemory setup"
fi

# =============================================================================
# Step 3: check memory.sqlite
# =============================================================================
section "步骤 3：memory.sqlite 文件检查"

DB_EXPANDED="${DB_PATH/#\~/$HOME}"
if [[ -f "$DB_EXPANDED" ]]; then
  DB_SIZE=$(du -sh "$DB_EXPANDED" 2>/dev/null | cut -f1)
  pass "memory.sqlite 存在 (大小: $DB_SIZE)"

  # Check the SQLite file header.
  if file "$DB_EXPANDED" 2>/dev/null | grep -q "SQLite"; then
    pass "文件格式为有效的 SQLite 数据库"
  else
    fail "文件格式不是 SQLite"
  fi
else
  warn "memory.sqlite 不存在: $DB_EXPANDED"
  warn "请先与 OpenClaw 进行一次对话，触发记忆写入"
fi

# =============================================================================
# Step 4: verify raw_events writes
# =============================================================================
section "步骤 4：raw_events 数据验证"

if [[ -f "$DB_EXPANDED" ]]; then
  NS_PREFIX=$(echo "$NAMESPACE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_]/_/g')
  RAW_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$DB_EXPANDED')
try:
    row = conn.execute('SELECT COUNT(*) FROM ${NS_PREFIX}_raw_events').fetchone()
    print(row[0])
except Exception as e:
    print(0)
conn.close()
" 2>/dev/null || echo "0")

  if [[ "$RAW_COUNT" -gt 0 ]]; then
    pass "raw_events 表有 $RAW_COUNT 条记录"
  else
    warn "raw_events 表为空（请先与 AI 进行对话）"
  fi

  # Check the atoms table.
  ATOM_COUNT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('$DB_EXPANDED')
try:
    row = conn.execute('SELECT COUNT(*) FROM ${NS_PREFIX}_atoms WHERE deprecated_at IS NULL').fetchone()
    print(row[0])
except:
    print(0)
conn.close()
" 2>/dev/null || echo "0")
  info "活跃 atoms: $ATOM_COUNT 条"
else
  warn "跳过（数据库文件不存在）"
fi

# =============================================================================
# Step 5: dashboard API validation
# =============================================================================
section "步骤 5：Dashboard API 验证"

if [[ "$SKIP_DASHBOARD" == "true" ]]; then
  warn "已跳过 dashboard 测试（--skip-dashboard）"
elif ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  warn "fastapi/uvicorn 未安装，跳过 dashboard 测试"
  warn "安装命令: pip install 'octop-memory[dashboard]'"
elif [[ ! -f "$DB_EXPANDED" ]]; then
  warn "数据库文件不存在，跳过 dashboard 测试"
else
  # Start the dashboard.
  info "启动 dashboard（端口 $DASHBOARD_PORT）..."
  python3 -m octop_memory.adapters.cli dashboard \
    --db-path "$DB_PATH" \
    --namespace "$NAMESPACE" \
    --port "$DASHBOARD_PORT" \
    --no-browser &
  DASHBOARD_PID=$!

  # Wait for the service to start.
  WAIT=0
  until curl -sf "http://127.0.0.1:$DASHBOARD_PORT/api/defaults" >/dev/null 2>&1; do
    sleep 0.5
    WAIT=$((WAIT + 1))
    if [[ $WAIT -gt 20 ]]; then
      fail "dashboard 启动超时（10s）"
      break
    fi
  done

  if curl -sf "http://127.0.0.1:$DASHBOARD_PORT/api/defaults" >/dev/null 2>&1; then
    pass "dashboard 服务启动成功"

    # Check /api/connect.
    CONNECT_RES=$(curl -sf "http://127.0.0.1:$DASHBOARD_PORT/api/connect?db_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DB_PATH'))")&namespace=$NAMESPACE" 2>/dev/null || echo "{}")
    if echo "$CONNECT_RES" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok')" 2>/dev/null; then
      pass "/api/connect 返回 ok=true"
    else
      fail "/api/connect 返回异常: $CONNECT_RES"
    fi

    # Check /api/stats.
    STATS_RES=$(curl -sf "http://127.0.0.1:$DASHBOARD_PORT/api/stats?db_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DB_PATH'))")&namespace=$NAMESPACE" 2>/dev/null || echo "{}")
    if echo "$STATS_RES" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'raw_events' in d" 2>/dev/null; then
      RAW_FROM_API=$(echo "$STATS_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['raw_events'])")
      pass "/api/stats 返回正常（raw_events=$RAW_FROM_API）"
    else
      fail "/api/stats 返回异常: $STATS_RES"
    fi

    # Check /api/namespaces.
    NS_RES=$(curl -sf "http://127.0.0.1:$DASHBOARD_PORT/api/namespaces?db_path=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DB_PATH'))")" 2>/dev/null || echo "{}")
    if echo "$NS_RES" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'namespaces' in d" 2>/dev/null; then
      NS_LIST=$(echo "$NS_RES" | python3 -c "import sys,json; print(', '.join(json.load(sys.stdin)['namespaces']))")
      pass "/api/namespaces 返回正常（namespaces: $NS_LIST）"
    else
      fail "/api/namespaces 返回异常"
    fi
  fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}  🎉 所有检查通过！octop-memory × OpenClaw 链路正常。${NC}"
else
  echo -e "${RED}  ⚠️  共 $FAILED 项检查失败，请根据上方提示修复。${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit $FAILED
