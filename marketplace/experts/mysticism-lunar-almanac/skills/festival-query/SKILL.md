---
name: festival-query
description: >
  节日查询工具，支持中国农历日期、传统节日、二十四节气、欧美主流节日查询。当用户提到
  "今天是什么节日"、"农历几号"、"什么时候端午节"、"查一下清明节"、"感恩节是哪天"、
  "2025年有什么节日"、"这个月有哪些节日"、"二十四节气"、"冬至是几号"、"圣诞节"、
  "情人节"、"万圣节"、"复活节是哪天"、"中秋节农历几号" 等节日/节气相关问题时触发。
  支持按日期查询和按年/月范围查询两种模式。
---

# 节日查询

查询中国传统节日、二十四节气、欧美主流节日。

## 依赖安装

首次使用前确保依赖已安装（通常已预装）：

```bash
pip install --break-system-packages zhdate holidays
```

## 使用方式

脚本路径：`scripts/festival_query.py`

### 1. 查询指定日期

输入公历日期，返回农历信息、传统节日、节气、西方节日：

```bash
python3 scripts/festival_query.py --date YYYY-MM-DD
```

示例：
```bash
python3 scripts/festival_query.py --date 2025-10-06  # 中秋节
python3 scripts/festival_query.py --date 2025-01-29  # 春节
python3 scripts/festival_query.py --date 2025-12-25  # 圣诞节
```

### 2. 查询全年节日

列出指定年份所有节日和节气：

```bash
python3 scripts/festival_query.py --year YYYY
```

### 3. 查询指定月份节日

列出指定月份所有节日和节气：

```bash
python3 scripts/festival_query.py --month YYYY-MM
```

### 4. 查看全年二十四节气

仅显示节气日期表：

```bash
python3 scripts/festival_query.py --terms YYYY
```

## 涵盖范围

- **中国传统节日**（农历）：春节、元宵、龙抬头、端午、七夕、中元、中秋、重阳、腊八、小年、除夕
- **二十四节气**：小寒 → 大寒，覆盖 2020-2030 年
- **欧美/国际节日**：元旦、情人节、愚人节、劳动节、母亲节、父亲节、万圣节、感恩节、平安夜、圣诞节、复活节等
- **农历转换**：天干地支年份、生肖、农历月日
