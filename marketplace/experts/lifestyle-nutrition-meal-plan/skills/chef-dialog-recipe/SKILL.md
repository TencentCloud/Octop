---
name: chef-dialog-recipe
description: "专业厨师对话食谱生成技能：完整的交互式工作流，包含厨师视角生成、AI分析审查、综合优化"
version: "1.0.0"
author: "肖柏然 (中国深圳)"
contact: "xiaoboren0@gmail.com"
license: "MIT"
metadata:
  openclaw:
    emoji: "👨🍳"
    requires: 
      bins: ["bash"]
    install:
      - id: "scripts"
        kind: "shell"
        command: "./install.sh"
        label: "安装脚本"
    examples:
      - input: "我想吃东坡肉，作为一个专业的厨师，你会怎么做？"
        output: "生成专业厨师视角食谱 → AI分析报告 → 完整优化食谱"
---
# 专业厨师对话食谱生成技能

## 核心功能
1. **厨师视角生成**：从专业厨师角度描述烹饪过程
2. **AI分析审查**：另一个AI分析食谱潜在问题
3. **综合优化**：生成完整优化的食谱
4. **时间容错系统**：提供±时间范围
5. **安全操作规范**：每个步骤标注安全等级

## 技术特点
- 完整的Bash脚本实现
- 支持多种中国菜品
- 输出格式：Markdown、JSON、Text
- 预置菜品模板：东坡肉、麻婆豆腐

## 安装
```bash
./install.sh
```

## 使用
```bash
./chef-dialog.sh "菜品名称"
```

## 示例输出
输入：`东坡肉`
输出：包含食材清单、时间线、烹饪流程、安全提示的完整食谱