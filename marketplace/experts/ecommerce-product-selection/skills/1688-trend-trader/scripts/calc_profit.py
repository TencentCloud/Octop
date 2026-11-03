#!/usr/bin/env python3
"""
利润计算器 — calc_profit.py
用法: python3 calc_profit.py <进货价> <售价> [--currency USD|EUR|GBP|USD]
       [--platform amazon|tiktok|shopify|temu]
       [--weight-gkg X]  (克重，g)
       [--freight-kg Y]   (头程每kg单价，美元)
       [--units N]        (首批数量)

依赖：python3（纯标准库，无外部依赖）
网络：无
凭证：无
"""

import sys
import json
import argparse

# 各平台费率参考
PLATFORM_PARAMS = {
    "amazon": {
        "commission_rate": 0.15,
        "fba_per_unit": 3.50,    # FBA 配送费参考
        "ac_acos": 0.25,         # 广告 ACOS
        "return_rate": 0.03,
        "currency_symbol": "$",
    },
    "tiktok": {
        "commission_rate": 0.07,
        "达人佣金": 0.20,
        "海外仓尾程": 5.00,
        "ac_acos": 0.20,
        "return_rate": 0.04,
        "currency_symbol": "$",
    },
    "shopify": {
        "commission_rate": 0.029,   # Stripe
        "paypal": 0.044,
        "物流小包": 20.00,          # 美元/单
        "ac_acos": 0.30,
        "return_rate": 0.02,
        "currency_symbol": "$",
    },
    "temu": {
        "commission_rate": 0.15,
        "推广费": 0.10,
        "退货率": 0.08,
        "currency_symbol": "$",
    },
}

def parse_args():
    p = argparse.ArgumentParser(description="1688 利润计算器")
    p.add_argument("cost_price", type=float, help="1688 进货价（元）")
    p.add_argument("sell_price", type=float, help="平台售价")
    p.add_argument("--currency", default="USD", choices=["USD","EUR","GBP","CNY"], help="目标市场货币")
    p.add_argument("--platform", default="amazon", choices=list(PLATFORM_PARAMS.keys()), help="销售平台")
    p.add_argument("--weight-g", type=float, default=500.0, help="单件克重（g）")
    p.add_argument("--freight-kg", type=float, default=5.0, help="头程每kg单价（美元）")
    p.add_argument("--units", type=int, default=100, help="首批数量")
    p.add_argument("--exchange-rate", type=float, default=7.20, help="汇率 USD/CNY")
    p.add_argument("--exchange-eur", type=float, default=7.80, help="汇率 EUR/CNY")
    p.add_argument("--exchange-gbp", type=float, default=9.10, help="汇率 GBP/CNY")
    p.add_argument("--custom-platform", type=str, default="", help="自定义平台参数 JSON")
    return p.parse_args()


def get_exchange_rate(currency: str, args) -> float:
    rates = {"USD": args.exchange_rate, "EUR": args.exchange_eur, "GBP": args.exchange_gbp, "CNY": 1.0}
    return rates.get(currency, args.exchange_rate)


def calc_profit(args) -> dict:
    platform = args.platform
    p = PLATFORM_PARAMS.get(platform, {})

    # 货币 & 汇率
    currency_sym = p.get("currency_symbol", "$")
    rate = get_exchange_rate(args.currency, args)

    # 售价（转为人民币）
    sell_price_cny = args.sell_price * rate

    # 成本项
    cost = args.cost_price  # 进货价（元）
    weight_kg = args.weight_g / 1000  # 转为kg
    freight_unit = weight_kg * args.freight_kg  # 每件头程（美元→转元）
    freight_unit_cny = freight_unit * rate

    # 平台佣金
    comm = sell_price_cny * p.get("commission_rate", 0)

    # 广告推广
    ad_cost = sell_price_cny * p.get("ac_acos", 0)

    # 尾程（FBA / 海外仓）
    tail_cost = p.get("fba_per_unit", 0) * rate
    if platform == "tiktok":
        tail_cost = p.get("海外仓尾程", 5.0) * rate
    elif platform == "shopify":
        tail_cost = p.get("物流小包", 20.0) * rate

    # 退货损耗
    return_rate = p.get("return_rate", 0.03)
    return_loss = sell_price_cny * return_rate

    # 汇损（1%）
    ex_loss = sell_price_cny * 0.01

    # Temu 特殊处理
    if platform == "temu":
        prom_fee = sell_price_cny * p.get("推广费", 0)
        total_cost = cost + freight_unit_cny + comm + prom_fee + return_loss * sell_price_cny + ex_loss
    else:
        total_cost = cost + freight_unit_cny + comm + ad_cost + tail_cost + return_loss + ex_loss

    # TikTok 达人佣金
    if platform == "tiktok":
        comm += sell_price_cny * p.get("达人佣金", 0.20)
        total_cost = cost + freight_unit_cny + comm + ad_cost + tail_cost + return_loss + ex_loss

    # 利润
    gross_profit = sell_price_cny - total_cost
    gross_margin = gross_profit / sell_price_cny * 100 if sell_price_cny else 0
    unit_profit = gross_profit
    total_profit = gross_profit * args.units

    # Shopify + PayPal 额外
    if platform == "shopify":
        pp_fee = sell_price_cny * p.get("paypal", 0)
        total_cost += pp_fee
        gross_profit = sell_price_cny - total_cost
        gross_margin = gross_profit / sell_price_cny * 100 if sell_price_cny else 0
        unit_profit = gross_profit
        total_profit = gross_profit * args.units

    return {
        "success": True,
        "platform": platform,
        "currency": args.currency,
        "exchange_rate": rate,
        "params": {
            "进货价_元": cost,
            "单件克重_g": args.weight_g,
            "头程单价美元_kg": args.freight_kg,
            "首批数量": args.units,
            "平台佣金": f"{p.get('commission_rate',0)*100:.0f}%",
            "ACOS": f"{p.get('ac_acos',0)*100:.0f}%",
            "退货率": f"{p.get('return_rate',0)*100:.0f}%",
        },
        "cost_breakdown_cny": {
            "进货价": round(cost, 2),
            "头程运费": round(freight_unit_cny, 2),
            "平台佣金": round(comm, 2),
            "推广费": round(ad_cost, 2),
            "尾程配送": round(tail_cost, 2),
            "退货损耗": round(return_loss, 2),
            "汇损": round(ex_loss, 2),
            "合计成本": round(total_cost, 2),
        },
        "sell_price_cny": round(sell_price_cny, 2),
        "unit_profit_cny": round(unit_profit, 2),
        "unit_margin_pct": round(gross_margin, 2),
        "total_profit_cny": round(total_profit, 2),
        "total_cost_cny": round(total_cost * args.units, 2),
        "summary": {
            "单品毛利": f"{gross_margin:.2f}%",
            "单品利润": f"¥{unit_profit:.2f}",
            f"首批{args.units}个总利润": f"¥{total_profit:.2f}",
        },
        "health_check": _health_check(gross_margin, platform),
    }


def _health_check(margin: float, platform: str) -> dict:
    thresholds = {"amazon": 25, "tiktok": 30, "shopify": 40, "temu": 10}
    healthy = margin >= thresholds.get(platform, 25)
    return {
        "healthy": healthy,
        "status": "✅ 健康" if healthy else "⚠️ 偏低",
        "建议": "毛利需达到 "
            + f"{thresholds.get(platform, 25)}%+ "
            + ("（控广告费或换更低价货源）" if not healthy else "（表现良好）")
    }


if __name__ == "__main__":
    args = parse_args()
    result = calc_profit(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
