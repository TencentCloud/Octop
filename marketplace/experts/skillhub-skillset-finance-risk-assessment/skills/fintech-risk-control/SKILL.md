---
name: fintech-risk-control
description: 数字金融科技与风控策略专家。当用户要求进行数据分析、使用Python处理金融数据、构建风控模型（决策树、分箱）、进行特征工程与分箱、分析信用风险、生成风控规则、构建评分卡等场景时使用此技能。
---

# 数字金融科技与风控策略专家

## 核心能力

- **Python数据分析**：使用pandas、numpy进行数据处理与统计分析
- **机器学习建模**：决策树、随机森林等算法构建风控模型
- **特征工程**：WOE编码、IV值计算、特征分箱与选择
- **风控策略**：生成决策规则、构建评分卡、风险分层

## 工作流程

### 1. 数据预处理

```python
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# 数据加载与清洗
def load_and_clean_data(file_path):
    df = pd.read_csv(file_path)
    df = df.fillna(df.median())
    for col in numeric_cols:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        df = df[(df[col] >= q1 - 1.5*iqr) & (df[col] <= q3 + 1.5*iqr)]
    return df
```

### 2. 特征分箱（WOE/IV）

```python
def calculate_woe_iv(df, feature, target, bins=10):
    df['bin'] = pd.qcut(df[feature], q=bins, duplicates='drop')
    grouped = df.groupby('bin')[target].agg(['sum', 'count'])
    grouped.columns = ['bad', 'total']
    grouped['good'] = grouped['total'] - grouped['bad']
    total_bad = grouped['bad'].sum()
    total_good = grouped['good'].sum()
    grouped['woe'] = np.log((grouped['bad'] / total_bad) / (grouped['good'] / total_good + 1e-10))
    grouped['iv'] = (grouped['bad']/total_bad - grouped['good']/total_good) * grouped['woe']
    return grouped, grouped['iv'].sum()
```

### 3. 决策树建模

```python
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

def build_decision_tree_model(X_train, X_test, y_train, y_test, max_depth=5):
    dt = DecisionTreeClassifier(max_depth=max_depth, min_samples_split=50,
                                min_samples_leaf=25, class_weight='balanced')
    dt.fit(X_train, y_train)
    auc = roc_auc_score(y_test, dt.predict_proba(X_test)[:, 1])
    return dt, auc
```

### 4. 风控规则生成

```python
from sklearn.tree import export_text

def generate_risk_rules(tree_model, feature_names):
    return export_text(tree_model, feature_names=feature_names)
```

## 常用指标阈值

| 指标 | 阈值建议 |
|------|---------|
| KS值 | >0.2 可接受 |
| AUC | >0.7 较好 |
| IV值 | >0.3 强特征 |
| PSI | <0.1 稳定 |

## 触发关键词

风控、信用评分、风险评估、决策树、分箱、WOE、IV、特征工程、变量筛选、评分卡、规则引擎、逾期率、坏账率、欺诈检测
