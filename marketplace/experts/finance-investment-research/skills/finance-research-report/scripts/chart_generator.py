"""
图表生成模块 - 使用 matplotlib 生成 K线/均线、指标、对比柱状图
所有图表返回 base64 编码的 PNG，可直接嵌入 HTML <img> 标签。
"""
import io
import base64
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

# 中文字体
rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "SimHei", "sans-serif"]
rcParams["axes.unicode_minus"] = False


def _fig_to_base64(fig, dpi=150) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def chart_stock_price_ma(df: pd.DataFrame, name: str, symbol: str) -> str:
    """生成价格+均线+成交量图（上下双轴）"""
    df = df.tail(40).copy()
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 3.5), gridspec_kw={"height_ratios": [2.5, 1]}, sharex=True)
    fig.subplots_adjust(hspace=0.08)

    x = range(len(df))
    dates = df["date"].dt.strftime("%m-%d")

    # 价格
    ax1.plot(x, df["close"], color="#333", linewidth=1.2, label="收盘价")
    ax1.plot(x, df["ma5"], color="#e6a817", linewidth=0.8, label="MA5", alpha=0.9)
    ax1.plot(x, df["ma10"], color="#1e88e5", linewidth=0.8, label="MA10", alpha=0.9)
    ax1.plot(x, df["ma20"], color="#d81b60", linewidth=0.8, label="MA20", alpha=0.9)
    ax1.fill_between(x, df["close"].min() * 0.998, df["close"], alpha=0.05, color="#c00")
    ax1.legend(loc="upper left", fontsize=7, ncol=4, framealpha=0.7)
    ax1.set_title(f"{name}（{symbol}）近40日走势", fontsize=10, fontweight="bold")
    ax1.set_ylabel("价格（元）", fontsize=8)
    ax1.tick_params(labelsize=7)
    ax1.grid(axis="y", alpha=0.3)

    # 成交量
    colors = ["#c00" if df["close"].iloc[i] >= df["open"].iloc[i] else "#00a86b" for i in range(len(df))]
    ax2.bar(x, df["volume"] / 1e4, color=colors, alpha=0.7, width=0.6)
    ax2.set_ylabel("成交量(万)", fontsize=7)
    ax2.tick_params(labelsize=7)
    ax2.grid(axis="y", alpha=0.3)

    # X 轴标签
    step = max(1, len(df) // 8)
    ax2.set_xticks(range(0, len(df), step))
    ax2.set_xticklabels([dates.iloc[i] for i in range(0, len(df), step)], fontsize=7, rotation=30)

    return _fig_to_base64(fig)


def chart_macd_rsi(df: pd.DataFrame, name: str, symbol: str) -> str:
    """生成 MACD + RSI 双指标图"""
    df = df.tail(40).copy()

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta).where(delta < 0, 0.0).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 3), gridspec_kw={"height_ratios": [1, 1]}, sharex=True)
    fig.subplots_adjust(hspace=0.15)
    x = range(len(df))
    dates = df["date"].dt.strftime("%m-%d")

    # MACD
    bar_colors = ["#c00" if h >= 0 else "#00a86b" for h in hist]
    ax1.bar(x, hist, color=bar_colors, alpha=0.6, width=0.6)
    ax1.plot(x, macd, color="#1e88e5", linewidth=0.9, label="MACD")
    ax1.plot(x, signal, color="#e6a817", linewidth=0.9, label="Signal")
    ax1.axhline(y=0, color="#999", linewidth=0.5, linestyle="--")
    ax1.legend(fontsize=7, loc="upper left", framealpha=0.7)
    ax1.set_title(f"{name} MACD & RSI", fontsize=9, fontweight="bold")
    ax1.set_ylabel("MACD", fontsize=7)
    ax1.tick_params(labelsize=7)
    ax1.grid(axis="y", alpha=0.3)

    # RSI
    ax2.plot(x, rsi, color="#7b1fa2", linewidth=1)
    ax2.axhline(y=70, color="#c00", linewidth=0.6, linestyle="--", alpha=0.7)
    ax2.axhline(y=30, color="#00a86b", linewidth=0.6, linestyle="--", alpha=0.7)
    ax2.axhline(y=50, color="#999", linewidth=0.4, linestyle=":")
    ax2.fill_between(x, 70, 100, alpha=0.05, color="#c00")
    ax2.fill_between(x, 0, 30, alpha=0.05, color="#00a86b")
    ax2.set_ylabel("RSI(14)", fontsize=7)
    ax2.set_ylim(10, 90)
    ax2.tick_params(labelsize=7)
    ax2.grid(axis="y", alpha=0.3)

    step = max(1, len(df) // 8)
    ax2.set_xticks(range(0, len(df), step))
    ax2.set_xticklabels([dates.iloc[i] for i in range(0, len(df), step)], fontsize=7, rotation=30)

    return _fig_to_base64(fig)


def chart_index_comparison(index_data: dict) -> str:
    """生成主要指数涨跌幅对比柱状图"""
    names = []
    pcts = []
    for name, data in index_data.items():
        if data and "pct_change" in data:
            names.append(name)
            pcts.append(float(data["pct_change"]))

    if not names:
        return ""

    fig, ax = plt.subplots(figsize=(7.5, 2.2))
    colors = ["#c00" if p >= 0 else "#00a86b" for p in pcts]
    bars = ax.barh(names, pcts, color=colors, height=0.5, alpha=0.8)

    for bar, pct in zip(bars, pcts):
        ax.text(bar.get_width() + 0.02 * (1 if pct >= 0 else -1), bar.get_y() + bar.get_height() / 2,
                f"{pct:+.2f}%", va="center", fontsize=8, color="#333",
                ha="left" if pct >= 0 else "right")

    ax.axvline(x=0, color="#999", linewidth=0.5)
    ax.set_title("主要指数日涨跌幅", fontsize=10, fontweight="bold")
    ax.set_xlabel("涨跌幅 (%)", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    return _fig_to_base64(fig)


def chart_signal_summary(signals) -> str:
    """生成信号强度雷达图 / 风险仪表盘"""
    if not signals:
        return ""

    names = [s.name for s in signals]
    buy_counts = [len(s.buy_signals) for s in signals]
    sell_counts = [len(s.sell_signals) for s in signals]
    risk_scores = [s.risk_score for s in signals]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.5, 2.5))

    # 左：买卖信号对比
    x = np.arange(len(names))
    w = 0.3
    ax1.bar(x - w / 2, buy_counts, w, color="#c00", alpha=0.7, label="买入信号")
    ax1.bar(x + w / 2, sell_counts, w, color="#00a86b", alpha=0.7, label="卖出信号")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, fontsize=8)
    ax1.set_ylabel("信号数", fontsize=8)
    ax1.set_title("买卖信号对比", fontsize=9, fontweight="bold")
    ax1.legend(fontsize=7)
    ax1.tick_params(labelsize=7)
    ax1.grid(axis="y", alpha=0.3)

    # 右：风险评分
    colors = ["#00a86b" if r <= 4 else "#e6a817" if r <= 6 else "#c00" for r in risk_scores]
    bars = ax2.barh(names, risk_scores, color=colors, height=0.4, alpha=0.8)
    ax2.set_xlim(0, 10)
    ax2.axvline(x=5, color="#999", linewidth=0.5, linestyle="--")
    for bar, score in zip(bars, risk_scores):
        ax2.text(bar.get_width() + 0.15, bar.get_y() + bar.get_height() / 2,
                 f"{score:.1f}", va="center", fontsize=8)
    ax2.set_title("风险评分 (0-10)", fontsize=9, fontweight="bold")
    ax2.tick_params(labelsize=8)
    ax2.grid(axis="x", alpha=0.3)
    ax2.invert_yaxis()

    fig.tight_layout()
    return _fig_to_base64(fig)
