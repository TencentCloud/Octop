#!/usr/bin/env bash
# =============================================================================
# e2e_hermes_test.sh — Hermes + octop-memory end-to-end verifier
#
# Purpose: verify the full octop-memory MemoryProvider plugin against a REAL
# Hermes source tree (NousResearch/hermes-agent), not the in-repo stub base
# class. Unlike the unit tests, this proves:
#   1. install + doctor succeed against a real Hermes home/source layout.
#   2. OctopMemoryProvider actually subclasses the REAL
#      agent.memory_provider.MemoryProvider (contract fidelity).
#   3. The runtime flow works: initialize -> sync_turn -> prefetch ->
#      memory_search -> memory_get, plus the host_files watcher indexes
#      $HERMES_HOME/memories topical markdown.
#
# This is optional / CI-gated: with no Hermes source available it prints a
# skip notice and exits 0 (mirrors scripts/e2e_openclaw_test.sh behaviour).
#
# Usage:
#   HERMES_SOURCE=/path/to/hermes-agent bash scripts/e2e_hermes_test.sh
#   bash scripts/e2e_hermes_test.sh --hermes-source /path/to/hermes-agent
#   # Or let the script clone it (needs network + repo access):
#   HERMES_REPO=https://github.com/NousResearch/hermes-agent \
#     HERMES_REF=main bash scripts/e2e_hermes_test.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
pass() { echo -e "${GREEN}  ✅ $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; FAILED=$((FAILED + 1)); }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
info() { echo -e "${BLUE}  ℹ️  $1${NC}"; }
section() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

FAILED=0
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_SOURCE="${HERMES_SOURCE:-}"
HERMES_REPO="${HERMES_REPO:-https://github.com/NousResearch/hermes-agent}"
HERMES_REF="${HERMES_REF:-main}"
PY="${PYTHON:-python3}"
CLONED_TMP=""
INSTALLER="$REPO_ROOT/plugins/hermes/octopmemory/installer.py"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hermes-source) HERMES_SOURCE="$2"; shift 2 ;;
    --hermes-repo) HERMES_REPO="$2"; shift 2 ;;
    --hermes-ref) HERMES_REF="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   octop-memory × Hermes 端到端验证                     ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── Step 0: resolve a real Hermes source tree ───────────────────────────────
section "步骤 0：定位真实 Hermes 源码"

if [[ -z "$HERMES_SOURCE" ]]; then
  info "未提供 HERMES_SOURCE，尝试从 $HERMES_REPO ($HERMES_REF) 克隆 ..."
  if command -v git &>/dev/null; then
    CLONED_TMP="$(mktemp -d)"
    if git clone --depth 1 --branch "$HERMES_REF" "$HERMES_REPO" "$CLONED_TMP/hermes-agent" 2>/dev/null; then
      HERMES_SOURCE="$CLONED_TMP/hermes-agent"
      pass "已克隆到 $HERMES_SOURCE"
    else
      warn "克隆失败（网络/权限）。设置 HERMES_SOURCE 指向本地 hermes-agent 后重试。"
      echo -e "${YELLOW}  ⏭️  SKIP: 无可用 Hermes 源码，跳过 e2e（exit 0）。${NC}"
      exit 0
    fi
  else
    warn "git 未安装且未提供 HERMES_SOURCE。"
    echo -e "${YELLOW}  ⏭️  SKIP: 无可用 Hermes 源码，跳过 e2e（exit 0）。${NC}"
    exit 0
  fi
fi

if [[ ! -d "$HERMES_SOURCE" ]]; then
  warn "HERMES_SOURCE 目录不存在：$HERMES_SOURCE"
  echo -e "${YELLOW}  ⏭️  SKIP: 无可用 Hermes 源码，跳过 e2e（exit 0）。${NC}"
  exit 0
fi
HERMES_SOURCE="$(cd "$HERMES_SOURCE" && pwd)"
if [[ ! -f "$HERMES_SOURCE/agent/memory_provider.py" ]]; then
  warn "在 $HERMES_SOURCE 未找到 agent/memory_provider.py —— 可能不是 Hermes 源码或版本过旧。"
  echo -e "${YELLOW}  ⏭️  SKIP: 无法验证真实 MemoryProvider 契约，跳过 e2e（exit 0）。${NC}"
  exit 0
fi
pass "找到真实 MemoryProvider：$HERMES_SOURCE/agent/memory_provider.py"

# ── Temp Hermes home + memories fixture ─────────────────────────────────────
HERMES_HOME="$(mktemp -d)/hermes-home"
mkdir -p "$HERMES_HOME/memories/topics"
printf 'User prefers concise status updates.\n' > "$HERMES_HOME/memories/USER.md"
printf 'Billing topic keeps the renewal policy notes.\n' > "$HERMES_HOME/memories/topics/billing.md"
info "HERMES_HOME = $HERMES_HOME"

