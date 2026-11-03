#!/usr/bin/env python3
"""Simple long-only backtester for daily OHLCV CSV data.

Signals are generated on bar t close and executed on bar t+1 open to avoid look-ahead.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

TRADING_DAYS = 252


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest stock strategies from OHLCV CSV.")
    parser.add_argument("--csv", required=True, help="Path to CSV with Date and Close columns.")
    parser.add_argument(
        "--strategy",
        default="sma-crossover",
        choices=["sma-crossover", "rsi-reversion", "breakout"],
        help="Strategy name.",
    )
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument("--commission-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--risk-free-rate", type=float, default=0.02)

    parser.add_argument("--fast-window", type=int, default=20)
    parser.add_argument("--slow-window", type=int, default=60)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-entry", type=float, default=30.0)
    parser.add_argument("--rsi-exit", type=float, default=55.0)
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def normalize(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def parse_date(raw: str):
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty date")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"unsupported date format: {raw}") from exc


def parse_float(raw: str, field: str, line_no: int) -> float:
    text = (raw or "").strip()
    if text == "":
        raise ValueError(f"line {line_no}: missing {field}")
    try:
        return float(text.replace(",", ""))
    except ValueError as exc:
        raise ValueError(f"line {line_no}: invalid {field} value '{raw}'") from exc


def resolve_columns(fieldnames):
    by_norm = {normalize(name): name for name in fieldnames}
    aliases = {
        "date": ["date", "datetime", "timestamp", "time"],
        "open": ["open", "openprice", "o"],
        "high": ["high", "highprice", "h"],
        "low": ["low", "lowprice", "l"],
        "close": ["close", "adjclose", "adjustedclose", "c"],
    }
    resolved = {}
    for key, candidates in aliases.items():
        for item in candidates:
            if item in by_norm:
                resolved[key] = by_norm[item]
                break
    if "date" not in resolved or "close" not in resolved:
        raise ValueError("CSV must contain Date and Close columns.")
    return resolved


def load_bars(csv_path: Path):
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    dedup = {}
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV header missing")
        cols = resolve_columns(reader.fieldnames)

        for line_no, row in enumerate(reader, start=2):
            dt = parse_date(row[cols["date"]])
            close = parse_float(row[cols["close"]], "close", line_no)
            open_px = close
            high = close
            low = close
            if "open" in cols and row.get(cols["open"], "").strip():
                open_px = parse_float(row[cols["open"]], "open", line_no)
            if "high" in cols and row.get(cols["high"], "").strip():
                high = parse_float(row[cols["high"]], "high", line_no)
            if "low" in cols and row.get(cols["low"], "").strip():
                low = parse_float(row[cols["low"]], "low", line_no)
            dedup[dt] = {
                "date": dt,
                "open": open_px,
                "high": high,
                "low": low,
                "close": close,
            }

    bars = [dedup[k] for k in sorted(dedup.keys())]
    if len(bars) < 3:
        raise ValueError("Need at least 3 rows.")
    return bars


def sma(values, window: int):
    if window <= 0:
        raise ValueError("window must be > 0")
    out = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def rsi(values, period: int):
    if period <= 0:
        raise ValueError("period must be > 0")
    out = [None] * len(values)
    if len(values) <= period:
        return out

    gains = []
    losses = []
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        gain = max(d, 0.0)
        loss = max(-d, 0.0)
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def max_drawdown(equity_curve):
    peak = equity_curve[0]
    worst = 0.0
    for x in equity_curve:
        if x > peak:
            peak = x
        dd = (x / peak) - 1.0 if peak > 0 else 0.0
        if dd < worst:
            worst = dd
    return abs(worst)


def sharpe_ratio(daily_returns, risk_free_rate: float):
    if len(daily_returns) < 2:
        return 0.0
    vol = stdev(daily_returns)
    if vol == 0:
        return 0.0
    excess = mean(daily_returns) - risk_free_rate / TRADING_DAYS
    return (excess / vol) * math.sqrt(TRADING_DAYS)


def cagr(initial: float, final: float, days: int):
    if initial <= 0 or final <= 0 or days <= 0:
        return -1.0
    years = days / 365.25
    if years <= 0:
        return -1.0
    return (final / initial) ** (1.0 / years) - 1.0


def decide_target(args, i, in_position, closes, highs, lows, fast_sma, slow_sma, rsi_values):
    if args.strategy == "sma-crossover":
        fast = fast_sma[i]
        slow = slow_sma[i]
        if fast is None or slow is None:
            return in_position
        return fast > slow

    if args.strategy == "rsi-reversion":
        v = rsi_values[i]
        if v is None:
            return in_position
        if not in_position and v <= args.rsi_entry:
            return True
        if in_position and v >= args.rsi_exit:
            return False
        return in_position

    if i < args.lookback:
        return in_position
    hi = max(highs[i - args.lookback : i])
    lo = min(lows[i - args.lookback : i])
    if not in_position and closes[i] > hi:
        return True
    if in_position and closes[i] < lo:
        return False
    return in_position


def run_backtest(args, bars):
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    fast_sma = sma(closes, args.fast_window)
    slow_sma = sma(closes, args.slow_window)
    rsi_values = rsi(closes, args.rsi_period)

    commission = max(args.commission_bps, 0.0) / 10000.0
    slippage = max(args.slippage_bps, 0.0) / 10000.0

    cash = args.initial_capital
    shares = 0.0
    in_position = False
    entry_date = None
    entry_basis = 0.0
    entry_price = 0.0
    trades = []
    days_in_market = 0

    equity_curve = [cash]

    for i in range(len(bars) - 1):
        target = decide_target(args, i, in_position, closes, highs, lows, fast_sma, slow_sma, rsi_values)
        next_open = bars[i + 1]["open"]

        if (not in_position) and target:
            px = next_open * (1.0 + slippage)
            unit_cost = px * (1.0 + commission)
            if unit_cost > 0:
                shares = cash / unit_cost
                fee = shares * px * commission
                notional = shares * px
                entry_basis = notional + fee
                cash -= entry_basis
                if cash < 0:
                    cash = 0.0
                in_position = True
                entry_date = bars[i + 1]["date"]
                entry_price = px

        elif in_position and (not target):
            px = next_open * (1.0 - slippage)
            gross = shares * px
            fee = gross * commission
            proceeds = gross - fee
            cash += proceeds
            ret = (proceeds / entry_basis - 1.0) if entry_basis > 0 else 0.0
            trades.append(
                {
                    "entry_date": entry_date.isoformat(),
                    "exit_date": bars[i + 1]["date"].isoformat(),
                    "entry_price": round(entry_price, 6),
                    "exit_price": round(px, 6),
                    "return_pct": round(ret * 100.0, 4),
                    "holding_days": max((bars[i + 1]["date"] - entry_date).days, 1),
                }
            )
            shares = 0.0
            in_position = False
            entry_date = None
            entry_basis = 0.0
            entry_price = 0.0

        equity = cash + (shares * bars[i + 1]["close"] if in_position else 0.0)
        if in_position:
            days_in_market += 1
        equity_curve.append(equity)

    if in_position:
        px = bars[-1]["close"] * (1.0 - slippage)
        gross = shares * px
        fee = gross * commission
        proceeds = gross - fee
        cash += proceeds
        ret = (proceeds / entry_basis - 1.0) if entry_basis > 0 else 0.0
        trades.append(
            {
                "entry_date": entry_date.isoformat(),
                "exit_date": bars[-1]["date"].isoformat(),
                "entry_price": round(entry_price, 6),
                "exit_price": round(px, 6),
                "return_pct": round(ret * 100.0, 4),
                "holding_days": max((bars[-1]["date"] - entry_date).days, 1),
            }
        )
        equity_curve[-1] = cash

    final_equity = equity_curve[-1]
    total_return = final_equity / args.initial_capital - 1.0
    period_days = max((bars[-1]["date"] - bars[0]["date"]).days, 1)

    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            daily_returns.append(equity_curve[i] / prev - 1.0)

    win_count = sum(1 for t in trades if t["return_pct"] > 0)
    win_rate = (win_count / len(trades) * 100.0) if trades else 0.0

    result = {
        "strategy": args.strategy,
        "period": {
            "start": bars[0]["date"].isoformat(),
            "end": bars[-1]["date"].isoformat(),
            "bars": len(bars),
            "days": period_days,
        },
        "metrics": {
            "initial_capital": round(args.initial_capital, 2),
            "final_equity": round(final_equity, 2),
            "net_profit": round(final_equity - args.initial_capital, 2),
            "total_return_pct": round(total_return * 100.0, 4),
            "cagr_pct": round(cagr(args.initial_capital, final_equity, period_days) * 100.0, 4),
            "max_drawdown_pct": round(max_drawdown(equity_curve) * 100.0, 4),
            "sharpe_ratio": round(sharpe_ratio(daily_returns, args.risk_free_rate), 4),
            "trade_count": len(trades),
            "win_rate_pct": round(win_rate, 4),
            "exposure_pct": round((days_in_market / max(len(bars) - 1, 1)) * 100.0, 4),
        },
        "config": {
            "commission_bps": args.commission_bps,
            "slippage_bps": args.slippage_bps,
            "risk_free_rate": args.risk_free_rate,
            "fast_window": args.fast_window,
            "slow_window": args.slow_window,
            "rsi_period": args.rsi_period,
            "rsi_entry": args.rsi_entry,
            "rsi_exit": args.rsi_exit,
            "lookback": args.lookback,
        },
        "trades": trades,
    }
    return result


def validate_args(args):
    if args.initial_capital <= 0:
        raise ValueError("--initial-capital must be > 0")
    if args.fast_window <= 0 or args.slow_window <= 0:
        raise ValueError("--fast-window and --slow-window must be > 0")
    if args.fast_window >= args.slow_window:
        raise ValueError("--fast-window must be smaller than --slow-window")
    if args.rsi_period <= 0:
        raise ValueError("--rsi-period must be > 0")
    if not (0 <= args.rsi_entry <= 100 and 0 <= args.rsi_exit <= 100):
        raise ValueError("--rsi-entry and --rsi-exit must be in [0, 100]")
    if args.rsi_entry >= args.rsi_exit:
        raise ValueError("--rsi-entry must be smaller than --rsi-exit")
    if args.lookback <= 1:
        raise ValueError("--lookback must be > 1")
    if args.commission_bps < 0 or args.slippage_bps < 0:
        raise ValueError("--commission-bps and --slippage-bps must be >= 0")


def main():
    args = parse_args()
    validate_args(args)
    bars = load_bars(Path(args.csv))
    result = run_backtest(args, bars)

    if not args.quiet:
        m = result["metrics"]
        p = result["period"]
        print("Backtest Summary")
        print("================")
        print(f"Strategy: {result['strategy']}")
        print(f"Period:   {p['start']} -> {p['end']} ({p['bars']} bars)")
        print(f"Return:   {m['total_return_pct']}%")
        print(f"CAGR:     {m['cagr_pct']}%")
        print(f"MDD:      {m['max_drawdown_pct']}%")
        print(f"Sharpe:   {m['sharpe_ratio']}")
        print(f"Trades:   {m['trade_count']}")
        print(f"Win rate: {m['win_rate_pct']}%")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
