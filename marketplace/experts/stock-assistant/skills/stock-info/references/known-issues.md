# 已知问题接口与替代方案

调用前先检查此列表，命中则直接用替代方案，不要浪费时间尝试。

## 完全损坏（不要使用）

| 损坏接口 | 替代方案 |
|---------|---------|
| `stock_us_spot_em` | `stock_us_daily`（新浪源） |
| `stock_zh_index_spot_sina` | `index_global_spot_em` |
| `fund_etf_spot_em` | `fund_etf_hist_em` 取最新日 |
| `stock_financial_analysis_indicator_em` | `stock_financial_analysis_indicator`（新浪源） |
| `stock_profit_sheet_by_report_em` | `stock_financial_benefit_new_ths`（同花顺） |
| `stock_balance_sheet_by_report_em` | `stock_financial_debt_new_ths`（同花顺） |
| `stock_cash_flow_sheet_by_report_em` | `stock_financial_cash_new_ths`（同花顺） |
| `stock_intraday_sina` | `stock_intraday_em` |

## 极慢（非必要不用）

| 接口 | 耗时 | 轻量替代 |
|------|------|---------|
| `stock_zh_a_spot_em` | 59s | `stock_individual_info_em` (0.1s) |
| `stock_hk_spot_em` | 59s | `stock_hk_hist` (0.6s) |
| `stock_main_fund_flow("全部股票")` | 62s | `stock_individual_fund_flow_rank("今日")` (7s) |

## 轻量接口替代表

| 场景 | 禁止（慢/损坏） | 应该用（快） |
|------|----------------|-------------|
| 查单只 A 股 | `stock_zh_a_spot_em` (30-60s) | `stock_individual_info_em` (0.1s) + `stock_zh_a_hist` (0.2s) |
| 查单只港股 | `stock_hk_spot_em` (59s) | `stock_hk_hist` (0.6s) |
| 查单只美股 | `stock_us_spot_em` 损坏 | `stock_us_daily` |
| 名称→代码 | `stock_zh_a_spot_em` 遍历 | `stock_info_sh_name_code` (1s) + `stock_info_sz_name_code` (0.6s) |
| 大盘指数 | `stock_zh_index_spot_sina` 损坏 | `index_global_spot_em` (0.3s) |
| ETF 实时 | `fund_etf_spot_em` 超时 | `fund_etf_hist_em` (0.2s) 取最新日 |
