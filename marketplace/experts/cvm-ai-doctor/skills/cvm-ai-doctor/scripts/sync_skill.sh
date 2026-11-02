#!/usr/bin/env bash
# sync_skill.sh — 将 cvm-ai-doctor 核心文件同步到目标目录
# 排除: docs/, _* 前缀目录, 隐藏文件/目录(.git, .venv, .workbuddy 等), generated-images/
# 用法:
#   ./scripts/sync_skill.sh                        # 同步到默认目标
#   ./scripts/sync_skill.sh /path/to/target        # 同步到指定目标
#   ./scripts/sync_skill.sh --dry-run               # 预览，不实际复制
#   ./scripts/sync_skill.sh --dry-run /path/to/target

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_TARGET="$HOME/vstation/finnie/src/lightclaw/agent/skills/cvm-ai-doctor"

# ── 参数解析 ──────────────────────────────────────────
DRY_RUN=false
TARGET=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        *)         TARGET="$arg" ;;
    esac
done

TARGET="${TARGET:-$DEFAULT_TARGET}"

# ── 颜色 ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { printf "${CYAN}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
err()   { printf "${RED}[ERR]${NC}   %s\n" "$*" >&2; }

# ── 检查源目录 ────────────────────────────────────────
if [ ! -d "$SRC_DIR/.git" ]; then
    err "源目录不是 git 仓库: $SRC_DIR"
    exit 1
fi

# ── 收集 git 版本信息 ────────────────────────────────
cd "$SRC_DIR"
GIT_COMMIT=$(git rev-parse HEAD)
GIT_SHORT=$(git rev-parse --short HEAD)
GIT_AUTHOR=$(git log -1 --format='%an')
GIT_DATE=$(git log -1 --format='%ai')
GIT_SUBJECT=$(git log -1 --format='%s')
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_DIRTY=$(git diff --quiet && git diff --cached --quiet && echo "clean" || echo "dirty")
GIT_COMMIT_COUNT=$(git rev-list --count HEAD)
SYNC_TIME=$(date '+%Y-%m-%d %H:%M:%S %z')

# ── 打印同步摘要 ──────────────────────────────────────
echo ""
info "cvm-ai-doctor skill 同步工具"
echo "  源目录:  $SRC_DIR"
echo "  目标:    $TARGET"
echo "  分支:    $GIT_BRANCH"
echo "  提交:    $GIT_SHORT ($GIT_SUBJECT)"
echo "  状态:    $GIT_DIRTY"
if $DRY_RUN; then
    warn "DRY-RUN 模式 — 仅预览，不执行复制"
fi
echo ""

# ── rsync 排除规则 ────────────────────────────────────
# docs/          — 开发文档，不属于 skill 发布物
# _*/            — 归档/备份目录
# .*/            — 隐藏文件/目录 (.git, .venv, .workbuddy, .DS_Store)
# generated-images/ — AI 生成的图片，不属于 skill
# version.ini    — 目标侧生成，不从源复制
# AUDIT-*.txt    — 开发审计文件，不属于 skill 发布物
# AUDIT-*.md     — 开发审计报告，不属于 skill 发布物
RSYNC_EXCLUDES=(
    --exclude='docs/'
    --exclude='_*/'
    --exclude='.*'
    --exclude='generated-images/'
    --exclude='version.ini'
    --exclude='AUDIT-*.txt'
    --exclude='AUDIT-*.md'
)

# ── 执行同步 ──────────────────────────────────────────
if $DRY_RUN; then
    info "将同步以下文件:"
    rsync -avn --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR/" "$TARGET/" 2>/dev/null \
        | grep -v '^\.' | grep -v '^$' | grep -v 'sent\|total\|sending' | head -50
    echo ""
    info "以上为预览，实际执行请去掉 --dry-run"
    exit 0
fi

# 创建目标目录
mkdir -p "$TARGET"

# rsync 同步: 镜像模式(--delete 清理目标中多余文件)
rsync -av --delete "${RSYNC_EXCLUDES[@]}" "$SRC_DIR/" "$TARGET/"

# ── 生成 version.ini ─────────────────────────────────
cat > "$TARGET/version.ini" << EOF
[version]
commit       = $GIT_COMMIT
short        = $GIT_SHORT
branch       = $GIT_BRANCH
author       = $GIT_AUTHOR
date         = $GIT_DATE
subject      = $GIT_SUBJECT
commit_count = $GIT_COMMIT_COUNT
tree_status  = $GIT_DIRTY

[sync]
synced_at    = $SYNC_TIME
EOF

# ── 完成 ──────────────────────────────────────────────
echo ""
ok "同步完成!"
echo ""
info "version.ini 内容:"
cat "$TARGET/version.ini"
echo ""

# 如果工作区有未提交改动，给个提醒
if [ "$GIT_DIRTY" = "dirty" ]; then
    echo ""
    warn "工作区有未提交的改动，同步的是磁盘上的实际文件（包含未提交修改）"
    warn "version.ini 中 tree_status=dirty 标记了这一点"
fi