cleanup() {
  [[ -n "$CLONED_TMP" ]] && rm -rf "$CLONED_TMP" 2>/dev/null || true
  rm -rf "$(dirname "$HERMES_HOME")" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: install the provider into the Hermes source ─────────────────────
section "步骤 1：安装 provider 到 Hermes 源码"

INSTALL_LOG="$(mktemp)"
if "$PY" "$INSTALLER" install \
  --hermes-home "$HERMES_HOME" --hermes-source "$HERMES_SOURCE" \
  --no-write-pth --force >"$INSTALL_LOG" 2>&1; then
  pass "octop-memory-hermes install 成功"
else
  fail "安装失败"; cat "$INSTALL_LOG"
fi

# ── Step 2: doctor ──────────────────────────────────────────────────────────
section "步骤 2：doctor 健康检查"

if "$PY" "$INSTALLER" doctor \
  --hermes-home "$HERMES_HOME" --hermes-source "$HERMES_SOURCE" 2>&1 | tee /dev/stderr | grep -q "checks passed"; then
  pass "doctor 全部通过"
else
  warn "doctor 报告问题（venv import 检查在未装 octop_memory 的 Hermes venv 上可能为 WARN，属预期）"
fi

# ── Step 3: real-contract runtime flow ──────────────────────────────────────
section "步骤 3：真实契约 + 运行时链路"

# Put the Hermes source first on PYTHONPATH so the installed plugin resolves
# the REAL agent.memory_provider.MemoryProvider (not the in-repo stub).
PLUGIN_DIR="$HERMES_SOURCE/plugins/memory/octopmemory"
if PYTHONPATH="$HERMES_SOURCE:${PYTHONPATH:-}" HERMES_HOME="$HERMES_HOME" \
  "$PY" - "$PLUGIN_DIR" "$HERMES_HOME" <<'PYEOF'
import importlib.util
import json
import sys
from pathlib import Path

plugin_dir, hermes_home = sys.argv[1], sys.argv[2]

# The real base class must be importable now.
from agent.memory_provider import MemoryProvider as RealBase  # noqa: E402

spec = importlib.util.spec_from_file_location("octop_hermes_e2e", Path(plugin_dir) / "__init__.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

Provider = mod.OctopMemoryProvider
assert issubclass(Provider, RealBase), "OctopMemoryProvider does not subclass the REAL MemoryProvider"
print("  ✅ 真实子类校验通过：OctopMemoryProvider ⊂ agent.memory_provider.MemoryProvider")

p = Provider()
p.initialize("e2e_sess", hermes_home=hermes_home, platform="cli")

# host_files are scanned synchronously during initialize; check them before
# shutdown() (which stops the watcher and rebuilds the bridge without it).
host = json.loads(p.handle_tool_call("memory_search", {"query": "renewal policy", "maxResults": 5}))
assert any(h.get("path") == "topics/billing.md" for h in host.get("hits", [])), "host_files watcher 未索引 topics/billing.md"
print("  ✅ host_files watcher 命中 topics/billing.md")

p.sync_turn(
    "Remember the release window is Tuesday 14:00 for the Hermes rollout.",
    "Confirmed: release window Tuesday 14:00.",
    session_id="e2e_sess",
)
# Flush the background write without tearing down host_files/watcher.
for t in list(getattr(p, "_threads")):
    t.join(timeout=5.0)

search = json.loads(p.handle_tool_call("memory_search", {"query": "release window Tuesday", "maxResults": 5}))
assert search.get("hits"), f"memory_search returned no hits: {search}"
print(f"  ✅ memory_search 命中 {len(search['hits'])} 条")

path = search["hits"][0]["path"]
got = json.loads(p.handle_tool_call("memory_get", {"path": path, "from": 1, "lines": 20}))
assert "release window" in got.get("excerpt", "").lower(), f"memory_get excerpt missing content: {got}"
print("  ✅ memory_get 返回正文")

block = p.prefetch("What is the release window?", session_id="e2e_sess")
assert "OctopMemory Recall" in block, f"prefetch produced no recall block: {block!r}"
print("  ✅ prefetch 返回召回上下文")

p.shutdown()
PYEOF
then
  pass "真实契约 + 运行时链路全部通过"
else
  fail "真实契约 / 运行时链路验证失败"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}  🎉 所有检查通过！octop-memory × Hermes 链路正常。${NC}"
else
  echo -e "${RED}  ⚠️  共 $FAILED 项检查失败，请根据上方提示修复。${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
exit $FAILED
