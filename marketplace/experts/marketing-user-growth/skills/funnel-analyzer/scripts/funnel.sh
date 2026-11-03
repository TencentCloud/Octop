#!/usr/bin/env bash
set -euo pipefail

# Funnel Analyzer — 漏斗分析工具
# Usage: bash scripts/funnel.sh <command> [args...]

CMD="${1:-help}"
shift 2>/dev/null || true

show_help() {
  cat <<'EOF'
Funnel Analyzer — 漏斗分析工具

Commands:
  create <name> <steps>         创建漏斗 (步骤名:数量,...)
  diagnose <steps>              诊断流失环节
  benchmark <industry>          行业转化率对标 (ecommerce|saas|content|app|recruitment)
  optimize <steps>              生成优化建议
  report <steps> [name]         完整分析报告
  compare <funnelA> <funnelB>   对比两个漏斗
  help                         显示帮助

Examples:
  funnel.sh create "电商购买" "浏览:10000,加购:3000,下单:1500,支付:1200,完成:1000"
  funnel.sh diagnose "浏览:10000,加购:3000,下单:1500,支付:1200"
  funnel.sh benchmark ecommerce
  funnel.sh optimize "注册:5000,激活:2000,留存:800,付费:200"
  funnel.sh compare "A组:1000,500,200,100" "B组:1000,600,300,150"
  funnel.sh report "注册:5000,激活:2000,留存:800,付费:200" "SaaS产品"

  Powered by BytesAgain | bytesagain.com | hello@bytesagain.com
EOF
}

parse_steps() {
  local data="$1"
  echo "$data"
}

cmd_create() {
  local name="${1:?请提供漏斗名称}"
  local steps="${2:?请提供步骤数据 (步骤名:数量,...)}"

  echo "## 🔽 转化漏斗: ${name}"
  echo ""
  echo '```'

  IFS=',' read -ra pairs <<< "$steps"
  local first_val=0
  local prev_val=0
  local idx=0
  local max_width=40

  for pair in "${pairs[@]}"; do
    local label="${pair%%:*}"
    local val="${pair##*:}"
    if (( idx == 0 )); then
      first_val=$val
    fi
    prev_val=$val
    idx=$((idx + 1))
  done

  idx=0
  prev_val=0
  for pair in "${pairs[@]}"; do
    local label="${pair%%:*}"
    local val="${pair##*:}"
    local bar_width=0
    if (( first_val > 0 )); then
      bar_width=$((val * max_width / first_val))
    fi
    (( bar_width < 1 )) && bar_width=1

    local pct_total=0
    if (( first_val > 0 )); then
      pct_total=$((val * 100 / first_val))
    fi

    local pct_step=100
    if (( idx > 0 && prev_val > 0 )); then
      pct_step=$((val * 100 / prev_val))
    fi

    # Draw funnel bar
    local pad=$(( (max_width - bar_width) / 2 ))
    local spaces=""
    for ((i=0; i<pad; i++)); do spaces+=" "; done
    local bar=""
    for ((i=0; i<bar_width; i++)); do bar+="█"; done

    printf "  %s%s  %-10s %6d  (%3d%% 总转化" "$spaces" "$bar" "$label" "$val" "$pct_total"
    if (( idx > 0 )); then
      printf " | %3d%% 步转化" "$pct_step"
    fi
    echo ")"

    prev_val=$val
    idx=$((idx + 1))
  done

  echo ""
  echo "  总转化率: $((prev_val * 100 / first_val))% (${prev_val}/${first_val})"
  echo '```'
  echo ""
  echo "✅ 漏斗创建成功"
}

cmd_diagnose() {
  local steps="${1:?请提供步骤数据}"

  echo "## 🔍 漏斗诊断报告"
  echo ""

  IFS=',' read -ra pairs <<< "$steps"
  local prev_label=""
  local prev_val=0
  local first_val=0
  local idx=0
  local worst_drop=0
  local worst_step=""

  echo "| 步骤 | 数量 | 步骤转化率 | 流失数 | 流失率 | 严重度 |"
  echo "|------|------|-----------|--------|--------|--------|"

  for pair in "${pairs[@]}"; do
    local label="${pair%%:*}"
    local val="${pair##*:}"
    if (( idx == 0 )); then
      first_val=$val
      printf "| %-8s | %6d | -      | -    | -    | -    |\n" "$label" "$val"
    else
      local conv_rate=$((val * 100 / prev_val))
      local drop=$((prev_val - val))
      local drop_rate=$((drop * 100 / prev_val))
      local severity="🟢"
      if (( drop_rate > 70 )); then
        severity="🔴 严重"
      elif (( drop_rate > 50 )); then
        severity="🟠 警告"
      elif (( drop_rate > 30 )); then
        severity="🟡 注意"
      fi
      if (( drop_rate > worst_drop )); then
        worst_drop=$drop_rate
        worst_step="${prev_label} → ${label}"
      fi
      printf "| %-8s | %6d | %3d%%   | %5d | %3d%% | %s |\n" "$label" "$val" "$conv_rate" "$drop" "$drop_rate" "$severity"
    fi
    prev_label="$label"
    prev_val=$val
    idx=$((idx + 1))
  done

  echo ""
  echo "### 🚨 最大流失环节"
  echo ""
  echo "**${worst_step}** — 流失率 ${worst_drop}%"
  echo ""
  echo "### 💡 可能原因"
  echo ""
  echo "1. 用户体验障碍（页面加载慢、操作复杂）"
  echo "2. 信息不足或不清晰（缺乏信任信号）"
  echo "3. 动机不足（价值未传达清楚）"
  echo "4. 外部干扰（竞品、价格敏感）"
  echo "5. 技术问题（表单错误、兼容性）"
}

