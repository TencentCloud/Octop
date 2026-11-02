#!/bin/bash
# 小说初始化脚本
# 为一部新小说创建工作区：初始化 output 目录、重置记忆文件
# 用法: ./init-novel.sh <小说名称> [--clean]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$SKILL_DIR/output"
LEARNINGS_DIR="$SKILL_DIR/.learnings"

usage() {
    cat << EOF
用法: $(basename "$0") <小说名称> [选项]

为一部新小说初始化工作区。

参数:
  小说名称     小说的名称

选项:
  --clean      清除旧的记忆文件和输出（重新开始）
  -h, --help   显示此帮助信息

示例:
  $(basename "$0") 逆天丹帝
  $(basename "$0") 都市之王 --clean

EOF
}

log_info() { echo -e "${GREEN}[信息]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
log_step() { echo -e "${CYAN}[步骤]${NC} $1"; }

NOVEL_NAME=""
CLEAN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean) CLEAN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo -e "${RED}[错误]${NC} 未知选项: $1"; usage; exit 1 ;;
        *)
            if [ -z "$NOVEL_NAME" ]; then
                NOVEL_NAME="$1"
            else
                echo -e "${RED}[错误]${NC} 意外参数: $1"; usage; exit 1
            fi
            shift ;;
    esac
done

if [ -z "$NOVEL_NAME" ]; then
    echo -e "${RED}[错误]${NC} 请提供小说名称"
    usage
    exit 1
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  爽文小说生成器 - 初始化工作区${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""
echo -e "  小说名称: ${GREEN}《${NOVEL_NAME}》${NC}"
echo -e "  清除旧数据: $([ "$CLEAN" = true ] && echo "${YELLOW}是${NC}" || echo "否")"
echo ""

if [ "$CLEAN" = true ]; then
    log_step "清除旧的输出文件..."
    rm -rf "$OUTPUT_DIR"/*.md 2>/dev/null || true

    log_step "重置记忆文件..."

    cat > "$LEARNINGS_DIR/CHARACTERS.md" << 'HEREDOC'
# 角色档案

记录所有已出场角色的信息，每次生成新章节前必读。

**更新规则**：新角色出场时添加，角色状态变化时更新，角色死亡时标记。

---
HEREDOC

    cat > "$LEARNINGS_DIR/LOCATIONS.md" << 'HEREDOC'
# 地点档案

记录所有已出现的地点信息，确保空间描写一致。

**更新规则**：新地点出现时添加，地点发生变化（被毁/升级）时更新。

---
HEREDOC

    cat > "$LEARNINGS_DIR/PLOT_POINTS.md" << 'HEREDOC'
# 关键情节档案

记录所有关键情节点，维护故事主线连贯性。

**更新规则**：每章生成后记录关键事件，标注是否有未解决的伏笔。

---
HEREDOC

    cat > "$LEARNINGS_DIR/STORY_BIBLE.md" << 'HEREDOC'
# 故事圣经

世界观核心设定，一经确立不可随意修改。新设定补充时追加。

---
HEREDOC

    cat > "$LEARNINGS_DIR/ERRORS.md" << 'HEREDOC'
# 生成错误日志

记录生成过程中出现的问题，用于优化后续创作。

**更新规则**：生成失败、质量不达标、连贯性问题时记录。

---
HEREDOC

    log_info "旧数据已清除"
fi

log_step "创建输出目录..."
mkdir -p "$OUTPUT_DIR"

log_step "创建 .gitkeep..."
touch "$OUTPUT_DIR/.gitkeep"

echo ""
log_info "《${NOVEL_NAME}》工作区初始化完成！"
echo ""
echo "后续步骤:"
echo "  1. 向 AI 代理描述你的小说方向/题材"
echo "  2. 代理会自动完善提示词，保存到 output/提示词.md"
echo "  3. 确认提示词后，代理生成大纲到 output/大纲.md"
echo "  4. 逐章生成，每章保存为 output/第XX章_章名.md"
echo ""
echo "记忆文件位置:"
echo "  角色档案:   $LEARNINGS_DIR/CHARACTERS.md"
echo "  地点档案:   $LEARNINGS_DIR/LOCATIONS.md"
echo "  情节档案:   $LEARNINGS_DIR/PLOT_POINTS.md"
echo "  世界观:     $LEARNINGS_DIR/STORY_BIBLE.md"
echo "  错误日志:   $LEARNINGS_DIR/ERRORS.md"
echo ""
