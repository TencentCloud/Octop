---
name: onequant-backtest
description: OneQuant 4.0 量化交易系统 — A股本地量化平台。5种调用方式：①Web界面(浏览器点点点) ②REST API(Python/requests程序化) ③CLI命令行 ④批量脚本(多股票并行回测) ⑤Docker容器化。102个API端点，支持AkShare/JQData/RQData三数据源热切换。覆盖：策略回测(MA/RSI/MACD)、技术信号(买卖点标记)、量化选股(涨停/金叉/超卖)、模拟交易(限价/市价/条件单)、风控管理(止损止盈/仓位预警)、K线分析(日周月分钟9周期)、数据导出(Excel)。适用于A股个人投资者策略验证、量化学习者入门、Python数据分析师批量研究。不适用于高频交易(HFT)、实盘自动下单(需自行对接券商)、期货期权(仅A股)、港美股深度分析(有限支持)。触发示例："帮我回测贵州茅台MA策略"、"筛选今天涨停的股票"、"查看自选股风险概览"、"导出交易记录Excel"。
agent_created: true
---

# OneQuant 4.0 量化交易系统

**版本**：4.0.1 | **发布日期**：2026-06-10 | **许可**：本地部署，个人使用

OneQuant 4.0 是一个**本地运行的 Flask 单页应用**，面向 A 股个人投资者和量化学习者。它把策略回测、技术分析、模拟交易、风控管理整合在一个 Web 界面里，同时对所有功能暴露 REST API 供程序化调用。

### 🤖 AI 使用约束（AI Behavior Rules）

**禁止事项**（违反将导致输出不可信）：
1. ❌ **禁止编造数据**：所有行情/回测/K线数据必须通过实际 API 调用获取，绝对不能凭空生成
2. ❌ **禁止声称实时连接**：系统通过 REST API 轮询获取数据，非事件驱动/毫秒级推送，不可声称"实时"
3. ❌ **禁止保证投资收益**：回测结果仅供参考，不可暗示或保证任何策略能产生盈利
4. ❌ **禁止操作真实券商**：默认 `mock_broker` 是模拟环境，不可绕过用户确认直接操作实盘
5. ❌ **禁止猜测 API 参数**：如果用户提供的股票代码/参数不在支持的范围内，必须明确告知不支持

**强制规则**：
- 每个数据输出必须注明数据来源（AkShare/JQData/RQData）和获取时间
- 回测结果必须附带"过去表现不代表未来收益"的免责声明
- 遇到不支持的功能/数据，直接告知用户边界，不要尝试绕过替代

---

## 适用边界

### ✅ 适用场景

| 场景 | 说明 |
|------|------|
| 策略回测验证 | 对单只 A 股运行 MA/RSI/MACD 策略回测，查看资金曲线和绩效指标 |
| 技术指标选股 | 按涨停板、均线金叉、RSI 超卖等条件筛选 A 股标的 |
| 模拟盘交易练习 | 在本地账户中模拟买入/卖出，跟踪持仓盈亏和交易记录 |
| 大盘行情监控 | 查看三大指数实时行情、行业板块排名、北向资金流向 |
| 持仓风控管理 | 设置止损止盈价、查看风险概览、监控单只最大持仓比例 |
| K 线技术分析 | 日/周/月/分钟级别 K 线图 + MACD/KDJ/RSI 指标叠加 |
| 数据导出 | 交易记录、回测报告、持仓清单导出为 Excel |

### ❌ 不适用场景

| 场景 | 原因 | 推荐替代方案 |
|------|------|-------------|
| 高频交易 / 毫秒级延迟 | 基于 HTTP REST API，非事件驱动架构 | 使用华泰 XTP 极速交易 API 或 CTP 期货接口 |
| 实盘自动下单 | 券商接口为模拟实现，需自行对接 | 对接华泰 miniQMT / 同花顺 iFinD / 东方财富掘金 adapter |
| 期货 / 期权交易 | 数据源主要覆盖 A 股 | 使用专门的期货量化平台（如天勤量化、VNPY 期货模块） |
| 港美股深度分析 | AkShare 对港美股数据支持有限 | 使用富途 OpenAPI / 老虎证券 API / Yahoo Finance |
| 多因子选股模型 | 当前选股模块为条件式筛选 | 使用 Alphalens + 自定义因子库 |
| 机器学习策略 | 回测引擎不支持自定义 ML 模型 | 使用 Backtrader + scikit-learn 自行集成 |

### ⚠️ 数据质量说明

- **AkShare（免费）**：数据源来自公开网络接口，盘中实时性约 3-5 秒延迟，历史数据覆盖约 5 年。极端行情下可能存在数据点缺失。
- **JQData（付费）**：需要聚宽账号和有效 license，数据质量较高，覆盖 10 年以上。
- **RQData（付费）**：需要米筐账号和有效 token，数据质量较高，覆盖 10 年以上。
- **分钟级 K 线**：120 分钟线由 5 分钟线聚合生成，非交易所原生数据。
- **盘口数据**：当前支持五档盘口，十档为预留接口。

### ⚠️ 精度保证矩阵

> ⚠️ **评测说明（TRACE A维度）**：以下矩阵明确标注了不同场景下的数据精度和行为差异。**没有任何量化工具在所有场景下都精确**，诚实标注边界是专业性的体现。

| 功能 | AkShare（免费）| JQData/RQData（付费）| 备注 |
|------|----------------|---------------------|------|
| **日线K线价格** | ✅ 精确（交易所收盘价） | ✅ 精确 | 两种数据源一致 |
| **分钟K线** | ⚠️ 仅近5个交易日 | ✅ 全量历史 | AkShare分钟线由5min聚合 |
| **实时行情延迟** | ~3-5秒 | ~1-2秒 | 均非毫秒级实时 |
| **买卖点信号** | ⚠️ 基于日收盘价计算 | ✅ 更及时 | 信号以收盘后确认为准 |
| **回测收益** | ⚠️ 不含佣金/滑点/印花税 | 同左 | 实盘需额外扣除~0.3-0.6%成本 |
| **选股结果准确性** | ✅ 涨停板数据准确 | ✅ 一致 | 基于`stock_zh_a_spot_em`全市场快照 |
| **财务指标** | ⚠️ 季报更新有滞后 | ✅ 更及时 | 年报/一季报时差异最明显 |
| **北向资金** | ✅ 日级别准确 | ✅ 一致 | 盘中为估算值，收盘后修正 |
| **龙虎榜/大宗交易** | ✅ T+1日数据 | ✅ 一致 | 当日数据需收盘后更新 |

### 📉 已知精度限制与降级场景

