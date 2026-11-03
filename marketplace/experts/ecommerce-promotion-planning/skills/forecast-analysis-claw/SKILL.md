---
name: forecast-analysis-claw
description: |
  根据历史销售数据预测未来销量并生成补货建议。核心能力：(1) 销量预测 - 基于移动平均、指数平滑、Holt-Winters、Prophet 等模型自动预测未来销量；(2) 补货计算 - 结合库存参数自动计算补货触发点和建议补货量；(3) 活动预测 - 叠加促销效应系数预测大促期间销量峰值；(4) 断货预警 - 识别高风险 SKU 并推送预警。
  
  触发场景：用户提供历史销售数据（Excel/CSV），要求预测销量、计算补货量、备战大促、分析库存风险、生成补货计划等。也适用于用户提到"预测"、"补货"、"销量预测"、"需求预测"、"库存预测"、"大促备货"、"季节性"、"历史数据"、"销售曲线"、"备货计划"等关键词。
---

# forecast-analysis-claw

根据历史销售数据预测未来销量，自动计算补货建议，防止断货和积压。

## 工作流程

### 1. 数据准备

**必需字段**：
- `date` / 日期 / 销售日期
- `sku` / SKU编码 / 商品编码
- `quantity` / 销量 / 数量

**可选字段**：
- `current_stock` / 当前库存
- `in_transit` / 在途库存
- `lead_time_days` / 供应商交货周期
- `safety_days` / 安全库存天数

**数据清洗**（如需要）：
```bash
python3 scripts/data-cleaner.py clean --input raw_sales.csv --output clean_sales.csv
python3 scripts/data-cleaner.py detect-outliers --input sales.csv
```

### 2. 执行预测

**单个 SKU 预测**：
```bash
python3 scripts/forecast-runner.py single \
  --sku SKU-001 \
  --input sales.csv \
  --days 30 \
  --stock 500 \
  --lead-time 14 \
  --safety-days 7
```

**批量预测**：
```bash
python3 scripts/forecast-runner.py batch \
  --input sales.csv \
  --output forecast_result.csv \
  --days 30
```

### 3. 生成报告

```bash
python3 scripts/forecast-runner.py report --forecast forecast_result.csv
```

### 4. 评估准确率（可选）

```bash
python3 scripts/forecast-runner.py evaluate \
  --forecast last_month_forecast.csv \
  --actual last_month_actual.csv
```

## 预测模型

脚本会根据数据特征自动选择模型：

- **移动平均法**：平稳型商品，无明显趋势
- **指数平滑法**：有趋势的商品
- **Holt-Winters**：有季节性的商品
- **Prophet**（可选）：复杂季节性 + 节假日效应

详见 `references/forecast-models.md`。

## 补货参数

默认参数参考 `references/replenishment-params.md`：

| 品类 | 安全库存 | 补货周期 |
|-----|---------|---------|
| 快消品 | 7天销量 | 14天 |
| 服装鞋帽 | 14天销量 | 30天 |
| 电子产品 | 21天销量 | 45天 |

可通过命令行参数覆盖：`--lead-time 20 --safety-days 10`

## 促销活动预测

叠加促销效应系数（参考 `references/promo-coefficients.md`）：

```
活动预测销量 = 基准日均销量 × 拉升系数 × 活动天数
```

常见系数：
- 双11：5x ~ 8x
- 618：3x ~ 5x
- 日常满减：1.3x ~ 1.8x

手动计算或在脚本中添加 `--promo-factor 6.0` 参数（需自行扩展脚本）。

## 输出说明

**预测结果**：
- `daily_avg_forecast`：日均预测销量
- `total_forecast`：预测周期总销量
- `lower_bound` / `upper_bound`：置信区间
- `model_used`：使用的预测模型

**补货建议**（如提供库存参数）：
- `reorder_point`：补货触发点
- `available_stock`：当前可用库存（含在途）
- `days_of_stock`：可用天数
- `replenishment_qty`：建议补货量
- `priority`：🔴 紧急 / 🟡 正常 / 🟢 可延后

## 依赖安装

```bash
pip install pandas numpy scikit-learn
pip install prophet  # 可选，用于复杂预测
```

## 注意事项

- **最少数据量**：建议至少 30 天历史数据，90 天以上更佳
- **数据质量**：促销期间需标注，否则影响基准预测
- **预测误差**：预测结果是概率性的，需结合业务判断
- **新品预测**：无历史数据时，参考同类品系数 × 0.7

## 与其他 Skills 协作

- **process-data-monitor-claw**：监控库存水位，触发重新预测
- **historical-data-compare-claw**：提供同比环比数据，辅助识别季节性
- **cross-platform-messenger-claw**：推送断货预警到飞书/邮件
