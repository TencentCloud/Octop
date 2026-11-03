---
name: data-analyst-cn
version: 1.0.23
description: 数据分析助手 - 数据清洗、统计分析、可视化建议。适合：数据分析师、产品经理、运营。
metadata:
  openclaw:
    emoji: "📊"
    requires:
      bins: ["python3"]
---

# 数据分析助手 Skill

快速进行数据清洗、统计分析和可视化。

## 核心功能

| 功能 | 描述 |
|------|------|
| 数据清洗 | 去重、填充、格式化 |
| 统计分析 | 描述统计、相关分析 |
| 可视化 | 图表建议、代码生成 |
| 报告生成 | 自动生成分析报告 |

## 使用方法

### 分析数据

```
分析这个 CSV 文件：sales.csv
```

### 数据清洗

```
清洗这个数据集，处理缺失值和异常值
```

### 生成图表

```
为这些数据生成折线图代码
```

## Python 数据分析模板

### 读取数据

```python
import pandas as pd

# CSV
df = pd.read_csv('data.csv')

# Excel
df = pd.read_excel('data.xlsx', sheet_name='Sheet1')

# JSON
df = pd.read_json('data.json')

# 数据库
import sqlite3
conn = sqlite3.connect('database.db')
df = pd.read_sql('SELECT * FROM table', conn)

# API
import requests
response = requests.get('https://api.example.com/data')
df = pd.DataFrame(response.json())
```

### 数据预览

```python
# 基本信息
print(df.shape)        # 行列数
print(df.columns)      # 列名
print(df.dtypes)       # 数据类型
print(df.info())       # 详细信息

# 查看数据
print(df.head())       # 前 5 行
print(df.tail())       # 后 5 行
print(df.sample(5))    # 随机 5 行

# 描述统计
print(df.describe())   # 数值列统计
print(df.describe(include='all'))  # 所有列
```

### 数据清洗

```python
# 处理缺失值
df.isnull().sum()                    # 统计缺失
df.dropna()                          # 删除缺失行
df.fillna(0)                         # 填充 0
df.fillna(df.mean())                 # 填充均值
df['col'].fillna(df['col'].mode()[0])  # 填充众数

# 处理重复
df.duplicated().sum()                # 统计重复
df.drop_duplicates()                 # 删除重复
df.drop_duplicates(subset=['col'])   # 按列去重

# 数据类型转换
df['date'] = pd.to_datetime(df['date'])
df['price'] = df['price'].astype(float)
df['category'] = df['category'].astype('category')

# 异常值处理
Q1 = df['col'].quantile(0.25)
Q3 = df['col'].quantile(0.75)
IQR = Q3 - Q1
df = df[(df['col'] >= Q1 - 1.5*IQR) & (df['col'] <= Q3 + 1.5*IQR)]

# 字符串处理
df['name'] = df['name'].str.strip()
df['name'] = df['name'].str.lower()
df['name'] = df['name'].str.replace('old', 'new')
```

### 统计分析

```python
# 集中趋势
df['col'].mean()      # 均值
df['col'].median()    # 中位数
df['col'].mode()      # 众数

# 离散程度
df['col'].std()       # 标准差
df['col'].var()       # 方差
df['col'].max() - df['col'].min()  # 极差

# 分布
df['col'].skew()      # 偏度
df['col'].kurt()      # 峰度
df['col'].quantile([0.25, 0.5, 0.75])  # 分位数

# 相关分析
df.corr()             # 相关矩阵
df.corr()['target']   # 与目标的相关性

# 分组统计
df.groupby('category').agg({
    'sales': ['sum', 'mean', 'count'],
    'profit': 'mean'
})

# 交叉表
pd.crosstab(df['col1'], df['col2'])
```

### 时间序列分析

```python
# 日期处理
df['date'] = pd.to_datetime(df['date'])
df = df.set_index('date')

# 时间重采样
df.resample('D').sum()      # 按天
df.resample('W').mean()     # 按周
df.resample('M').sum()      # 按月

# 滚动统计
df['rolling_mean'] = df['col'].rolling(window=7).mean()
df['rolling_std'] = df['col'].rolling(window=7).std()

# 时间差
df['diff'] = df['col'].diff()
df['pct_change'] = df['col'].pct_change()

# 季节分解
from statsmodels.tsa.seasonal import seasonal_decompose
result = seasonal_decompose(df['col'], model='additive', period=12)
result.plot()
```

## 可视化代码

### 基础图表

```python
import matplotlib.pyplot as plt
import seaborn as sns

# 设置中文
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 折线图
plt.figure(figsize=(10, 6))
plt.plot(df['date'], df['value'])
plt.title('趋势图')
plt.xlabel('日期')
plt.ylabel('数值')
plt.show()

# 柱状图
plt.bar(df['category'], df['value'])
plt.xticks(rotation=45)
plt.show()

# 散点图
plt.scatter(df['x'], df['y'], alpha=0.5)
plt.xlabel('X')
plt.ylabel('Y')
plt.show()

# 直方图
plt.hist(df['value'], bins=20, edgecolor='black')
plt.xlabel('数值')
plt.ylabel('频数')
plt.show()

# 箱线图
sns.boxplot(data=df, x='category', y='value')
plt.show()

# 热力图
sns.heatmap(df.corr(), annot=True, cmap='coolwarm', center=0)
plt.show()
```

### 高级图表

```python
# 分组柱状图
df_grouped = df.groupby(['category', 'type'])['value'].sum().unstack()
df_grouped.plot(kind='bar', figsize=(12, 6))
plt.legend(title='类型')
plt.show()

# 小提琴图
sns.violinplot(data=df, x='category', y='value')
plt.show()

# 配对图
sns.pairplot(df[['col1', 'col2', 'col3', 'category']], hue='category')
plt.show()

# 时间序列
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(df.index, df['value'], label='实际值')
ax.plot(df.index, df['rolling_mean'], label='7日均值', linestyle='--')
ax.fill_between(df.index, df['lower'], df['upper'], alpha=0.2)
ax.legend()
plt.show()
```

## 分析报告模板

```python
def generate_report(df):
    """生成数据分析报告"""
    report = f"""
# 数据分析报告

## 1. 数据概览
- 数据量：{len(df)} 行 × {len(df.columns)} 列
- 时间范围：{df['date'].min()} 至 {df['date'].max()}
- 缺失值：{df.isnull().sum().sum()} 个

## 2. 关键指标
- 总销售额：¥{df['sales'].sum():,.2f}
- 平均订单：¥{df['sales'].mean():,.2f}
- 最高订单：¥{df['sales'].max():,.2f}
- 最低订单：¥{df['sales'].min():,.2f}

## 3. 分布特征
- 偏度：{df['sales'].skew():.2f}
- 峰度：{df['sales'].kurt():.2f}
- 标准差：{df['sales'].std():,.2f}

## 4. Top 5 类别
{df.groupby('category')['sales'].sum().sort_values(ascending=False).head().to_markdown()}

## 5. 趋势分析
- 环比增长：{df['sales'].pct_change().mean()*100:.2f}%
- 月均销售额：¥{df.resample('M', on='date')['sales'].sum().mean():,.2f}

## 6. 建议
1. 重点推广 Top 3 类别
2. 优化低转化品类
3. 关注季节性波动
"""
    return report
```

## 注意事项

- 大数据集注意内存使用
- 处理前备份数据
- 结果需要业务验证
- 可视化要简洁清晰

---

创建：2026-03-12
版本：1.0