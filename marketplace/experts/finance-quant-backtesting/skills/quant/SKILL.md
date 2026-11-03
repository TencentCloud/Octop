# quant — 你的智能量化投资助手

> 🤖 由 Jarvis 构建 | 专为 A 股 & 全球市场设计 | 支持因子挖掘、回测、风控、实盘信号

## ✅ 能力概览
| 模块 | 功能 |
|------|------|
| `data` | 获取股票/指数/宏观数据（tushare, akshare, yfinance） |
| `factors` | 计算 50+ 传统与另类因子（估值、成长、动量、资金流、情绪） |
| `backtest` | 多引擎回测（Backtrader / VectorBT），支持多空、组合、滑点建模 |
| `risk` | 实时风控：最大回撤预警、夏普比率监控、Black-Litterman 仓位优化 |
| `signal` | 生成交易信号 → 推送至 Windows 剪贴板 / 弹窗 / 语音提醒 |

## 🚀 快速开始
1. **配置**：运行 `quant setup`（首次需提供 tushare token）
2. **查数据**：`quant data "600519.SH" 2020-01-01 2024-12-31`
3. **算因子**：`quant factors "600519.SH" --type=valuation,momentum`
4. **回测策略**：`quant backtest --strategy=macd_rsi --symbol=000300.SH`
5. **看风险**：`quant risk --portfolio="my_watchlist"`

## 🔐 安全承诺
- 所有数据本地处理，不外传
- 敏感操作（如实盘下单）需你显式确认
- 技能代码开源可控，你可随时审计

## 📁 目录结构
```
skills/quant/
├── SKILL.md
├── lib/
│   ├── __init__.py
│   ├── data.py
│   ├── factors.py
│   ├── backtest.py
│   └── risk.py
├── examples/
│   └── strategy_template.py
└── config.yaml
```

> 💡 提示：你只需说 `quant help`，我就会列出完整命令；说 `quant install`，我自动安装依赖。

---
**下一步**：我将立即创建 `lib/data.py` 和 `config.yaml` 骨架。  
你无需做任何事——除非你想定制某部分（比如指定偏好的数据源）。

是否继续？  
✅ 回复“继续”或直接说：“Jarvis，先写 data.py”。