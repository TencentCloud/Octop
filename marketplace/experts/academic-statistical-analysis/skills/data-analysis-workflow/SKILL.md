---
name: data-analysis-workflow
description: Standardized data analysis workflow integrating data-analysis, statistical-analysis, scientific-visualization and other skills. Provides complete data analysis process from data import to result reporting with 6 stages.
license: MIT License
metadata:
    skill-author: academic-assistant
    version: 1.0.0
    created: 2026-03-14
---

# Data Analysis Workflow

## Overview

标准化数据分析工作流，整合多个数据分析技能，提供从数据导入到结果报告的完整流程。

## 6 Workflow Stages

### 1. 数据导入与检查 (5-10 分钟)
- 数据维度检查
- 变量类型检查
- 缺失值检测
- 异常值检测

**使用技能**: data-analysis, pandas

---

### 2. 数据清洗与预处理 (15-30 分钟)
- 缺失值处理
- 异常值处理
- 变量转换
- 数据标准化

**使用技能**: data-analysis, pandas

---

### 3. 描述统计与探索 (20-40 分钟)
- 集中趋势（均值、中位数）
- 离散程度（标准差、范围）
- 分布形态（偏度、峰度）
- 相关分析

**使用技能**: data-analysis, seaborn, exploratory-data-analysis

---

### 4. 推断统计分析 (30-60 分钟)
- 统计检验选择
- 假设条件检查
- 执行统计检验
- 效应量计算

**使用技能**: statistical-analysis, scipy

---

### 5. 可视化呈现 (20-40 分钟)
- 统计图表（seaborn）
- 定制图表（matplotlib）
- 出版级图表（scientific-visualization）

**使用技能**: seaborn, matplotlib, scientific-visualization

---

### 6. 结果报告 (15-30 分钟)
- APA 格式报告
- 结果解释
- 图表整合

**使用技能**: statistical-analysis, scientific-visualization

---

## Analysis Types

### 实验数据分析 (experimental)

**适用场景**:
- 随机对照试验
- 组间比较
- 前后测设计

**统计检验**:
- t 检验（独立/配对）
- ANOVA（单因素/多因素）
- 卡方检验

**可视化**:
- 箱线图
- 小提琴图
- 条形图（带误差线）

---

### 调查数据分析 (survey)

**适用场景**:
- 问卷调查
- 相关研究
- 预测模型

**统计检验**:
- 相关分析（Pearson/Spearman）
- 回归分析（线性/逻辑）
- 因子分析

**可视化**:
- 热力图
- 散点图
- 直方图

---

### 探索性数据分析 (exploratory)

**适用场景**:
- 初步数据探索
- 特征工程
- 假设生成

**统计检验**:
- 描述统计
- 相关分析

**可视化**:
- 配对图（pairplot）
- 分布图
- 相关矩阵

---

## Usage

### 基本使用

```bash
# 完整分析流程
python data_analysis_workflow.py --file data.csv --type experimental

# 仅描述统计
python data_analysis_workflow.py --file data.csv --stage 3

# 仅统计检验
python data_analysis_workflow.py --file data.csv --stage 4 --test anova

# 生成可视化
python data_analysis_workflow.py --file data.csv --stage 5 --plot boxplot
```

---

### 高级使用

```bash
# 指定输出格式
python data_analysis_workflow.py --file data.csv --output report.md --format APA

# 批量分析
python data_analysis_workflow.py --input-dir data/ --output-dir results/

# 出版级图表
python data_analysis_workflow.py --file data.csv --publication-quality --journal nature
```

---

## Statistical Tests

### t 检验

**适用场景**: 比较两组均值

**假设条件**:
- 正态性
- 方差齐性
- 独立性

**APA 报告**:
```
进行独立样本 t 检验，结果显示两组之间存在显著差异，
t(58) = 2.45, p = .017, d = 0.63, 95% CI [0.12, 1.14]。
```

---

### ANOVA

**适用场景**: 比较三组及以上均值