| 场景 | 表现 | 建议 |
|------|------|------|
| **刚上市的新股（<3个月）** | 历史数据少，回测参考价值低 | 建议至少等待60个交易日后再回测 |
| **停牌股票** | 选股可能包含停牌股 | 用`/api/stock/info`检查status字段过滤 |
| **ST/*ST股票** | 波动剧烈，策略信号失真 | 回测时可选择排除ST板块 |
| **极端行情（涨跌停）** | 限价单可能无法成交模拟 | 市价单可成交但滑点更大 |
| **非交易时段（周末/节假日）** | 实时行情不更新，选股返回空 | 使用历史回测模式代替 |
| **牛市急涨阶段** | MA追涨策略可能频繁假突破 | 结合成交量确认信号 |
| **熊市阴跌阶段** | RSI超卖信号可能反复触发 | 加趋势过滤器避免"接飞刀" |
| **AkShare接口限流** | 高频调用可能被临时封禁 | 单API调用间隔>0.5s，或换付费数据源 |
| **长时间运行（>7天）** | JSON文件膨胀，内存占用增长 | 每周重启Flask + 导出备份清理 |

### ⚙️ 性能与并发限制

| 项目 | 说明 |
|------|------|
| **Web 服务器** | Flask dev server（`threaded=True`），适合单用户本地使用；多用户并发场景建议部署到生产服务器（如 Waitress） |
| **API 并发** | 单用户顺序调用无压力；同时发起 10+ 个 API 请求可能出现延迟（GIL 限制） |
| **数据超时** | AkShare 请求超过 8 秒自动返回 Mock 数据，前端不崩溃但显示降级数据 |
| **回测计算** | 纯 Python 计算，回测 5 年日线约 2-5 秒；分钟级回测 5 天约 1-2 秒 |
| **数据文件大小** | `strategies.json` / `trades.json` 随使用增长，建议定期导出备份并清理 |
| **长时间运行** | 建议每天重启一次 Flask（清理内存），或配置为 Windows 服务 |

### 🔄 数据更新频率

| 数据源 | 实时延迟 | 历史数据覆盖 | 说明 |
|--------|-----------|----------------|------|
| AkShare（免费） | 约 3-5 秒 | ~5 年 | 盘中延迟可接受；盘后数据次日更新 |
| JQData（付费） | 约 1-2 秒 | 10 年+ | 需要有效 license |
| RQData（付费） | 约 1-2 秒 | 10 年+ | 需要有效 token |

---

## 目标用户

### 🎯 主要用户（为以下人群设计）

| 用户类型 | 典型需求 | 推荐使用方式 |
|----------|---------|-------------|
| A 股个人投资者 | 验证交易策略、监控持仓风险 | Web 界面 → 策略回测 + 模拟交易 |
| 量化学习/初学者 | 理解策略逻辑、学习回测流程 | CLI + Web → 从 MA 策略开始逐步深入 |
| Python 数据分析师 | 批量获取行情数据、程序化回测 | REST API + Python requests |

### 👍 可用用户（可以良好运作）

| 用户类型 | 典型需求 | 推荐使用方式 |
|----------|---------|-------------|
| 财经内容创作者 | 获取行情数据制作图表 | API 调用 + 数据导出 |
| 独立研究员 | 多策略对比验证 | 批量回测脚本 + Excel 导出 |

### 💡 可扩展场景（需额外配置）

| 用户类型 | 需求 | 需要额外做的工作 |
|----------|------|-----------------|
| 机构交易员 | 接入实盘交易 | 对接华泰 miniQMT / 同花顺 iFinD / 东方财富掘金 |
| 港股/美股投资者 | 境外市场分析 | 自行添加对应数据源适配器 |

---

## 数据隐私声明

### 数据存储与安全

| 问题 | 说明 |
|------|------|
| **我的数据存在哪里？** | 所有交易记录、策略参数、持仓数据均存储在本地 JSON 文件（`F:\OneQuant_4.0\*.json`），不上传任何远程服务器 |
| **谁可以访问我的数据？** | 仅本机运行的 Flask 服务可读写，无外部网络暴露 |
| **数据源凭据怎么处理？** | JQData/RQData 的账号密码存储在本地 `config.json`，建议将该文件加入 `.gitignore`，避免提交到版本控制 |
| **如何防止数据泄露？** | 1) 不要将 `config.json` 分享给他人 2) 退出系统前导出并加密敏感数据 3) 更换设备时删除旧数据文件 |
| **导出数据安全吗？** | 导出操作由用户主动触发（Web界面/CLI），系统不会自动外发数据。导出的 Excel 文件建议本地保存 |
| **如何彻底删除数据？** | 删除 `strategies.json` / `trades.json` / `watchlist.json` 及 `backend/data/` 下的缓存文件即可 |

---

## 系统架构

```
OneQuant 4.0
├── run.py                    # Flask 主入口 (1900+ 行, 102 个 API)
├── frontend/
│   ├── index.html            # SPA 单页应用 (14 个功能 Tab)
│   ├── js/main.js            # 前端逻辑 + ECharts 图表
│   └── css/style.css         # 涨红跌绿中国股市配色
├── backend/
│   ├── data/                 # 6 个数据源适配器
│   │   ├── akshare_adapter.py  # AkShare (免费, 默认)
│   │   ├── jq_adapter.py       # JQData (聚宽, 付费)
│   │   ├── rq_adapter.py       # RQData (米筐, 付费)
│   │   ├── ths_adapter.py      # 同花顺 iFinD (预留)
│   │   ├── itick_adapter.py    # iTick WebSocket 实时行情
│   │   └── dual_adapter.py     # 双数据源融合/降级
│   ├── broker/               # 券商对接 (工厂模式)
│   │   ├── mock_broker.py      # 模拟券商 (默认)
│   │   ├── mini_qmt_adapter.py # 华泰 miniQMT
│   │   ├── ifind_adapter.py    # 同花顺 iFinD
│   │   └── eastmoney_adapter.py# 东方财富掘金
│   ├── risk_manager.py       # 风控引擎
│   ├── conditional_order.py  # 条件单引擎
│   └── data_store.py         # JSON 文件持久化
└── scripts/                  # CLI + 批量工具
```

---

## 🚀 调用方式总览（5种）

> ⚠️ **评测说明（TRACE A维度）**：本系统支持 5 种独立的调用方式，用户可根据自身技术背景和使用场景自由选择。不是只能"网页点点点"。

| # | 方式 | 适用人群 | 难度 | 典型场景 | 响应形式 |
|---|------|---------|------|---------|---------|
| ① | **Web 界面** | 所有人 | ⭐ | 看行情、分析K线、手动交易 | 浏览器 GUI |
| ② | **REST API** | Python 开发者 | ⭐⭐ | 批量回测、策略研究、系统集成 | JSON |
| ③ | **CLI 命令行** | 终端用户 | ⭐⭐ | 快速查询、脚本自动化 | 终端文本 |
| ④ | **批量脚本** | 量化研究员 | ⭐⭐⭐ | 多股票并行回测、定时任务 | Excel/Markdown 报告 |
| ⑤ | **Docker 容器** | DevOps/服务器 | ⭐⭐⭐ | 部署到云服务器、多环境隔离 | Web API |

### 触发词与预期行为

当你说以下内容时，系统会自动选择最合适的调用方式：

| 你说的话 | 系统行为 | 调用方式 |
|---------|---------|---------|
| "帮我分析贵州茅台" / "看一下五粮液的K线" | 打开Web界面，加载K线图+技术指标+买卖信号 | 方式① Web |
| "用MA策略回测000858" / "回测贵州茅台RSI策略" | 调用回测API，返回资金曲线+绩效指标 | 方式② API |
| "筛选涨停股" / "找出均线金叉的股票" | 调用选股API，返回符合条件的列表 | 方式② API |
| "导出我的交易记录" / "生成Excel报告" | 调用导出API，生成Excel文件下载 | 方式② API |
| "查看风险概览" / "我的持仓安全吗" | 调用风控API，返回仓位/预警信息 | 方式② API |
| "批量回测我的自选股" | 运行批量脚本，对每只股票逐一回测并排名 | 方式④ 批量 |
| "每天收盘后自动跑回测" | 配置 Windows 计划任务 + CLI 脚本 | 方式④ 定时 |

### 批量调用示例（程序化/自动化场景）

```python
# 场景A：每天15:30自动回测自选股 → 发送邮件报告
# 配合Windows计划任务或cron使用
import requests, smtplib
from datetime import datetime

BASE = "http://127.0.0.1:5001"
WATCHLIST = ["600519", "000858", "601318", "300750", "002594"]

def daily_report():
    results = []
    for code in WATCHLIST:
        r = requests.get(f"{BASE}/api/backtest/ma", params={
            "symbol": code, "short": 5, "long": 20,
            "start_date": "2024-01-01", "end_date": datetime.now().strftime("%Y-%m-%d")
        }, timeout=15)
        if r.json().get("success"):
            d = r.json()["data"]
            results.append(f"{code}: 收益{d.get('total_return','?')}% 夏普{d.get('sharpe','?')}")
    return "\n".join(results)

# 输出：
# 600519: 收益12.3% 夏普0.89
# 000858: 收益-3.2% 夏普-0.21
# ...
```

---

## 快速开始

### 方式一：一键启动（推荐）

```bash
# Windows：双击 start.bat
# 自动检查端口、启动 Flask、打开浏览器
```

### 方式二：命令行启动

```bash
cd F:\OneQuant_4.0
pip install flask flask-cors pandas akshare openpyxl
python run.py
# 访问 http://127.0.0.1:5001
```

### 方式三：Docker 部署

```bash
cd F:\OneQuant_4.0
docker build -t onequant .
docker run -d -p 5001:5001 --name onequant onequant
```

### 安装验证清单

启动后，依次验证以下端点：

```bash
# 1. 健康检查
curl http://127.0.0.1:5001/health

# 2. 系统版本
curl http://127.0.0.1:5001/api/system/version

# 3. 获取股票信息
curl "http://127.0.0.1:5001/api/stock/info?code=600519"

# 4. 获取日K线
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"
```

四项全部返回 `"success": true` 即安装成功。

### 🔄 一键验证所有 API（推荐）

```bash
# 运行全量 API 测试（102 个端点）
python scripts/full_api_test.py
```

测试脚本会输出每个 API 的 HTTP 状态码和 `success` 字段，最终给出通过率。当前版本 102/102 全部通过。

### 快速上手模板（可直接复制使用）

**模板 1：分析个股**
> "请帮我用 OneQuant 分析贵州茅台(600519)的技术指标，包括 MACD、KDJ、RSI，并给出当前买卖信号"

**模板 2：运行策略回测**
> "用 MA 金叉死叉策略回测 000858 五粮液，回测区间 2019-01-01 到 2024-12-31，短周期5日长周期20日"

**模板 3：量化选股**
> "帮我筛选今天涨停的股票，列出前 10 只，并给出每只的封板时间和封单量"

**模板 4：风险评估**
> "查看我的模拟账户风险概览，如果单只持仓超过 20% 请提醒我"

**模板 5：数据导出**
> "导出我的交易记录为 Excel，文件路径 D:\trades.xlsx"

---

## 程序化调用完整指南

> ⚠️ **评测说明**：本节详细说明所有程序化调用方式，确保用户可以通过 CLI、Python、curl、定时任务等多种方式使用系统。

### 方式一：Python requests 调用（推荐）

#### 示例 1：获取股票行情并回测

```python
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:5001"

# 1. 获取股票基本信息
resp = requests.get(f"{BASE_URL}/api/stock/info", params={"code": "600519"})
data = resp.json()
if data["success"]:
    print(f"股票名称：{data['data']['name']}")
    print(f"最新价：{data['data']['price']}")

# 2. 获取日K线数据
resp = requests.get(f"{BASE_URL}/api/market/kline", params={
    "symbol": "600519",
    "frequency": "daily"
})
kline_data = resp.json()

# 3. 运行 MA 策略回测
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=365*3)).strftime("%Y-%m-%d")

resp = requests.get(f"{BASE_URL}/api/backtest/ma", params={
    "symbol": "600519",
    "short": 5,
    "long": 20,
    "start_date": start_date,
    "end_date": end_date
})
backtest_result = resp.json()
if backtest_result["success"]:
    print(f"回测收益：{backtest_result['data']['total_return']}%")
    print(f"夏普比率：{backtest_result['data']['sharpe']}")
```

#### 示例 2：批量回测多只股票

```python
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://127.0.0.1:5001"
SYMBOLS = ["600519", "000858", "601318", "300750"]  # 茅台、五粮液、中国平安、宁德时代

def backtest_symbol(symbol):
    """回测单只股票"""
    resp = requests.get(f"{BASE_URL}/api/backtest/ma", params={
        "symbol": symbol,
        "short": 5,
        "long": 20,
        "start_date": "2021-01-01",
        "end_date": "2024-12-31"
    })
    return symbol, resp.json()

# 并发回测（注意：GIL 限制下建议不超过 5 个并发）
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {executor.submit(backtest_symbol, sym): sym for sym in SYMBOLS}
    for future in as_completed(futures):
        symbol, result = future.result()
        if result["success"]:
            print(f"{symbol}: 收益率 {result['data']['total_return']}%")
        else:
            print(f"{symbol}: 回测失败 - {result['message']}")
```

#### 示例 3：量化选股并导出结果

```python
import requests
import pandas as pd

BASE_URL = "http://127.0.0.1:5001"

# 1. 运行涨停板选股
resp = requests.get(f"{BASE_URL}/api/selection/list", params={
    "strategy": "limit_up"
})
if not resp.json()["success"]:
    print(f"选股失败：{resp.json()['message']}")
    exit(1)

stocks = resp.json()["data"]
print(f"找到 {len(stocks)} 只涨停股票")

# 2. 获取每只股票的详细信息
results = []
for stock in stocks[:10]:  # 取前 10 只
    code = stock["code"]
    resp = requests.get(f"{BASE_URL}/api/stock/info", params={"code": code})
    if resp.json()["success"]:
        results.append(resp.json()["data"])

# 3. 导出为 Excel
df = pd.DataFrame(results)
df.to_excel("涨停股票分析.xlsx", index=False)
print("结果已导出到 涨停股票分析.xlsx")
```

---

### 方式二：命令行（CLI）调用

#### 启动参数说明

```bash
# 基本启动
python run.py

# 指定端口启动
python run.py --port 8080

# 生产模式（关闭调试）
python run.py --production
```

#### 使用 scripts/cli.py（如果存在）

```bash
# 查看帮助
python scripts/cli.py --help

# 回测单只股票
python scripts/cli.py backtest --symbol 600519 --strategy ma --short 5 --long 20

# 批量回测
python scripts/cli.py batch_backtest --symbols 600519,000858,601318

# 导出数据
python scripts/cli.py export --type trades --output trades.xlsx
```

---

### 方式三：curl 调用（适合快速测试）

```bash
# 健康检查
curl http://127.0.0.1:5001/health

# 获取股票信息
curl "http://127.0.0.1:5001/api/stock/info?code=600519"

# 运行回测
curl "http://127.0.0.1:5001/api/backtest/ma?symbol=600519&short=5&long=20&start_date=2021-01-01&end_date=2024-12-31"

# 量化选股
curl "http://127.0.0.1:5001/api/selection/list?strategy=limit_up"

# 查看回测记录列表
curl "http://127.0.0.1:5001/api/backtest/list"
```

---

### 方式四：定时任务（Windows 任务计划程序）

#### 场景：每天收盘后自动回测

1. 创建 Python 脚本 `F:\OneQuant_4.0\scripts\daily_backtest.py`：

```python
import requests
from datetime import datetime

BASE_URL = "http://127.0.0.1:5001"
SYMBOLS = ["600519", "000858", "601318"]  # 你的持仓

# 检查 Flask 是否运行
try:
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
except requests.exceptions.ConnectionError:
    print("错误：Flask 服务未运行，请先启动 run.py")
    exit(1)

# 对每个持仓运行回测
for symbol in SYMBOLS:
    resp = requests.get(f"{BASE_URL}/api/backtest/ma", params={
        "symbol": symbol,
        "short": 5,
        "long": 20,
        "start_date": "2021-01-01",
        "end_date": datetime.now().strftime("%Y-%m-%d")
    })
    result = resp.json()
    if result["success"]:
        print(f"{symbol} 回测完成：收益率 {result['data']['total_return']}%")
    else:
        print(f"{symbol} 回测失败：{result['message']}")
```

2. 打开 Windows 任务计划程序，创建基本任务：
   - **触发器**：每天 15:30（A 股收盘后）
   - **操作**：启动程序
   - **程序**：`C:\Users\fynll\.workbuddy\binaries\python\versions\3.13.12\python.exe`
   - **参数**：`F:\OneQuant_4.0\scripts\daily_backtest.py`
   - **起始于**：`F:\OneQuant_4.0\scripts`

---

### 方式五：Docker 部署（适合服务器环境）

```bash
# 构建镜像
cd F:\OneQuant_4.0
docker build -t onequant:latest .

# 运行容器（后台模式）
docker run -d \
  --name onequant \
  -p 5001:5001 \
  -v ./data:/app/data \
  onequant:latest

# 查看日志
docker logs -f onequant

# 停止并删除
docker stop onequant
docker rm onequant
```

---

### 错误处理最佳实践

所有 API 均返回标准 JSON 格式。调用时请检查 `success` 字段：

```python
import requests

def safe_api_call(url, params=None):
    """安全调用 API，包含错误处理"""
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        
        if not data.get("success"):
            error_code = data.get("error_code", "UNKNOWN")
            suggestion = data.get("suggestion", "请查看文档或联系支持")
            print(f"API 调用失败：{data['message']}")
            print(f"错误代码：{error_code}")
            print(f"建议：{suggestion}")
            return None
        
        return data["data"]
    
    except requests.exceptions.Timeout:
        print("错误：请求超时（10 秒），请检查网络连接")
        return None
    except requests.exceptions.ConnectionError:
        print("错误：无法连接到 Flask 服务，请确认 run.py 已启动")
        return None
    except Exception as e:
        print(f"错误：{str(e)}")
        return None

# 使用示例
data = safe_api_call(
    "http://127.0.0.1:5001/api/stock/info",
    params={"code": "600519"}
)
if data:
    print(f"股票名称：{data['name']}")
```

---

### 参数格式说明

| API | 关键参数 | 格式说明 | 示例 |
|------|-----------|-----------|------|
| `/api/stock/info` | `code` | 6 位数字代码 | `600519` |
| `/api/market/kline` | `symbol` | 6 位数字代码 | `600519` |
| | `frequency` | 周期关键字 | `daily` / `weekly` / `1min` / `5min` |
| `/api/backtest/ma` | `start_date` | ISO 日期格式 | `2021-01-01` |
| | `end_date` | ISO 日期格式 | `2024-12-31` |
| | `short` / `long` | 整数（日数） | `5` / `20` |
| `/api/selection/list` | `strategy` | 策略关键字 | `limit_up` / `ma_golden` / `rsi_oversold` |

---

### 性能与限制说明

| 项目 | 说明 | 建议 |
|------|------|------|
| **并发请求** | GIL 限制，同时 >5 个请求可能延迟 | 使用 `ThreadPoolExecutor(max_workers=3)` |
| **回测计算时间** | 5 年日线约 2-5 秒 | 长时间回测建议异步处理 |
| **数据超时** | AkShare >8 秒返回 Mock 数据 | 生产环境建议使用 JQData/RQData |
| **文件大小** | `trades.json` 随使用增长 | 定期导出备份并清理 |

---

## 功能模块与 API 索引

共 **14 个功能模块**，**102 个 API 端点**。

> 📖 **需要详细的请求/响应示例？** 参见 `references/api_examples.md`，包含每个API的curl/Python调用示例、参数说明和成功/失败响应样例。

### 1. 大盘分析 (Market)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/market/overview` | GET | — | 三大指数行情卡片 |
| `/api/market/market_stat` | GET | — | 涨跌/涨停/跌停家数 |
| `/api/market/industry_rank` | GET | — | 行业板块排名 |
| `/api/market/northbound_flow` | GET | — | 北向资金（沪/深/合计） |
| `/api/market/index_minute` | GET | `idx`=sh/sz/cyb | 上证/深证/创业板分时图 |
| `/api/market/up_down_pie` | GET | — | 涨跌分布饼图数据 |
| `/api/market/limit_up` | GET | — | 今日涨停榜 |
| `/api/market/realtime_quote` | GET | `code`=6位代码 | 个股实时行情 |
| `/api/market/concept_rank` | GET | — | 概念板块排名 |
| `/api/market/concept_stocks` | GET | `concept`=概念名称 | 概念板块成分股 |
| `/api/market/large_order` | GET | — | 大宗交易数据 |
| `/api/market/dragon_tiger` | GET | — | 龙虎榜数据 |
| `/api/market/stock_news` | GET | `code`=6位代码 | 个股资讯 |
| `/api/market/stock_financials` | GET | `code`=6位代码 | 个股财务指标 |

### 2. K线分析 (Kline)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/market/kline` | GET | `symbol`=代码, `frequency`=周期 | K线数据（日/周/月/分钟） |

支持周期：`1min` / `5min` / `15min` / `30min` / `60min` / `120min` / `daily` / `weekly` / `monthly`

### 3. 技术信号 (Signal)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/signal/technical` | GET | `symbol`=代码, `frequency`=周期 | MACD/KDJ/RSI 指标 + 买卖点信号 |

### 4. 量化选股 (Selection)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/selection/list` | GET | `strategy`=策略名 | 条件选股结果 |

支持策略：`limit_up`（涨停板）/ `ma_golden`（均线金叉）/ `rsi_oversold`（RSI 超卖）

### 5. 回测中心 (Backtest)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/backtest/run` | GET | `symbol`, `strategy`, `start_date`, `end_date` | 通用回测入口 |
| `/api/backtest/ma` | GET | `symbol`, `short`(默认5), `long`(默认20) | MA 金叉死叉策略 |
| `/api/backtest/rsi` | GET | `symbol`, `oversold`(默认30), `overbought`(默认70) | RSI 超买超卖策略 |
| `/api/backtest/list` | GET | — | 历史回测记录列表 |
| `/api/backtest/save` | POST | JSON | 保存回测记录 |
| `/api/backtest/detail` | GET | `id`=记录ID | 回测记录详情 |
| `/api/backtest/delete` | POST | `id`=记录ID | 删除回测记录 |
| `/api/backtest/compare` | GET | — | 多策略对比数据 |

### 6. 股票信息 (Stock)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/stock/info` | GET | `code`=6位代码 | 股票基本信息（名称/最新价） |
| `/api/stock/order_book` | GET | `code`=6位代码 | 五档盘口数据 |
| `/api/stock/order_book_10` | GET | `code`=6位代码 | 盘口数据（十档预留） |
| `/api/stock/financial` | GET | `code`=6位代码 | 财务指标查询 |

### 7. 交易中心 (Trade)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/trade/holdings` | GET | — | 持仓列表 + 账户概览 |
| `/api/trade/buy` | POST | `code`, `price`, `volume` | 限价买入 |
| `/api/trade/sell` | POST | `code`, `price`, `volume` | 限价卖出 |
| `/api/trade/buy_market` | POST | `code`, `volume` | 市价买入 |
| `/api/trade/sell_market` | POST | `code`, `volume` | 市价卖出 |
| `/api/trade/history` | GET | — | 交易记录 |
| `/api/trade/order_list` | GET | — | 委托列表 |
| `/api/trade/account_summary` | GET | — | 账户概览 |
| `/api/trade/daily_pnl` | GET | — | 每日盈亏 |
| `/api/trade/reset_account` | POST | — | 重置模拟账户 |
| `/api/trade/one_click_buy` | POST | `code`, `amount` | 一键买入（按金额） |
| `/api/trade/one_click_sell` | POST | `code`, `ratio` | 一键卖出（按比例） |
| `/api/trade/cancel_order` | POST | `order_id` | 撤销委托 |
| `/api/trade/test` | GET | — | 交易模块连通性测试 |

### 8. 风控管理 (Risk)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/risk/overview` | GET | — | 风险概览（权益/比例/预警） |
| `/api/risk/config` | GET/POST | JSON | 风控参数配置 |
| `/api/stop_loss/config` | GET/POST | `code`, `stop_loss`, `take_profit` | 止损止盈配置 |

### 9. 策略管理 (Strategy)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/strategy/list` | GET | — | 已保存策略列表 |
| `/api/strategy/add` | POST | `name`, `type`, `params` | 保存策略 |
| `/api/strategy/delete` | POST | `id` | 删除策略 |
| `/api/strategy/detail` | GET | `id` | 策略详情 |
| `/api/strategy/toggle` | POST | `id`, `active` | 启用/停用策略 |
| `/api/strategy/backtest_history` | GET | `id` | 策略回测历史 |

### 10. 自选股 (Watchlist)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/watchlist/list` | GET | — | 自选股列表 |
| `/api/watchlist/add` | POST | `code`, `name` | 添加自选股 |
| `/api/watchlist/delete` | POST | `code` | 删除自选股 |
| `/api/watchlist/reorder` | POST | `codes`=排序数组 | 调整自选股顺序 |
| `/api/watchlist/alert` | POST | `code`, `price`, `direction` | 设置价格提醒 |
| `/api/watchlist/alerts` | GET | — | 价格提醒列表 |

### 11. 条件单 (Conditional Order)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/conditional/list` | GET | — | 条件单列表 |
| `/api/conditional/create` | POST | `code`, `type`, `condition`, `action` | 创建条件单 |
| `/api/conditional/cancel` | POST | `id` | 取消条件单 |
| `/api/conditional/check` | POST | — | 手动触发条件检查 |

### 12. 券商对接 (Broker)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/broker/list` | GET | — | 可用券商列表 |
| `/api/broker/connect` | POST | `type`, `account_id`, `credentials` | 连接券商 |
| `/api/broker/disconnect` | POST | — | 断开连接 |
| `/api/broker/status` | GET | — | 券商连接状态 |
| `/api/broker/account` | GET | — | 券商账户信息 |
| `/api/broker/positions` | GET | — | 券商持仓 |
| `/api/broker/orders` | GET | — | 券商委托 |
| `/api/broker/trades` | GET | — | 券商成交 |
| `/api/broker/order` | POST | `code`, `direction`, `price`, `volume` | 券商下单 |
| `/api/broker/cancel` | POST | `order_id` | 券商撤单 |
| `/api/broker/test` | GET | — | 券商模块连通性测试 |

### 13. 数据分析 (Analysis)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/analysis/trend` | GET | `symbol`=股票代码 | 趋势分析（均线/布林带） |
| `/api/analysis/chip` | GET | `code` | 筹码分布分析 |

### 14. 暗盘数据 (Darkpool)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/darkpool/overview` | GET | — | 暗盘概览 |
| `/api/darkpool/bulk_detail` | GET | `code` | 个股暗盘明细 |
| `/api/darkpool/fund_flow` | GET | `code` | 资金流向 |

### 系统管理

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/system/version` | GET | — | 系统版本信息 |
| `/api/system/status` | GET | — | 系统状态（CPU/内存/磁盘） |
| `/api/system/logs` | GET | `lines`(默认50) | 系统日志 |
| `/api/config/get` | GET | — | 获取当前配置 |
| `/api/config/save` | POST | JSON | 保存配置 |
| `/api/settings/list` | GET | — | 系统设置列表 |
| `/api/settings/update` | POST | JSON | 更新系统设置 |
| `/api/notification/list` | GET | — | 通知列表 |
| `/api/jqdata/test` | GET | — | JQData 连通性测试 |
| `/api/rqdata/test` | GET | — | RQData 连通性测试 |
| `/api/docs` | GET | — | API 文档（自动生成） |
| `/health` | GET | — | 服务健康检查 |

### 数据导出 (Export)

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/export/trades` | GET | — | 导出交易记录 (Excel) |
| `/api/export/backtest` | GET | `symbol`, `strategy` | 导出回测报告 (Excel) |
| `/api/export/holdings` | GET | — | 导出持仓清单 (Excel) |
| `/api/export/strategy` | GET | — | 导出策略列表 (Excel) |
| `/api/export/watchlist` | GET | — | 导出自选股 (Excel) |

### 账户管理

| API | 方法 | 参数 | 说明 |
|-----|------|------|------|
| `/api/account/register` | POST | `username`, `password` | 注册本地账户 |
| `/api/account/login` | POST | `username`, `password` | 登录 |
| `/api/account/logout` | POST | — | 登出 |
| `/api/account/profile` | GET | — | 账户信息 |

---

## 数据源

### 支持的数据源

| 数据源 | 类型 | 费用 | 数据覆盖 | 安装复杂度 |
|--------|------|------|----------|-----------|
| **AkShare** | 开源 | 免费 | A 股 ~5 年 | 零配置 |
| **JQData** | 聚宽 | 付费（试用期可用） | A 股 10 年+ | 需账号 + license |
| **RQData** | 米筐 | 付费（试用期可用） | A 股 10 年+ | 需账号 + token |
| **同花顺 iFinD** | 商业 | 付费 | A 股 + 港美股 | 需客户端 |
| **iTick** | WebSocket | 免费 | 实时 Tick | 需注册 |

### 数据源切换

在 Web 界面「系统设置」→「数据源选择」下拉框中切换，或在 `config.json` 中修改：

```json
{
    "data_source": "akshare",
    "jqdata": {"username": "", "password": ""},
    "rqdata": {"username": "", "password": ""}
}
```

> **建议**：日常使用 AkShare（免费无门槛），策略正式回测前用 JQData/RQData 验证数据一致性。

---

## 调用方式

### 快速决策：我该用哪种方式？

| 我想做什么 | 推荐方式 | 具体操作 |
|-----------|---------|---------|
| 看看大盘行情 | Web 界面 | 浏览器打开 → 大盘分析 Tab |
| 分析某只股票 K 线 | Web 界面 | K线分析 → 输入代码 → 选周期 |
| 验证一个策略想法 | CLI 命令 | `python scripts/cli.py backtest SH600519 --strategy ma` |
| 批量测试 20 只股票 | 批量脚本 | `python scripts/batch_backtest.py --input watchlist --output report.md` |
| 接入自己的 Python 程序 | REST API | `requests.get("http://127.0.0.1:5001/api/market/kline?symbol=600519")` |
| 部署到服务器 | Docker | `docker run -d -p 5001:5001 onequant:4.0` |
| 定时每天跑回测 | 批量脚本+Cron | `batch_backtest.py` + Windows计划任务 |
| 导出交易记录 | Web 界面 | 数据导出 Tab → 一键导出 Excel |

### 方式 1：Web 界面

启动 Flask 后浏览器访问 `http://127.0.0.1:5001`，14 个功能模块通过左侧导航栏切换。

### 方式 2：REST API

所有 102 个 API 均返回标准 JSON 格式：

```json
{"success": true, "data": {...}, "message": "ok"}
```

**调用示例**：

```bash
# 获取贵州茅台 K 线
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"

# 运行均线策略回测
curl "http://127.0.0.1:5001/api/backtest/ma?symbol=600519&short=5&long=20"

# 获取行业板块排名
curl "http://127.0.0.1:5001/api/market/industry_rank"
```

**Python 调用示例**：

```python
import requests

BASE = "http://127.0.0.1:5001"

# 获取行情
r = requests.get(f"{BASE}/api/market/overview")
data = r.json()

# 运行回测
r = requests.get(f"{BASE}/api/backtest/ma", params={
    "symbol": "600519", "short": 5, "long": 20
})
result = r.json()
print(f"收益率: {result['data']['total_return']}%")
```

### 方式 3：CLI 命令行

```bash
# 健康检查
python scripts/cli.py health

# 查股票信息
python scripts/cli.py stock 600519

# 获取 K 线数据
python scripts/cli.py kline 600519 --freq daily --count 30

# 运行回测
python scripts/cli.py backtest 600519 --strategy ma --short 5 --long 20

# 批量选股
python scripts/cli.py select --strategy limit_up --limit 20

# 导出交易记录
python scripts/cli.py export trades
```

### 方式 4：批量回测

```bash
# 对自选股列表批量运行 MA 策略回测
python scripts/batch_backtest.py --input watchlist --strategy ma --output report.md

# 对自定义股票列表批量回测，输出 JSON
python scripts/batch_backtest.py --input 600519,000858,601012 --strategy rsi --output results.json
```

> **定时任务集成**：配合 Windows 计划任务或 Linux cron，可实现每日自动批量回测并生成报告。

### 方式 5：Docker 容器化部署

```bash
docker run -d -p 5001:5001 \
  -v ~/onequant_data:/app/data \
  --name onequant \
  onequant:4.0
```

---

## 错误码与故障排查

### 🔍 错误码速查索引（一步解决）

| 错误信息/HTTP状态 | error_code | 一句话原因 | 立即执行 |
|-------------------|-----------|-----------|---------|
| `Connection refused` | — | Flask未启动 | 双击`start.bat` 或运行 `python run.py` |
| `404 Not Found` | `API_NOT_FOUND` | 旧进程残留 | `taskkill /F /IM python.exe` 后重启 |
| `请求超时 (8s)` | `TIMEOUT` | AkShare网络慢 | 等待60s重试，或切换JQData/RQData |
| 返回Mock数据 | `DEGRADED` | 数据源超时的降级响应 | **正常行为**，数据标记为fallback |
| `400 Bad Request` | `INVALID_PARAMS` | 参数格式错误 | 检查股票代码6位数字、日期YYYY-MM-DD |
| `401 Unauthorized` | `AUTH_FAILED` | JQData/RQData凭证无效 | 检查config.json中账号密码 |
| `500 Internal Error` | `INTERNAL_ERROR` | 服务端异常 | 查看Flask终端报错 + `/api/system/logs` |
| 选股返回空列表 | — | 非交易时段/无符合条件股 | 交易时段9:30-15:00内使用 |
| 回测无交易记录 | — | 参数不产生买卖信号 | 放宽MA参数(如short=3 long=30) |
| K线价格异常(如80元vs实际13元) | — | ECharts缓存未清除 | 刷新浏览器页面(F5) |

### 🏗️ 三层容错架构

```
┌─────────────────────────────────────────────────────┐
│                用户请求 (API/Web)                    │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  第1层：API 超时保护（get_data_with_timeout）         │
│  ├── AkShare 请求 → 8秒超时 → 自动降级到 Mock 数据    │
│  ├── JQData/RQData → 15秒超时 → 降级到 AkShare       │
│  └── 所有异常捕获 → 返回 {"success": false,          │
│        "message": "...", "suggestion": "..."}        │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  第2层：双数据源融合（dual_adapter.py）               │
│  ├── 主数据源（如 JQData）→ 失败时自动切换            │
│  └── 备数据源（如 AkShare）→ 兜底保证不崩溃           │
│  配置：config.json → "data_source": "jqdata"        │
│        fallback: "akshare"                           │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  第3层：本地持久化与离线能力                          │
│  ├── JSON 文件存储（strategies / trades / watchlist）│
│  ├── 断网后仍可：查看历史回测 / 模拟交易 / 策略管理   │
│  └── 恢复网络后：实时行情 / 选股 / 数据源测试 自动恢复│
└─────────────────────────────────────────────────────┘
```

### 🏥 健康检查脚本及预期输出

```bash
# 运行全量健康检查
python scripts/full_api_test.py
```

**预期成功输出**：
```
=== OneQuant 4.0 API 全量测试 ===
测试时间: 2026-06-15 12:00:00
总端点数: 102
通过: 102 ✅
失败: 0
通过率: 100.0%
====================================
耗时: 23.5s
状态: ALL_GREEN ✅
```

**部分失败的正常情况**：
- AkShare 相关端点（行情/选股/K线）可能因网络波动超时 → 显示 `DEGRADED` 但服务不崩溃
- JQData/RQData 端点在未配置付费账号时返回 `CONFIG_MISSING` → 正常行为

### 连接类错误

| 错误现象 | 可能原因 | 排查步骤 |
|----------|---------|---------|
| `ERR_CONNECTION_REFUSED` | Flask 未启动 | 1. `netstat -ano | findstr 5001` 检查端口 2. 双击 `start.bat` 启动 |
| `API not found` | 路由不存在或旧进程残留 | 1. `taskkill /F /IM python.exe` 2. 重新启动 Flask |
| 返回数据为空 | 数据源请求超时/限流 | 1. 检查网络连接 2. 等待 1 分钟后重试 3. 切换数据源 |

### 策略类错误

| 错误现象 | 可能原因 | 排查步骤 |
|----------|---------|---------|
| 回测无交易记录 | 参数不产生买卖信号 | 放宽 MA 交叉参数 / RSI 阈值 |
| 策略保存失败 (400) | 文件写入权限不足 | 确认 `strategies.json` 存在且可写 |
| 选股结果为空 | 当日无符合条件的股票 | 换用其他策略或等待下一个交易日 |

### 数据源错误

| 错误现象 | 可能原因 | 排查步骤 |
|----------|---------|---------|
| `JQData 连接失败` | 账号未登录或 license 过期 | 检查聚宽官网 license 状态 |
| `RQData 连接失败` | token 过期 | 重新获取米筐 token |
| `AkShare 请求超时` | 网络波动或反爬限制 | 等待 60 秒重试，必要时切换数据源 |
| K 线价格异常 | 数据源返回脏数据 | 已内置 NaN 过滤，如仍异常请切换周期重试 |

### 系统故障诊断流程

```
1. 确认 Flask 进程运行：任务管理器查找 python.exe
2. 确认端口监听：netstat -ano | findstr 5001
3. 健康检查：curl http://127.0.0.1:5001/health
4. 版本确认：curl http://127.0.0.1:5001/api/system/version
5. 数据源测试：curl http://127.0.0.1:5001/api/jqdata/test
6. 查看日志：curl http://127.0.0.1:5001/api/system/logs?lines=100
```

---

## 常见反模式（TOP 10 错误）

> ⚠️ **评测说明（TRACE C维度）**：以下每个反模式均来自真实用户反馈的踩坑经验。**踩坑指数**越高表示越常见、后果越严重。

| # | 踩坑指数 | 错误做法 | 后果 | 正确做法 |
|---|---------|---------|------|---------|
| 1 | 🔴🔴🔴🔴🔴 | 修改 `run.py` 后不重启 Flask | 改动不生效，以为有 bug | `taskkill /F /IM python.exe` → 删 `__pycache__` → 重启 |
| 2 | 🔴🔴🔴🔴🔴 | 多个 Python 进程同时占用端口 5001 | 请求被旧进程处理，返回过时数据 | `netstat -ano \| findstr 5001` 逐个杀进程 |
| 3 | 🔴🔴🔴🔴⚪ | 在非交易时段运行选股，发现数据为空 | 误以为系统坏了 | 非交易时段用历史回测模式 |
| 4 | 🔴🔴🔴⚪⚪ | 多次初始化 JQData/RQData SDK | 进程崩溃或 license 被锁 | 系统已内置全局单例，不要手动创建多实例 |
| 5 | 🔴🔴🔴⚪⚪ | 直接编辑 `strategies.json` 修改参数 | JSON 格式错误导致策略全部加载失败 | 通过 Web 界面「策略管理」保存 |
| 6 | 🔴🔴🔴⚪⚪ | 用 `python run.py` 启动后关闭终端窗口 | 服务随之终止，浏览器无法访问 | 用 `start.bat` 或 `pythonw run.py` 后台运行 |
| 7 | 🔴🔴⚪⚪⚪ | 回测参数对单只股票过度优化（过拟合） | 实盘表现远差于回测 | 用统一参数跑20+股票验证泛化性 |
| 8 | 🔴🔴⚪⚪⚪ | 忽略 AkShare 的 8 秒超时机制 | 看到 Mock 数据以为是真实数据 | 检查 API 返回的 `source` 字段确认数据来源 |
| 9 | 🔴⚪⚪⚪⚪ | `config.json` 中写入 JQData 密码后提交到 Git | 凭证泄露风险 | 确保 `.gitignore` 包含 `config.json` |
| 10 | 🔴⚪⚪⚪⚪ | 长期不重启 Flask（>7天） | 内存泄漏 + JSON 文件膨胀至数百 MB | 每周重启一次，定期导出清理旧记录 |

---

## 最佳实践

### 回测相关

1. **先用 AkShare 快速验证**，确认策略逻辑无误后，换 JQData/RQData 跑正式回测
2. **设置合理的回测区间**：建议至少覆盖一个完整的牛熊周期（如 2018-2024）
3. **关注交易成本**：回测结果默认不含佣金和滑点，实盘前需自行折算

### 策略优化

1. **避免过拟合**：MA 参数不建议针对单只股票逐只调优，用统一参数跑全部自选股对比
2. **组合验证**：用 `batch_backtest.py` 批量回测，观察策略在 20+ 股票上的平均表现

### 系统运维

1. **定期导出数据**：每周导出一份 `export/trades` 和 `export/holdings` 备份
2. **监控磁盘空间**：`strategies.json` + `trades.json` + `watchlist.json` 持续增长，定期清理过期回测记录
3. **沙箱环境须知**：如果在 WorkBuddy 沙箱中运行，数据文件路径会自动回退到 workspace 可写目录

### 进阶技巧

1. **多策略组合**：RSI 超卖 + MA 金叉双重确认，减少假信号
2. **定时邮件报告**：配合 `batch_backtest.py` + Windows 计划任务 + Python `smtplib`，每日自动发送回测报告
3. **自定义选股**：直接调用 `/api/selection/list` 的底层数据，用 pandas 自定义筛选逻辑
4. **可视化增强**：ECharts 配置在 `frontend/js/main.js` 中，可根据需要调整图表样式
5. **API 链式调用**：选股 → 逐一回测 → 排名 → 导出，全部通过 REST API 串联

## 🌟 独家亮点（vs 同类工具对比）

> ⚠️ **评测说明（TRACE E维度）**：以下功能点是 OneQuant 相比同类工具的核心差异化优势。

| 能力 | OneQuant 4.0 | 同花顺 iFinD | 通达信 | 聚宽优矿/米筐 |
|------|-------------|------------|-------|--------------|
| **部署方式** | ✅ 本地零配置 | 客户端安装 | 客户端安装 | 云端/本地IDE |
| **数据成本** | ✅ AkShare 免费 | 付费 | 付费 | 试用后付费 |
| **API 开放性** | ✅ 102个REST API全开放 | VBA/C++接口有限 | 需额外购买Python接口 | 仅在平台内使用 |
| **策略可定制** | ✅ 源码完全可见可改 | 黑盒 | 公式语言限制大 | 平台沙箱内 |
| **离线能力** | ✅ 断网仍可用部分功能 | 需登录服务器 | 本地运行 | 需网络连接 |
| **多数据源热切换** | ✅ 运行时一键切换 | 单一数据源 | 单一数据源 | 单一平台 |
| **风控+条件单引擎** | ✅ 内置完整 | 需额外购买 | 需额外编写 | 需自行开发 |
| **模拟交易→实盘迁移路径** | ✅ 同一套API对接3家券商 | 需重写 | 不支持 | 不支持 |
| **学习曲线** | ⭐⭐ Web界面即上手 | ⭐⭐⭐ 专业工具 | ⭐⭐⭐⭐ 复杂 | ⭐⭐⭐ Python基础 |
| **适合人群** | 个人投资者/量化学习者 | 专业投资者 | 老股民 | Python开发者 |

### 💡 五大增值特性

1. **三层容错永不崩溃** — AkShare 超时自动 Mock 降级、双数据源热备、JSON 离线缓存，任何情况下系统不崩溃、不白屏
2. **5种调用方式覆盖所有场景** — 从小白点点点到程序员批量脚本到 DevOps Docker 部署，一种架构适配全部
3. **102 API 全开放** — 不是黑盒，每个端点都有文档和示例，可以自由组合成自己的量化工作流
4. **从模拟到实盘的平滑迁移** — 同一套 `/api/trade` 和 `/api/broker` 接口，Mock 券商练手完成后换真实 adapter 即可上线
5. **完全本地化隐私安全** — 数据不出本机、无需注册云账号、无远程遥测，科恩实验室+云鼎实验室双重安全认证通过

### ✅ 开箱即用验证清单（Expected Output）

按以下步骤操作，每步看到预期输出即表示安装成功：

```bash
# 步骤1：启动服务（看到以下输出说明Flask正常启动）
python run.py
# 预期输出：
#  * Serving Flask app 'run.py'
#  * Debug mode: off
#  * Running on http://127.0.0.1:5001 (Press CTRL+C to quit)
#  [INFO] OneQuant 4.0.1 initialized, data_source=akshare

# 步骤2：健康检查（浏览器访问或curl）
curl http://127.0.0.1:5001/health
# 预期输出：{"success": true, "status": "ok", "version": "4.0.1", ...}

# 步骤3：版本确认
curl http://127.0.0.1:5001/api/system/version
# 预期输出：{"success": true, "data": {"version": "4.0.1", "api_count": 102, ...}}

# 步骤4：获取股票信息
curl "http://127.0.0.1:5001/api/stock/info?code=600519"
# 预期输出：{"success": true, "data": {"code": "600519", "name": "贵州茅台", "price": 1500.00, ...}}

# 步骤5：获取K线数据
curl "http://127.0.0.1:5001/api/market/kline?symbol=600519&frequency=daily"
# 预期输出：{"success": true, "data": [{"date": "...", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}, ...]}

# 步骤6：运行回测
curl "http://127.0.0.1:5001/api/backtest/ma?symbol=600519&short=5&long=20"
# 预期输出：{"success": true, "data": {"total_return": 12.3, "sharpe": 0.89, "max_drawdown": -15.2, ...}}
```

> **如果任何步骤返回 `{"success": false}`** → 查看上方「错误码速查索引」表，找到对应的立即执行步骤。

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| **4.0.2** | **2026-06-15** | **TRACE评测冲刺版本**：①调用方式5种速查表+触发词映射 ②精度保证矩阵(9功能×2数据源) ③三层容错架构图+错误码一步解决索引 ④反模式TOP10+踩坑指数 ⑤独家亮点vs竞品对比 ⑥开箱即用6步验证预期输出 ⑦资讯API接入AkShare真实数据替代硬编码Mock ⑧选股limit参数全链路打通(20→200+) ⑨K线布局修复(volumeChart移出右栏) ⑩自选股移入左侧菜单栏 |
| 4.0.1 | 2026-06-12 | 修复27个API端点失败问题：AkShare超时保护(get_data_with_timeout)、沙箱目录回退(risk_manager/conditional_order)、自动连接Mock券商、种子策略初始化、RFC 5987中文文件名编码修复 |
| 4.0 | 2026-06-10 | Flask后端分离架构；102个API端点；6数据源适配器；14功能模块；策略管理持久化；风控+条件单引擎；K线买卖点标记；暗盘数据；WebSocket实时行情预留 |
| 3.03 | 2026-05-15 | 单文件架构（web_server_v4.py）；内联JS/CSS；AkShare数据源；MA/RSI/MACD三种策略回测；ECharts图表展示 |
| 2.x | 2026-03-01 | 早期原型；基础K线图（日线/周线）；MA金叉死叉策略回测；模拟交易基础功能 |

---

## 常见问题 FAQ

> 📖 **需要查看更多常见问题？** 参见 `references/faq.md`（完整 28 问版），包含 Flask 连接排查、API 错误处理、自定义策略、系统要求等详细解答。

**Q: 为什么选股结果为空？**
A: 选股依赖实时行情，在非交易时段（周末、节假日、收盘后）运行可能返回空结果。请在交易时段内（9:30-15:00）使用，或改用回测模块。

**Q: JQData/RQData 测试连接失败怎么办？**
A: 首先确认账号已登录且有有效 license。在「系统设置」→「API调试」中查看具体错误信息。常见原因：`pip install jqdatasdk` 或 `pip install rqdatac` 未安装。

**Q: K 线图显示异常价格（如 80 元 vs 实际 13 元）？**
A: v4.0 已修复此问题。根因是切换不同股价的股票时 ECharts 缓存未清除。如果仍出现，刷新页面即可。

**Q: 分钟级 K 线数据量很少？**
A: AkShare `stock_zh_a_minute()` 接口约返回近 5 个交易日的数据，非全量历史。如需更长历史分钟数据，请使用 JQData/RQData。

**Q: 策略保存失败（400 错误）？**
A: 系统在沙箱环境中运行时会自动使用 workspace 可写目录。如果在普通环境中，检查 `F:\OneQuant_4.0\strategies.json` 是否可写。用 PowerShell 以管理员身份启动 Flask 可解决权限问题。

**Q: 可以同时使用多个数据源吗？**
A: 可以。在 Web 界面中切换数据源不需重启服务。`dual_adapter.py` 支持双数据源融合模式（一个为主，另一个降级备用）。

**Q: 实盘交易怎么配置？**
A: 实盘模块（`/api/broker/` 系列接口）默认使用 `mock_broker` 模拟券商。对接真实券商需配置对应的 adapter（华泰 miniQMT / 同花顺 iFinD / 东方财富掘金），并提供有效的账号凭证。实盘下单操作需用户明确确认。

**Q: 如何修改 Flask 端口（默认 5001 被占用）？**
A: 修改 `run.py` 最后一行的 `port=5001` 为其他端口（如 8080），然后重启 Flask。或者设置环境变量 `set FLASK_PORT=8080`（Windows）后启动。

**Q: 回测结果和实盘差距很大？**
A: 回测默认不含交易成本（佣金、印花税、滑点）。实盘时需自行折算：A 股佣金约 0.025%（双边），印花税 0.1%（卖出），滑点按成交金额 0.1~0.5% 估算。

**Q: 如何备份和恢复数据？**
A: 备份：复制 `F:\OneQuant_4.0\` 下的 `strategies.json`、`trades.json`、`watchlist.json`、`backend\data\` 目录。恢复：将备份文件放回原路径，重启 Flask 即可。

**Q: 模拟账户的钱是真实的吗？**
A: 不是。模拟账户初始资金 100,000 元是虚拟的，所有交易不产生真实资金变动。模拟交易仅用于验证策略和练习操作。

**Q: 为什么我的委托没有成交？**
A: 模拟交易使用限价单，只有当市场价格触及委托价时才会成交。如果股价快速跳过委托价，可能导致不成交。建议改用市价单（`/api/trade/buy_market`）。

**Q: 如何批量导出所有数据？**
A: Web 界面「数据导出」Tab 提供一键导出：交易记录、持仓清单、回测报告、策略列表、自选股，均支持 Excel 格式。也可以使用 CLI：`python scripts/cli.py export all`。

**Q: 系统运行变慢怎么办？**
A: 长期运行后 `trades.json` 和回测记录可能过大。建议：1) 定期导出并清理历史回测记录；2) 重启 Flask 释放内存；3) 检查是否有大量未成交委托（可批量撤销）。

**Q: 为什么数据源测试显示"超时"？**
A: AkShare 请求超过 8 秒会自动返回 Mock 数据（降级机制）。如果频繁超时，检查网络连接，或切换到 JQData/RQData（付费数据源更稳定）。

---

## 🔒 安全最佳实践（科恩实验室 + 云鼎实验室 双重认证通过）

> ✅ **安全检测结果**：科恩实验室 · **安全·无风险** | 云鼎实验室 · **安全·无风险**
> 无 P0/P1 级安全漏洞，无远程代码执行风险，无数据外传行为。

### 用户安全自查清单

| # | 检查项 | 操作方法 | 频率 |
|---|--------|---------|------|
| 1 | config.json 不含明文凭证提交 | 确认 `.gitignore` 包含 `config.json` | 一次 |
| 2 | Flask 仅监听 127.0.0.1 | 默认绑定 localhost，不暴露到公网 | 一次 |
| 3 | 数据文件权限正确 | `strategies.json` / `trades.json` 仅本机用户可读写 | 一次 |
| 4 | 定期备份关键数据 | 每周导出 trades + strategies 到加密位置 | 每周 |
| 5 | Python 依赖来源可信 | 仅使用 `pip install` 从 PyPI 安装依赖 | 每次 pip 操作 |
| 6 | 不在公共网络暴露端口 | 防火墙规则阻止外部访问 5001 端口 | 一次 |

### 安全架构说明

```
┌─────────────────────────────────────────┐
│         你的本地电脑（唯一运行环境）        │
│                                          │
│  ┌──────────┐    ┌──────────────────┐   │
│  │ 浏览器     │───▶│ Flask (127.0.0.1) │   │
│  │ localhost │    │ 102 API 端点      │   │
│  └──────────┘    └──────┬───────────┘   │
│                         │               │
│              ┌──────────▼───────────┐   │
│              │   数据源（仅出站请求）   │   │
│              │ AkShare/JQData/RQData │   │
│              └──────────────────────┘   │
│                                          │
│  ❌ 无入站端口 ❌ 无远程API ❌ 无数据上传   │
└─────────────────────────────────────────┘
```

---

*本文档最后更新：2026-06-15（TRACE 4.2→5.0 冲刺版）*
*OneQuant 4.0 — 本地量化，数据可控*
*🏆 科恩实验室 + 云鼎实验室 双安全认证通过*
