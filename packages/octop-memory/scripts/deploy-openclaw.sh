#!/usr/bin/env bash
#
# deploy-openclaw.sh — Deploy the OctopMemory plugin to an OpenClaw server.
#
# It does the following, all idempotent and safe to rerun:
#   1. Check prerequisites, with optional install for Node 20+, Python 3, and git.
#   2. Clone or update the octop-memory source tree.
#   3. Create an isolated Python venv and install octop-memory[cli].
#   4. Build the TS plugin shell with npm run build.
#   5. Write openclaw.json plugins.slots.memory = octopmemory.
#   6. Copy the plugin directory into ~/.openclaw/extensions/.
#   7. Run doctor checks.
#
# Usage:
#   REPO_URL=git@github.com:TencentCloud/octop-memory.git ./scripts/deploy-openclaw.sh
#   ./scripts/deploy-openclaw.sh --namespace openclaw__prod --install-node
#
# All settings can be overridden by env vars or matching --flag options.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults, overridable by env vars or matching --flag options
# ---------------------------------------------------------------------------
REPO_URL="${REPO_URL:-}"                                  # Repository URL, required when OCTOP_MEMORY_DIR does not exist.
OCTOP_MEMORY_DIR="${OCTOP_MEMORY_DIR:-$HOME/octop-memory}"                  # Source directory.
VENV="${VENV:-$HOME/.venv/octopmemory}"                   # Python venv
PROFILE="${PROFILE:-balanced}"                            # Recall/capture profile.
NAMESPACE="${NAMESPACE:-openclaw__prod}"                  # Memory namespace.
DB_PATH="${DB_PATH:-$HOME/.octopmemory/$NAMESPACE/memory.sqlite}"
OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
EXTENSIONS_DIR="${EXTENSIONS_DIR:-$HOME/.openclaw/extensions}"
WORKSPACE="${WORKSPACE:-$HOME/.openclaw/workspace}"
INSTALL_NODE="${INSTALL_NODE:-0}"                         # 1 = install Node 20 with apt automatically.
UPDATE="${UPDATE:-1}"                                     # 1 = run git pull when the source tree exists.
SETUP_DRY_RUN="${SETUP_DRY_RUN:-0}"                       # 1 = preview openclaw setup without writing.
PRETEND_VERSION="${PRETEND_VERSION:-0.2.0}"               # Version injected for non-git source trees.

PLUGIN_SUBDIR="plugins/openclaw/octopmemory"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
if [ -t 1 ]; then C_G=$'\033[32m'; C_Y=$'\033[33m'; C_R=$'\033[31m'; C_B=$'\033[36m'; C_0=$'\033[0m'
else C_G=; C_Y=; C_R=; C_B=; C_0=; fi
step() { printf "%s\n" "${C_B}==> $*${C_0}"; }
ok()   { printf "%s\n" "${C_G}  ✓ $*${C_0}"; }
warn() { printf "%s\n" "${C_Y}  ! $*${C_0}"; }
die()  { printf "%s\n" "${C_R}  ✗ $*${C_0}" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Parse --flag options, overriding env vars and defaults.
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url)        REPO_URL="$2"; shift 2;;
    --octop-memory-dir)          OCTOP_MEMORY_DIR="$2"; shift 2;;
    --venv)            VENV="$2"; shift 2;;
    --profile)         PROFILE="$2"; shift 2;;
    --namespace)       NAMESPACE="$2"; DB_PATH="$HOME/.octopmemory/$NAMESPACE/memory.sqlite"; shift 2;;
    --db-path)         DB_PATH="$2"; shift 2;;
    --openclaw-config) OPENCLAW_CONFIG="$2"; shift 2;;
    --extensions-dir)  EXTENSIONS_DIR="$2"; shift 2;;
    --workspace)       WORKSPACE="$2"; shift 2;;
    --install-node)    INSTALL_NODE=1; shift;;
    --no-update)       UPDATE=0; shift;;
    --setup-dry-run)   SETUP_DRY_RUN=1; shift;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0;;
    *) die "未知参数: $1(用 --help 查看)";;
  esac
done

PY="$VENV/bin/python"
OM="$VENV/bin/octop-memory"

# ---------------------------------------------------------------------------
# 1. Prerequisite checks
# ---------------------------------------------------------------------------
step "检查前置依赖"

command -v git >/dev/null 2>&1 || die "缺少 git。先装:sudo apt-get install -y git"
command -v python3 >/dev/null 2>&1 || die "缺少 python3。先装:sudo apt-get install -y python3 python3-venv"
python3 -c 'import venv' 2>/dev/null || die "缺少 python3-venv。先装:sudo apt-get install -y python3-venv"
ok "git / python3 OK"

node_major() { command -v node >/dev/null 2>&1 && node -v | sed 's/^v//' | cut -d. -f1 || echo 0; }
if [ "$(node_major)" -lt 20 ]; then
  if [ "$INSTALL_NODE" = "1" ]; then
    warn "Node < 20,正在安装 Node 20(NodeSource,需 sudo)…"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    die "需要 Node.js 20+(当前: $(node -v 2>/dev/null || echo 无))。加 --install-node 自动装,或手动安装后重跑。"
  fi
fi
ok "Node $(node -v)"