**假设条件**:
- 正态性
- 方差齐性
- 独立性

**APA 报告**:
```
进行单因素方差分析，结果显示三组之间存在显著差异，
F(2, 87) = 5.67, p = .005, η² = 0.12。
```

---

### 相关分析

**适用场景**: 评估变量间关系

**类型**:
- Pearson 相关（连续变量，正态分布）
- Spearman 相关（等级变量，非正态）

**APA 报告**:
```
Pearson 相关分析显示，变量 X 与变量 Y 呈显著正相关，
r(98) = .45, p < .001, 95% CI [.28, .59]。
```

---

## Quality Checks

### 数据质量

| 指标 | 优秀 | 良好 | 需改进 |
|------|------|------|--------|
| **缺失值** | <5% | 5-10% | >10% |
| **异常值** | <1% | 1-5% | >5% |
| **正态性** | 符合 | 近似 | 不符合 |
| **方差齐性** | 符合 | 近似 | 不符合 |

---

### 分析质量

| 指标 | 优秀 | 良好 | 需改进 |
|------|------|------|--------|
| **检验选择** | 完全适当 | 基本适当 | 不适当 |
| **假设检查** | 完整 | 部分 | 缺失 |
| **效应量** | 包含 | 部分 | 缺失 |
| **可视化** | 出版级 | 清晰 | 需改进 |
| **报告格式** | APA 规范 | 基本规范 | 不规范 |

---

## Best Practices

### 最佳实践

1. **先探索后检验**
   - 先做 EDA
   - 了解数据特征
   - 再选择统计方法

2. **检查假设条件**
   - 正态性
   - 方差齐性
   - 独立性

3. **报告效应量**
   - 不仅报告 p 值
   - 还要报告效应量
   - 提供置信区间

4. **可视化呈现**
   - 图表清晰
   - 标注完整
   - 符合出版标准

---

### 避免错误

1. **检验误用**
   - ❌ 非参数数据用参数检验
   - ✅ 先检查假设条件

2. **忽略效应量**
   - ❌ 只报告 p 值
   - ✅ 报告效应量和 CI

3. **可视化不当**
   - ❌ 3D 饼图
   - ✅ 简洁清晰的图表

4. **过度解读**
   - ❌ 相关=因果
   - ✅ 谨慎解释结果

---

## Integration

### 与文献搜索配合

```
literature-search-workflow: 负责文献搜索
data-analysis-workflow: 负责数据分析
paper-writing-workflow: 负责论文写作
```

---

### 与论文写作配合

```
data-analysis-workflow: 负责数据分析
statistical-analysis: 负责统计检验
scientific-visualization: 负责图表生成
paper-writing-workflow: 负责整合到论文
```

---

## Examples

### 示例 1: 实验数据分析

```bash
python data_analysis_workflow.py \
  --file experiment_data.csv \
  --type experimental \
  --output experiment_report.md
```

**输出**:
- 数据概览
- 描述统计表
- t 检验/ANOVA 结果
- 箱线图/小提琴图
- APA 格式报告

---

### 示例 2: 调查数据分析

```bash
python data_analysis_workflow.py \
  --file survey_data.csv \
  --type survey \
  --output survey_report.md
```

**输出**:
- 样本特征
- 相关矩阵
- 回归分析结果
- 热力图/散点图
- APA 格式报告

---

### 示例 3: 探索性数据分析

```bash
python data_analysis_workflow.py \
  --file data.csv \
  --type exploratory \
  --output eda_report.md
```

**输出**:
- 数据概览
- 缺失值分析
- 分布可视化
- 相关分析
- EDA 报告

---

## References

- APA Style: https://apastyle.apa.org/
- Effect Size: https://www.cohen.com/
- Statistical Power: https://www.gpower.com/
- Scientific Visualization: https://matplotlib.org/

---

**技能版本**: v1.0.0  
**创建时间**: 2026-03-14  
**维护者**: academic-assistant  
**下次更新**: 功能改进时

---

*高效数据分析，从标准化工作流开始！*📊🔬
