---
name: stock-performance-express
description: 查询 A 股上市公司业绩快报数据，支持沪深京股票。当用户询问股票业绩快报、营收、净利润、EPS、ROE、同比增长、一季报、半年报、三季报、年报等财务指标时使用。
---

# Stock Performance Express

查询 A 股单只股票所有报告期业绩快报，输出 Markdown 表格。

## 调用方式

```bash
python {baseDir}/handler.py <股票代码>
```

股票代码格式：`6位数字.SH/SZ/BJ`，例如：
- `603323.SH`（上交所）
- `000001.SZ`（深交所）
- `832566.BJ`（北交所）

## 工作流程

1. 若用户提供股票名称（如"贵州茅台"），先确认 6 位代码和市场后缀
2. 执行 `handler.py <股票代码>`
3. 将输出的 Markdown 表格展示给用户

## 注意事项

- 单次只支持一个股票代码
- `total_revenue_yoy` / `net_profit_yoy` 可能为 null（无去年同期数据）
- 可通过环境变量 `BASE_URL` / `PAGE_SIZE` 覆盖默认配置