cmd_benchmark() {
  local industry="${1:?请指定行业: ecommerce|saas|content|app|recruitment}"

  echo "## 📊 行业转化率对标: ${industry}"
  echo ""

  case "$industry" in
    ecommerce)
      cat <<'EOF'
| 步骤 | 行业中位数 | 优秀值 | 顶尖值 |
|------|-----------|--------|--------|
| 浏览 → 加购 | 8-12% | 15% | 20%+ |
| 加购 → 下单 | 30-40% | 50% | 65%+ |
| 下单 → 支付 | 70-80% | 85% | 92%+ |
| 支付 → 完成 | 90-95% | 97% | 99%+ |
| 整体转化率 | 2-4% | 5% | 8%+ |

**关键指标**:
- 购物车放弃率: 60-80% (行业常态)
- 平均客单价关联复购率
- 移动端 vs 桌面端转化差异通常在30-50%
EOF
      ;;
    saas)
      cat <<'EOF'
| 步骤 | 行业中位数 | 优秀值 | 顶尖值 |
|------|-----------|--------|--------|
| 访问 → 注册 | 2-5% | 8% | 15%+ |
| 注册 → 激活 | 20-40% | 50% | 70%+ |
| 激活 → 留存(M1) | 40-60% | 70% | 85%+ |
| 留存 → 付费 | 2-5% | 8% | 15%+ |
| 试用→付费 | 15-25% | 30% | 50%+ |

**关键指标**:
- Time to Value (TTV): 越短越好
- 激活事件定义是关键
- PLG产品注册转化通常高于传统SaaS
EOF
      ;;
    content)
      cat <<'EOF'
| 步骤 | 行业中位数 | 优秀值 | 顶尖值 |
|------|-----------|--------|--------|
| 曝光 → 点击 | 1-3% | 5% | 8%+ |
| 点击 → 阅读 | 40-60% | 70% | 85%+ |
| 阅读 → 互动 | 2-5% | 8% | 15%+ |
| 互动 → 转化 | 1-3% | 5% | 10%+ |

**关键指标**:
- 跳出率: 40-60% (内容页)
- 平均阅读时长
- 分享率 > 2% 算优秀
EOF
      ;;
    app)
      cat <<'EOF'
| 步骤 | 行业中位数 | 优秀值 | 顶尖值 |
|------|-----------|--------|--------|
| 广告展示 → 点击 | 1-2% | 3% | 5%+ |
| 点击 → 商店页 | 50-70% | 80% | 90%+ |
| 商店页 → 下载 | 25-35% | 45% | 60%+ |
| 下载 → 首次打开 | 70-80% | 85% | 95%+ |
| 打开 → 注册 | 30-50% | 60% | 75%+ |
| D1留存 | 25-35% | 40% | 50%+ |
| D7留存 | 10-15% | 20% | 30%+ |
| D30留存 | 5-8% | 12% | 20%+ |
EOF
      ;;
    recruitment)
      cat <<'EOF'
| 步骤 | 行业中位数 | 优秀值 | 顶尖值 |
|------|-----------|--------|--------|
| 投递 → 筛选通过 | 15-25% | 30% | 40%+ |
| 筛选 → 面试 | 40-60% | 70% | 80%+ |
| 面试 → Offer | 15-25% | 35% | 50%+ |
| Offer → 入职 | 70-85% | 90% | 95%+ |
| 整体转化率 | 1-3% | 5% | 8%+ |
EOF
      ;;
    *)
      echo "❌ 未知行业: ${industry}"
      echo "可选: ecommerce, saas, content, app, recruitment"
      return 1
      ;;
  esac
}

cmd_optimize() {
  local steps="${1:?请提供步骤数据}"

  echo "## 🚀 漏斗优化建议"
  echo ""

  IFS=',' read -ra pairs <<< "$steps"
  local prev_val=0
  local idx=0

  for pair in "${pairs[@]}"; do
    local label="${pair%%:*}"
    local val="${pair##*:}"

    if (( idx > 0 )); then
      local drop_rate=$(( (prev_val - val) * 100 / prev_val ))
      if (( drop_rate > 30 )); then
        echo "### 🎯 ${label} (流失率 ${drop_rate}%)"
        echo ""
        case $idx in
          1)
            cat <<'EOF'
**优化方向: 首次转化**
- 📝 简化注册/加购流程，减少必填字段
- 🎁 提供首次优惠/免费试用
- 🏷️ 突出价值主张和信任标志
- ⚡ 优化页面加载速度 (<3秒)
- 📱 确保移动端体验流畅
EOF
            ;;
          2)
            cat <<'EOF'