# ---------------------------------------------------------------------------
# 2. Fetch source
# ---------------------------------------------------------------------------
step "准备源码: $OCTOP_MEMORY_DIR"
if [ -d "$OCTOP_MEMORY_DIR/.git" ]; then
  if [ "$UPDATE" = "1" ]; then
    git -C "$OCTOP_MEMORY_DIR" pull --ff-only && ok "已 git pull"
  else
    ok "已存在,跳过更新(--no-update)"
  fi
elif [ -e "$OCTOP_MEMORY_DIR" ]; then
  ok "目录已存在(非 git),原样使用"
else
  [ -n "$REPO_URL" ] || die "目录 $OCTOP_MEMORY_DIR 不存在且未提供 REPO_URL。请设 --repo-url <仓库地址>。"
  git clone "$REPO_URL" "$OCTOP_MEMORY_DIR" && ok "已 clone"
fi
[ -f "$OCTOP_MEMORY_DIR/pyproject.toml" ] || die "$OCTOP_MEMORY_DIR 看起来不是 octop-memory 仓库(没有 pyproject.toml)。"

# ---------------------------------------------------------------------------
# 3. Python venv + core install
# ---------------------------------------------------------------------------
step "安装 Python core 到 venv: $VENV"
[ -x "$PY" ] || python3 -m venv "$VENV"
"$PY" -m pip install --quiet --upgrade pip
# hatch-vcs/setuptools-scm derive the version from git. If the source tree came
# from git archive or scp and has no .git directory, inject a pretend version.
# Use global SETUPTOOLS_SCM_PRETEND_VERSION because per-dist *_FOR_<NAME> is
# not recognized by hatch-vcs here.
if [ ! -d "$OCTOP_MEMORY_DIR/.git" ]; then
  export SETUPTOOLS_SCM_PRETEND_VERSION="${PRETEND_VERSION:-0.2.0}"
  warn "非 git 目录,注入 pretend 版本 $SETUPTOOLS_SCM_PRETEND_VERSION"
fi
( cd "$OCTOP_MEMORY_DIR" && "$PY" -m pip install --quiet -e ".[cli]" )
"$OM" --help >/dev/null || die "octop-memory CLI 安装失败"
ok "octop-memory 已安装($("$OM" --version 2>/dev/null | head -1))"

# ---------------------------------------------------------------------------
# 4. Build the TS plugin shell
# ---------------------------------------------------------------------------
step "构建 OpenClaw 插件壳"
PLUGIN_DIR="$OCTOP_MEMORY_DIR/$PLUGIN_SUBDIR"
[ -d "$PLUGIN_DIR" ] || die "找不到插件目录 $PLUGIN_DIR"
( cd "$PLUGIN_DIR" && npm install --no-audit --no-fund && npm run build )
[ -f "$PLUGIN_DIR/dist/index.js" ] || die "构建失败:没有 dist/index.js"
ok "dist/index.js 已生成"

# ---------------------------------------------------------------------------
# 5. Write OpenClaw config
# ---------------------------------------------------------------------------
step "写入 openclaw 配置: $OPENCLAW_CONFIG"
mkdir -p "$(dirname "$OPENCLAW_CONFIG")" "$(dirname "$DB_PATH")" "$WORKSPACE"
SETUP_ARGS=(
  openclaw setup
  --openclaw-config "$OPENCLAW_CONFIG"
  --profile "$PROFILE"
  --namespace "$NAMESPACE"
  --db-path "$DB_PATH"
  --workspace "$WORKSPACE"
  --bridge-python "$PY"
)
# Print the pending config first as a preview.
"$OM" "${SETUP_ARGS[@]}" --dry-run || true
if [ "$SETUP_DRY_RUN" = "1" ]; then
  warn "SETUP_DRY_RUN=1:仅预览,未写入 openclaw.json"
else
  "$OM" "${SETUP_ARGS[@]}"
  ok "已写入 $OPENCLAW_CONFIG"
fi

# ---------------------------------------------------------------------------
# 6. Deploy the plugin directory with cp instead of a symlink.
# ---------------------------------------------------------------------------
step "部署插件到 $EXTENSIONS_DIR/octopmemory"
mkdir -p "$EXTENSIONS_DIR"
rm -rf "$EXTENSIONS_DIR/octopmemory"
cp -r "$PLUGIN_DIR" "$EXTENSIONS_DIR/octopmemory"
ok "已拷贝(含 dist/)"

# ---------------------------------------------------------------------------
# 7. Self-check
# ---------------------------------------------------------------------------
step "运行 doctor 自检"
"$OM" openclaw doctor \
  --openclaw-config "$OPENCLAW_CONFIG" \
  --extensions-dir "$EXTENSIONS_DIR" || warn "doctor 有告警,按上面输出排查"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
cat <<EOF

${C_G}部署完成 ✅${C_0}

  namespace : $NAMESPACE
  db        : $DB_PATH
  venv      : $VENV
  插件      : $EXTENSIONS_DIR/octopmemory

下一步:
  • 让 openclaw agent 用记忆:
      openclaw agent --local --agent main --message "Search memory. Use memory_search."
  • 看存量 atom:
      $OM --backend sqlite --db "$DB_PATH" --namespace "$NAMESPACE" atom list --limit 50
  • 跑语义去重(先 dry-run):
      $OM --backend sqlite --db "$DB_PATH" --namespace "$NAMESPACE" consolidate run --dry-run

以后升级:重新跑本脚本即可(幂等,会 git pull + 重建 + 重新部署)。
EOF
