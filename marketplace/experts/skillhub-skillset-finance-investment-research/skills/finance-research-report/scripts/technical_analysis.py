"""
技术分析模块 - 计算各类技术指标并生成交易信号
参考：日频短期股票分析框架
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field


@dataclass
class TechnicalSignal:
    """技术分析信号汇总"""
    symbol: str
    name: str = ""
    date: str = ""
    close: float = 0.0
    pct_change_1d: float = 0.0
    pct_change_5d: float = 0.0

    # 均线
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma_alignment: str = ""  # 多头/空头/震荡

    # 成交量
    volume_ratio: float = 0.0  # 量比
    turnover_rate: float = 0.0
    volume_trend: str = ""  # 放量/缩量/平稳

    # 波动率
    atr: float = 0.0
    std_dev: float = 0.0
    intraday_range: float = 0.0

    # 动量指标
    rsi: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    kdj_k: float = 0.0
    kdj_d: float = 0.0
    kdj_j: float = 0.0

    # 信号
    buy_signals: list = field(default_factory=list)
    sell_signals: list = field(default_factory=list)
    signal_strength: str = ""  # 强/中/弱
    risk_score: float = 0.0  # 0-10
    position_coeff: float = 0.0

    # 止损止盈
    stop_loss: float = 0.0
    take_profit: float = 0.0

    def summary(self) -> str:
        direction = "看多" if len(self.buy_signals) > len(self.sell_signals) else "看空" if len(self.sell_signals) > len(self.buy_signals) else "中性"
        return f"{direction} | 信号强度: {self.signal_strength} | 风险评分: {self.risk_score:.1f}/10"


def calc_ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    # 使用 EMA 方式平滑
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1 / m1, adjust=False).mean()
    d = k.ewm(alpha=1 / m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def calc_volume_ratio(volume: pd.Series, period: int = 5) -> float:
    """量比 = 当日成交量 / 过去N日平均成交量"""
    if len(volume) < period + 1:
        return 1.0
    avg = volume.iloc[-(period + 1):-1].mean()
    if avg == 0:
        return 1.0
    return volume.iloc[-1] / avg


def determine_ma_alignment(ma5: float, ma10: float, ma20: float) -> str:
    if ma5 > ma10 > ma20:
        return "多头排列"
    elif ma5 < ma10 < ma20:
        return "空头排列"
    else:
        return "震荡整理"


def determine_volume_trend(volume: pd.Series, period: int = 5) -> str:
    if len(volume) < period + 1:
        return "数据不足"
    recent_avg = volume.iloc[-period:].mean()
    prev_avg = volume.iloc[-(period * 2):-period].mean() if len(volume) >= period * 2 else volume.mean()
    ratio = recent_avg / prev_avg if prev_avg > 0 else 1.0
    if ratio > 1.3:
        return "放量"
    elif ratio < 0.7:
        return "缩量"
    else:
        return "平稳"


def generate_buy_signals(sig: TechnicalSignal, df: pd.DataFrame) -> list[str]:
    signals = []
    ma5_series = calc_ma(df["close"], 5)
    ma10_series = calc_ma(df["close"], 10)

    # MA5上穿MA10（金叉）
    if len(ma5_series) >= 2 and len(ma10_series) >= 2:
        if ma5_series.iloc[-2] <= ma10_series.iloc[-2] and ma5_series.iloc[-1] > ma10_series.iloc[-1]:
            signals.append("MA5上穿MA10（金叉）")

    # 价格突破MA10且站稳
    if sig.close > sig.ma10 and df["close"].iloc[-2] <= ma10_series.iloc[-2]:
        signals.append("价格突破MA10")

    # 量比>1.2且价格上涨
    if sig.volume_ratio > 1.2 and sig.pct_change_1d > 0:
        signals.append(f"量价齐升（量比{sig.volume_ratio:.2f}）")

    # RSI > 50 且 < 70
    if 50 < sig.rsi < 70:
        signals.append(f"RSI动量良好（{sig.rsi:.1f}）")

    # MACD柱状线由负转正
    _, _, hist = calc_macd(df["close"])
    if len(hist) >= 2 and hist.iloc[-2] < 0 and hist.iloc[-1] > 0:
        signals.append("MACD柱状线翻红")

    return signals


def generate_sell_signals(sig: TechnicalSignal, df: pd.DataFrame) -> list[str]:
    signals = []
    ma5_series = calc_ma(df["close"], 5)
    ma10_series = calc_ma(df["close"], 10)

    # MA5下穿MA10（死叉）
    if len(ma5_series) >= 2 and len(ma10_series) >= 2:
        if ma5_series.iloc[-2] >= ma10_series.iloc[-2] and ma5_series.iloc[-1] < ma10_series.iloc[-1]:
            signals.append("MA5下穿MA10（死叉）")

    # 价格跌破MA5且成交量放大
    if sig.close < sig.ma5 and sig.volume_ratio > 1.2 and sig.pct_change_1d < 0:
        signals.append("放量跌破MA5")

    # RSI > 80（超买）
    if sig.rsi > 80:
        signals.append(f"RSI超买（{sig.rsi:.1f}）")

    # 5日累计涨幅 > 15%
    if sig.pct_change_5d > 15:
        signals.append(f"5日累计涨幅过大（{sig.pct_change_5d:.1f}%）")

    # KDJ超买
    if sig.kdj_j > 100:
        signals.append(f"KDJ超买（J={sig.kdj_j:.1f}）")

    return signals


def calc_risk_score(sig: TechnicalSignal) -> float:
    """风险评分 0-10，越高风险越大"""
    score = 5.0  # 基准分

    # RSI风险
    if sig.rsi > 80:
        score += 2.0
    elif sig.rsi > 70:
        score += 1.0
    elif sig.rsi < 30:
        score += 1.5
    elif sig.rsi < 20:
        score += 2.5

    # 波动率风险
    if sig.close > 0:
        atr_pct = sig.atr / sig.close * 100
        if atr_pct > 5:
            score += 1.5
        elif atr_pct > 3:
            score += 0.5

    # 均线排列
    if sig.ma_alignment == "空头排列":
        score += 1.0
    elif sig.ma_alignment == "多头排列":
        score -= 1.0

    # 量比异常
    if sig.volume_ratio > 3:
        score += 1.0

    # 5日涨幅过大
    if sig.pct_change_5d > 15:
        score += 1.5
    elif sig.pct_change_5d < -10:
        score += 1.0

    return max(0.0, min(10.0, score))


def analyze_stock(df: pd.DataFrame, symbol: str, name: str = "") -> TechnicalSignal:
    """对单只股票进行完整技术分析"""
    sig = TechnicalSignal(symbol=symbol, name=name)

    if df.empty or len(df) < 20:
        return sig

    sig.date = df["date"].iloc[-1].strftime("%Y-%m-%d")
    sig.close = df["close"].iloc[-1]
    sig.pct_change_1d = ((df["close"].iloc[-1] / df["close"].iloc[-2]) - 1) * 100 if len(df) >= 2 else 0
    sig.pct_change_5d = ((df["close"].iloc[-1] / df["close"].iloc[-6]) - 1) * 100 if len(df) >= 6 else 0

    # 均线
    ma5 = calc_ma(df["close"], 5)
    ma10 = calc_ma(df["close"], 10)
    ma20 = calc_ma(df["close"], 20)
    sig.ma5 = ma5.iloc[-1]
    sig.ma10 = ma10.iloc[-1]
    sig.ma20 = ma20.iloc[-1]
    sig.ma_alignment = determine_ma_alignment(sig.ma5, sig.ma10, sig.ma20)

    # 成交量
    sig.volume_ratio = calc_volume_ratio(df["volume"])
    sig.turnover_rate = df["turnover_rate"].iloc[-1] if "turnover_rate" in df.columns else 0.0
    sig.volume_trend = determine_volume_trend(df["volume"])

    # 波动率
    atr = calc_atr(df)
    sig.atr = atr.iloc[-1] if not atr.empty else 0
    sig.std_dev = df["close"].iloc[-20:].std()
    sig.intraday_range = (df["high"].iloc[-1] - df["low"].iloc[-1]) / df["close"].iloc[-1] * 100

    # 动量指标
    rsi = calc_rsi(df["close"])
    sig.rsi = rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50

    macd_line, signal_line, hist = calc_macd(df["close"])
    sig.macd = macd_line.iloc[-1]
    sig.macd_signal = signal_line.iloc[-1]
    sig.macd_hist = hist.iloc[-1]

    k, d, j = calc_kdj(df)
    sig.kdj_k = k.iloc[-1]
    sig.kdj_d = d.iloc[-1]
    sig.kdj_j = j.iloc[-1]

    # 信号判断
    sig.buy_signals = generate_buy_signals(sig, df)
    sig.sell_signals = generate_sell_signals(sig, df)

    # 风险评估
    sig.risk_score = calc_risk_score(sig)
    sig.position_coeff = max(0, (10 - sig.risk_score)) / 10

    # 信号强度
    net_signal = len(sig.buy_signals) - len(sig.sell_signals)
    if abs(net_signal) >= 3:
        sig.signal_strength = "强"
    elif abs(net_signal) >= 1:
        sig.signal_strength = "中"
    else:
        sig.signal_strength = "弱"

    # 止损止盈
    prev_low = df["low"].iloc[-2] if len(df) >= 2 else sig.close
    sig.stop_loss = min(prev_low * 0.995, sig.ma10 * 0.99, sig.close * 0.95)
    sig.take_profit = sig.close + sig.atr * 2 if sig.atr > 0 else sig.close * 1.08

    return sig
