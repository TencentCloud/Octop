---
name: auto-data-analysis-claw
description: "自动化财务与业务数据分析，深度挖掘数据价值，生成专业报表。激活场景：用户提供财务报表（利润表、资产负债表、现金流量表）、业务数据（销售数据、运营数据、客户数据、成本数据），或要求进行数据分析、数据挖掘、报表生成、KPI计算、趋势分析、差异分析、同比环比分析、多维分析、数据清洗。触发关键词：分析数据、财务分析、业务分析、做报表、数据挖掘、看看数据、分析一下、出报告、KPI、趋势、同比、环比、差异分析、数据质量、收入分析、成本分析、客户分析、运营分析。"
---

# 自动化数据分析虾 🦐

对财务、业务数据进行深度挖掘，自动完成复杂业务逻辑处理，产出专业报表。

## 工作流程

### 1. 理解需求

明确以下要素（缺少则向用户确认）：
- **数据来源**：文件路径/格式（CSV、Excel）或描述数据结构
- **分析目标**：用户最关心什么？（盈利？增长？效率？风险？）
- **时间范围**：分析哪个周期？
- **对比基准**：与上期比？与预算比？与行业比？

### 2. 数据加载与质量评估

使用 `scripts/analyze.py profile` 检查数据：
```bash
python3 scripts/analyze.py profile {文件路径}
```

关注：行数、字段类型、空值率、数值范围是否合理。发现异常数据立即告知用户。

### 3. 数据清洗

```bash
python3 scripts/analyze.py clean {文件路径} -o {输出路径}
```

- 空值处理：数值列用中位数填充，分类列用众数填充
- 全空列自动删除
- 清洗后向用户确认数据量变化

### 4. 核心分析（根据场景选择）

#### 通用分析
```bash
# 差异分析（环比、同比、分组对比）
python3 scripts/analyze.py variance {文件} --value {数值列} --period {时间列} --group {分组列}

# 趋势分析
python3 scripts/analyze.py trend {文件} --date {日期列} --value {数值列} --freq M

# 相关性分析
python3 scripts/analyze.py correlate {文件} --columns {列1} {列2} ...
```

#### KPI 计算
准备配置 JSON，然后执行：
```bash
python3 scripts/analyze.py kpi {文件} --config {kpi_config.json}
```

配置格式：
```json
{"kpis": [
  {"name": "总收入", "formula": "sum(revenue)"},
  {"name": "平均毛利率", "formula": "mean(gross_margin_pct)"},
  {"name": "订单数", "formula": "count(order_id)"}
]}
```

### 5. 深度分析参考

根据分析场景加载对应参考资料：
- **财务数据**：阅读 `references/financial-metrics.md`（指标体系与公式）
- **业务数据**：阅读 `references/business-analysis-patterns.md`（分析场景与方法论）
- **生成报表时**：阅读 `references/report-templates.md`（结构与格式规范）

### 6. 生成报表

使用 `scripts/report_generator.py` 生成专业报表：

准备报表配置 JSON，然后执行：
```bash
python3 scripts/report_generator.py {report_config.json} -o {输出路径} --format markdown
```

配置格式：
```json
{
  "title": "2025年度财务分析报告",
  "metadata": {"period": "2025-01 至 2025-12", "author": "数据分析虾"},
  "sections": [
    {"title": "执行摘要", "content": "核心发现概要...", "insight": "关键洞察"},
    {"title": "核心KPI", "content": {"总收入": {"value": "1,234万"}, "净利润": {"value": "156万"}}},
    {"title": "收入趋势", "content": "..."}
  ]
}
```

支持输出 Markdown 和 HTML 两种格式。

## 分析原则

1. **先概览再深挖**：先了解数据全貌，再针对重点展开
2. **结论驱动**：每个分析模块结束时总结 1-3 条结论
3. **数据说话**：用具体数字支撑观点，避免空泛描述
4. **标注异常**：发现偏离预期的数据点，主动提示风险
5. **可操作性**：最终输出应包含明确的行动建议

## 注意事项

- pandas、numpy 是必需依赖，运行前确认已安装
- 大数据集（超 100MB）建议先采样分析再全量处理
- 敏感财务数据注意脱敏提示
- 预测类分析需明确告知用户置信区间和局限性