**优化方向: 深度参与**
- 📧 设置自动化引导邮件/消息
- 🎯 简化核心功能的操作路径
- 💡 提供新手引导和帮助文档
- 🔔 适时的提醒推送
- 📊 展示使用进度和成就
EOF
            ;;
          3)
            cat <<'EOF'
**优化方向: 转化促成**
- 💰 优化定价和付费体验
- 🛡️ 添加安全保障（退款承诺等）
- ⏰ 创造适度紧迫感（限时优惠）
- 📞 提供人工客服支持
- 🎁 推出限定促销活动
EOF
            ;;
          *)
            cat <<'EOF'
**通用优化方向**
- 收集流失用户反馈
- A/B测试关键页面
- 简化操作步骤
- 增加社会证明（评价/案例）
- 优化错误提示和异常处理
EOF
            ;;
        esac
        echo ""
      fi
    fi

    prev_val=$val
    idx=$((idx + 1))
  done

  echo "### 📋 优化优先级矩阵"
  echo ""
  echo '```'
  echo "  影响大 │ ② 快速改善    │ ① 优先优化"
  echo "        │ (低成本高收益) │ (核心投入)"
  echo "  ──────┼───────────────┼──────────────"
  echo "  影响小 │ ④ 暂时搁置    │ ③ 计划改善"
  echo "        │ (低优先级)     │ (有余力再做)"
  echo "        └───────────────┴──────────────"
  echo "         容易实现           难以实现"
  echo '```'
}

cmd_report() {
  local steps="${1:?请提供步骤数据}"
  local name="${2:-转化漏斗}"

  echo "# 📊 漏斗分析报告: ${name}"
  echo ""
  echo "**报告时间**: $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""
  echo "---"
  echo ""

  echo "## 1. 漏斗概览"
  echo ""
  cmd_create "$name" "$steps"

  echo ""
  echo "## 2. 流失诊断"
  echo ""
  cmd_diagnose "$steps"

  echo ""
  echo "## 3. 优化建议"
  echo ""
  cmd_optimize "$steps"
}

cmd_compare() {
  local funnelA="${1:?请提供漏斗A数据}"
  local funnelB="${2:?请提供漏斗B数据}"

  local nameA="${funnelA%%:*}"
  local dataA="${funnelA#*:}"
  local nameB="${funnelB%%:*}"
  local dataB="${funnelB#*:}"

  echo "## ⚖️ 漏斗对比: ${nameA} vs ${nameB}"
  echo ""

  IFS=',' read -ra valsA <<< "$dataA"
  IFS=',' read -ra valsB <<< "$dataB"

  local len=${#valsA[@]}
  (( ${#valsB[@]} < len )) && len=${#valsB[@]}

  echo "| 步骤 | ${nameA} | ${nameB} | 差异 | 胜出 |"
  echo "|------|---------|---------|------|------|"

  local prevA=0
  local prevB=0
  for ((i=0; i<len; i++)); do
    local vA="${valsA[$i]}"
    local vB="${valsB[$i]}"

    if (( i == 0 )); then
      printf "| 步骤%d | %s | %s | - | - |\n" "$((i+1))" "$vA" "$vB"
    else
      local rateA=$((vA * 100 / prevA))
      local rateB=$((vB * 100 / prevB))
      local diff=$((rateB - rateA))
      local winner="🏆${nameB}"
      if (( diff < 0 )); then
        winner="🏆${nameA}"
        diff=$((-diff))
      elif (( diff == 0 )); then
        winner="平手"
      fi
      printf "| 步骤%d | %s (%d%%) | %s (%d%%) | %+d%% | %s |\n" \
        "$((i+1))" "$vA" "$rateA" "$vB" "$rateB" "$((rateB - rateA))" "$winner"
    fi

    prevA=$vA
    prevB=$vB
  done

  echo ""
  local totalA=$((prevA * 100 / ${valsA[0]}))
  local totalB=$((prevB * 100 / ${valsB[0]}))
  echo "### 📊 总转化率"
  echo "- **${nameA}**: ${totalA}%"
  echo "- **${nameB}**: ${totalB}%"
  if (( totalB > totalA )); then
    echo "- 🏆 **${nameB}** 总转化率高出 $((totalB - totalA))个百分点"
  elif (( totalA > totalB )); then
    echo "- 🏆 **${nameA}** 总转化率高出 $((totalA - totalB))个百分点"
  else
    echo "- 🤝 两者总转化率相同"
  fi
}

case "$CMD" in
  create)     cmd_create "$@" ;;
  diagnose)   cmd_diagnose "$@" ;;
  benchmark)  cmd_benchmark "$@" ;;
  optimize)   cmd_optimize "$@" ;;
  report)     cmd_report "$@" ;;
  compare)    cmd_compare "$@" ;;
  help|--help) show_help ;;
  *)
    echo "❌ 未知命令: $CMD"
    echo "运行 'funnel.sh help' 查看帮助"
    exit 1
    ;;
esac
