---
name: akshare-data
description: 使用 akshare-cli 获取中国及全球金融市场数据（1090+ 个函数）。覆盖股票、基金、期货、债券、外汇、宏观经济、指数、期权、新闻等全领域。当用户需要以下任何一种数据时触发此 skill：股票行情、历史K线、实时报价、涨停跌停池、龙虎榜、板块资金流向、基金/ETF净值、期货行情、债券/可转债、外汇汇率、宏观经济指标（GDP/CPI/PMI）、指数数据、期权数据、财经新闻。关键词触发：akshare、股票、行情、K线、基金、期货、外汇、宏观、国债、可转债、涨停、龙虎榜、板块、资金流向、stock data、market data、financial data、A股、港股、美股。即使用户只是随口提到"看看某个股票"或"最近市场怎么样"，也应触发。
metadata:
  octop:
    emoji: "📈"
    label:
      zh: "金融行情"
      en: "Market Data"
    summary:
      zh: "用 akshare-cli 查询股票、基金、期货、宏观与财经新闻。"
      en: "Fetch stocks, funds, futures, macro, and financial news via akshare-cli."
---

# AKShare 金融数据获取

`akshare-cli` 封装了 AKShare（1090+ 个函数），覆盖中国几乎所有金融数据及部分全球数据。

## 核心原则

1. **轻量优先** — 查单只股票用 `stock_individual_info_em`(0.1s)，不要用 `stock_zh_a_spot_em`(59s)。详见 `references/known-issues.md`。
2. **先查后调** — 不熟悉的函数先 `--full-help` 看参数，再 call。
3. **失败必降级** — 不要在第一次失败后就告诉用户"查不到"，走完三级降级。
4. **控制输出量** — 全量接口加 `--limit N --sort desc`，确保拿到最新数据而非最旧数据。

---

## 工作流程：发现 → 查看 → 调用 → 降级

严格按以下步骤顺序执行，不要跳步。

### 第一步：发现函数

三种方式，按场景选一种：

**A. 快捷命令**（常用场景直接用，不需要搜索）：
```bash
akshare-cli stock hist <代码> [--period daily|weekly|monthly] [--adjust qfq|hfq]
akshare-cli stock spot [--market all|sh|sz|bj|hk|us]
akshare-cli fund etf [代码]
akshare-cli futures hist <合约>
akshare-cli bond convertible
akshare-cli macro gdp | macro cpi
akshare-cli forex spot | forex hist [货币对]
akshare-cli index spot [--market global|cn]
```

**B. 关键词搜索**（知道大致方向时用）：
```bash
akshare-cli search <关键词>    # 支持中英文
```
英文匹配函数名（结果更全），中文匹配描述和分类路径。

| 用户意图 | 英文关键词（推荐） | 中文关键词 |
|---------|-------------------|-----------|
| 新闻 | `news` | `新闻` |
| 股票 | `stock` | `股票` |
| 涨停/跌停 | `stock_zt` | `涨停` |
| 龙虎榜 | `stock_lhb` | `龙虎榜` |
| 板块/概念 | `stock_board` | `板块` |
| 资金流向 | `fund_flow` | `资金流向` |
| 基金/ETF | `fund` | `基金` |
| 期货 | `futures` | `期货` |
| 债券 | `bond` | `债券` |
| 外汇 | `forex` | `外汇` |
| 宏观 | `macro` | `宏观` |
| 指数 | `index` | `指数` |

**C. 按分类浏览**（不确定关键词时用，按中文目录逐级查找）：
```bash
akshare-cli browse                                # 30 个顶级分类
akshare-cli browse 股票数据/A股/历史行情数据          # 逐级深入
akshare-cli browse --func stock_zh_a_hist         # 反查函数归属
```

### 第二步：查看参数（用快捷命令时可跳过）

```bash
akshare-cli call --full-help <函数名>
akshare-cli call --full-help fn1,fn2,fn3       # 批量查询
```

输出包括：说明、数据源、目标地址、参数（含可选值枚举）、用法示例。

仔细看参数：不同函数参数名不同（`symbol`/`code`/`indicator`），有些有枚举约束，日期一般是 `YYYYMMDD`。

### 第三步：调用

```bash
akshare-cli call <函数名> [--参数 值 ...] [--json] [--limit N] [--sort desc]
```

查最新数据时加 `--sort desc --limit N`，否则 `--limit` 会截取最旧的数据。

### 第四步：失败时三级降级

AKShare 底层爬取第三方网站，上游随时可能挂。失败后必须依次尝试：

**第一级：换数据源后缀**
`_em`（东方财富）失败 → 搜索 `_ths`（同花顺）或 `_sina`（新浪）同类函数：
```bash
akshare-cli search <相似关键词>
```

**第二级：browser_use 打开目标地址抓取网页数据**
`--full-help` 输出中有「目标地址」字段，这就是数据来源的网页 URL。用 browser_use 工具打开这个 URL，直接从网页上提取数据：
```bash
# 先获取目标地址
akshare-cli call --full-help stock_zh_a_hist
# 输出中会显示: 目标地址: https://quote.eastmoney.com/concept/sh603777.html
# 然后用 browser_use 打开该 URL，从页面中提取所需数据
```

**第三级：WebSearch 兜底**
用搜索引擎查数据：
```bash
# WebSearch "贵州茅台 财务数据 site:eastmoney.com"
```

触发条件：非零退出码、空数据（0 行）、网络错误。

---

## 股票代码识别

| 格式 | 含义 | 处理 |
|------|------|------|
| 6 位数字 | A 股 | 直接用 |
| 5 位数字 | 港股 | 直接用 |
| 字母开头 | 美股 | 直接用 |
| sh/sz 前缀 | 去前缀 | `sh600519` → `600519` |
| 股票名称 | 查代码 | `stock_info_sh_name_code` / `stock_info_sz_name_code` |

---

## 输出选项

| 选项 | 效果 |
|------|------|
| `--json` | JSON 格式（推荐） |
| `--csv` | CSV 格式 |
| `--output FILE` | 保存文件（.csv/.json/.xlsx/.md） |
| `--limit N` | 限制行数 |
| `--sort desc\|asc` | 排序：`desc` 最新在前（默认），`asc` 最旧在前 |
| `--no-cache` | 跳过缓存 |

**获取最新数据的关键：** 很多历史数据接口默认返回从最早开始的数据。如果你只取 `--limit 10` 而不加 `--sort desc`，拿到的是最旧的 10 条而不是最新的。查最新数据时务必加 `--sort desc`：
```bash
akshare-cli call stock_zh_a_hist --symbol 000001 --json --limit 10 --sort desc   # 最近 10 天
```

默认缓存 30 分钟（宏观 24 小时），实时行情不缓存。

---

## 注意事项

- **已知损坏接口**：调用前先查 `references/known-issues.md`，命中直接用替代方案
- **盘中 vs 盘后**：非交易时段优先用历史接口（`stock_zh_a_hist`），更快更稳定
- **日期自动填充**：未指定 `date` 参数时 CLI 自动填充当天日期
- **名称查代码**：用 `stock_info_sh_name_code` / `stock_info_sz_name_code`，禁止用全量 spot 遍历

> 更多工作流示例见 `references/examples.md`
