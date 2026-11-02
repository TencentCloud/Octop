# 工作流示例

## 示例 1："查一下贵州茅台最近的走势"

```bash
# 轻量接口，不要用全量 spot：
akshare-cli call stock_individual_info_em --symbol 600519 --json       # 基本信息 (0.1s)
akshare-cli stock hist 600519 --period daily --start 20260101 --json   # 近期K线 (0.2s)
```

## 示例 2："今天哪些概念板块涨得好？"

```bash
akshare-cli search stock_board_concept
akshare-cli call --full-help stock_board_concept_name_em
akshare-cli call stock_board_concept_name_em --json --limit 20
```

## 示例 3："查一下中国最新的 CPI 数据"

```bash
akshare-cli macro cpi --json
```

## 示例 4："昨天涨停的股票有哪些？"

```bash
akshare-cli search stock_zt
akshare-cli call --full-help stock_zt_pool_em
akshare-cli call stock_zt_pool_em --date 20260314 --json
```

## 示例 5：接口失败时的三级降级

```bash
# 东财财务接口损坏：
$ akshare-cli call stock_profit_sheet_by_report_em --symbol 600519 --json
Error: NoneType 错误

# 第一级：换同花顺源
akshare-cli call stock_financial_benefit_new_ths --symbol 600519 --json

# 如果同花顺也失败：
# 第二级：browser_use 打开 --full-help 中的目标地址
# 第三级：WebSearch "贵州茅台 利润表 site:eastmoney.com"
```

## 示例 6：按分类浏览找函数

```bash
akshare-cli browse                                    # 30 个顶级分类
akshare-cli browse 股票数据                             # 52 个子分类
akshare-cli browse 股票数据/A股/历史行情数据              # 8 个子分类
akshare-cli browse 股票数据/A股/历史行情数据/历史行情数据-东财  # 具体函数

# 反查函数归属
akshare-cli browse --func stock_zh_a_hist
# 输出: 分类: 股票数据 > A股 > 历史行情数据 > 历史行情数据-东财
```

## 示例 7：批量查看多个函数

```bash
akshare-cli call --full-help stock_zh_a_hist,news_cctv,macro_cnbs
```
