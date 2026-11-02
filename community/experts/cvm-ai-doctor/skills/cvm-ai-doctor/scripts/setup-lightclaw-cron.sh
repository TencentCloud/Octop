#!/bin/bash
# CVM AI Doctor 定时巡检配置脚本 (LightClaw Cron)

set -e

echo "🚀 配置 CVM AI Doctor 定时巡检 (LightClaw Cron)..."
echo ""

# 检查 jq 是否安装
if ! command -v jq &> /dev/null; then
    echo "❌ 错误: 需要安装 jq"
    echo "   macOS: brew install jq"
    echo "   Ubuntu: sudo apt install jq"
    exit 1
fi

# 检查 LightClaw 是否可用
if ! command -v lightclaw &> /dev/null; then
    echo "❌ 错误: lightclaw 命令不可用"
    echo "   请确保已安装 LightClaw 并配置了 PATH"
    exit 1
fi

# 检查 LightClaw 服务是否运行
if ! curl -s http://127.0.0.1:8088/health > /dev/null 2>&1; then
    echo "⚠️  警告: LightClaw 服务未运行"
    echo "   任务将保存到 jobs.json,但不会立即生效"
    echo "   请运行: lightclaw server start"
    echo ""
    read -p "是否继续配置? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📋 请选择巡检频率:"
echo "  1. 每分钟 (高频,成本 ~$4/天)"
echo "  2. 每 5 分钟 (推荐,成本 ~$0.9/天)"
echo "  3. 每 15 分钟 (低频,成本 ~$0.3/天)"
echo "  4. 自定义"
echo ""
read -p "请选择 [1-4]: " -n 1 -r choice
echo ""

case $choice in
    1)
        CRON_EXPR="*/1 * * * *"
        FREQ_DESC="每分钟"
        ;;
    2)
        CRON_EXPR="*/5 * * * *"
        FREQ_DESC="每 5 分钟"
        ;;
    3)
        CRON_EXPR="*/15 * * * *"
        FREQ_DESC="每 15 分钟"
        ;;
    4)
        echo "请输入 cron 表达式 (例如: */10 * * * * 表示每 10 分钟):"
        read -r CRON_EXPR
        FREQ_DESC="自定义 ($CRON_EXPR)"
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo ""
echo "📋 请选择输出渠道:"
echo "  1. dashboard (Dashboard 面板)"
echo "  2. dingtalk (钉钉)"
echo "  3. qq (QQ)"
echo ""
read -p "请选择 [1-3]: " -n 1 -r channel_choice
echo ""

case $channel_choice in
    1) CHANNEL="dashboard" ;;
    2) CHANNEL="dingtalk" ;;
    3) CHANNEL="qq" ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo ""
echo "📋 配置摘要:"
echo "  频率: $FREQ_DESC"
echo "  Cron 表达式: $CRON_EXPR"
echo "  输出渠道: $CHANNEL"
echo ""
read -p "确认配置? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 1
fi

echo ""
echo "🔧 创建定时任务..."

# 1. 快速巡检任务
echo "  → 创建快速巡检任务..."
JOB_ID_QUICK=$(lightclaw cron create \
  --type agent \
  --name "CVM Quick Check - $FREQ_DESC" \
  --cron "$CRON_EXPR" \
  --channel "$CHANNEL" \
  --timezone "Asia/Shanghai" \
  --text "使用 CVM AI Doctor 技能执行快速巡检。如果所有指标正常,只返回'系统正常 ✅';如果发现警告或严重问题,返回详细诊断结果和修复建议。重点检查: CPU/内存/磁盘/网络状态。" \
  --mode final 2>/dev/null | jq -r '.id')

if [ -z "$JOB_ID_QUICK" ]; then
    echo "❌ 快速巡检任务创建失败"
    exit 1
fi

echo "  ✅ 快速巡检任务已创建: $JOB_ID_QUICK"

# 2. 深度分析任务 (每小时)
echo "  → 创建深度分析任务 (每小时)..."
JOB_ID_DEEP=$(lightclaw cron create \
  --type agent \
  --name "CVM Deep Analysis - Hourly" \
  --cron "0 * * * *" \
  --channel "$CHANNEL" \
  --timezone "Asia/Shanghai" \
  --text "使用 CVM AI Doctor 技能执行深度诊断。分析系统性能瓶颈,检查系统日志中的错误和警告,提供优化建议。重点关注: 资源饱和度、日志异常、进程状态。" \
  --mode final 2>/dev/null | jq -r '.id')

if [ -z "$JOB_ID_DEEP" ]; then
    echo "❌ 深度分析任务创建失败"
    exit 1
fi

echo "  ✅ 深度分析任务已创建: $JOB_ID_DEEP"

# 3. 每日完整体检 (凌晨 3 点)
echo "  → 创建每日体检任务 (凌晨 3 点)..."
JOB_ID_DAILY=$(lightclaw cron create \
  --type agent \
  --name "CVM Daily Health Check" \
  --cron "0 3 * * *" \
  --channel "$CHANNEL" \
  --timezone "Asia/Shanghai" \
  --text "使用 CVM AI Doctor 技能执行完整健康体检。检查项目包括: 资源饱和度、系统日志审查、磁盘 SMART 健康度、硬件健康状态、NTP 时间同步。生成详细健康报告,包括历史趋势和预防性建议。" \
  --mode final 2>/dev/null | jq -r '.id')

if [ -z "$JOB_ID_DAILY" ]; then
    echo "❌ 每日体检任务创建失败"
    exit 1
fi

echo "  ✅ 每日体检任务已创建: $JOB_ID_DAILY"

echo ""
echo "✅ 所有任务创建完成!"
echo ""

# 测试执行
echo "🧪 测试执行快速巡检任务..."
if curl -s http://127.0.0.1:8088/health > /dev/null 2>&1; then
    lightclaw cron run "$JOB_ID_QUICK" > /dev/null 2>&1 && echo "  ✅ 测试执行成功" || echo "  ⚠️  测试执行失败 (任务可能需要一些时间)"
else
    echo "  ⚠️  LightClaw 服务未运行,跳过测试"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 任务列表"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
lightclaw cron list | jq -r '.[] | "  \(.id)  [\(.enabled | if . then "✓" else "✗" end)]  \(.name)  (\(.schedule.cron))"'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 管理命令"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  查看所有任务:  lightclaw cron list"
echo "  查看任务详情:  lightclaw cron get <JOB_ID>"
echo "  暂停任务:      lightclaw cron pause <JOB_ID>"
echo "  恢复任务:      lightclaw cron resume <JOB_ID>"
echo "  删除任务:      lightclaw cron delete <JOB_ID>"
echo "  手动执行:      lightclaw cron run <JOB_ID>"
echo ""
echo "  快速巡检 ID:   $JOB_ID_QUICK"
echo "  深度分析 ID:   $JOB_ID_DEEP"
echo "  每日体检 ID:   $JOB_ID_DAILY"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 相关文件"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  任务配置:      ~/.lightclaw/jobs.json"
echo "  执行日志:      ~/.lightclaw/logs/cron.log"
echo "  Agent 日志:    ~/.lightclaw/logs/agent.log"
echo ""
echo "🎉 配置完成! 定时巡检已启动。"
