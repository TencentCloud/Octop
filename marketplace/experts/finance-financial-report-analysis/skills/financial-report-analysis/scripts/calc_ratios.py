#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
财报解读 · 核心指标计算器

输入一个 JSON（结构见 assets/input_template.json，支持中英文键名），
输出：平衡校验 / 盈利能力 / 回报与杜邦分解 / 营运效率 / 偿债与资本结构 /
      现金流质量 / 多期同比对照，全部为 Markdown 表格。

用法：
    python calc_ratios.py --input data.json
    python calc_ratios.py --input data.json --out result.md

设计原则：
    - 只做确定性算术，不做任何推断；缺数据输出「未披露」，绝不补值、绝不估算。
    - 有期初值就用平均口径，没有就退回期末口径并在表里标注口径。
"""

import argparse
import json
import sys
from pathlib import Path

NA = "未披露"

# ---------------------------------------------------------------- 科目别名表
# 规范键 -> 允许的输入键（英文 / 中文 / 常见财报措辞）
ALIASES = {
    # 利润表
    "revenue": ["revenue", "营业收入", "营业总收入", "营收", "主营业务收入"],
    "cost": ["cost", "cogs", "营业成本", "主营业务成本"],
    "gross_profit": ["gross_profit", "毛利", "毛利润"],
    "tax_surcharge": ["tax_surcharge", "税金及附加"],
    "selling_exp": ["selling_exp", "销售费用"],
    "admin_exp": ["admin_exp", "管理费用"],
    "rd_exp": ["rd_exp", "研发费用", "研究与开发费用"],
    "finance_exp": ["finance_exp", "财务费用"],
    "op_profit": ["op_profit", "营业利润"],
    "pretax_profit": ["pretax_profit", "利润总额", "税前利润"],
    "net_profit": ["net_profit", "净利润"],
    "net_profit_parent": ["net_profit_parent", "归母净利润", "归属于母公司股东的净利润",
                          "归属母公司净利润", "归属于上市公司股东的净利润"],
    "net_profit_deducted": ["net_profit_deducted", "扣非净利润", "扣除非经常性损益后的净利润",
                            "扣非归母净利润", "归属于上市公司股东的扣除非经常性损益的净利润"],
    "nonrecurring": ["nonrecurring", "非经常性损益"],
    "eps": ["eps", "每股收益", "基本每股收益"],
    # 资产负债表
    "cash": ["cash", "货币资金"],
    "trading_fin_assets": ["trading_fin_assets", "交易性金融资产"],
    "ar": ["ar", "应收账款", "应收账款净额"],
    "contract_assets": ["contract_assets", "合同资产"],
    "prepay": ["prepay", "预付款项", "预付账款"],
    "inventory": ["inventory", "存货"],
    "total_current_assets": ["total_current_assets", "流动资产合计", "流动资产"],
    "fixed_assets": ["fixed_assets", "固定资产"],
    "cip": ["cip", "在建工程"],
    "intangibles": ["intangibles", "无形资产"],
    "goodwill": ["goodwill", "商誉"],
    "total_assets": ["total_assets", "资产总计", "总资产", "资产合计"],
    "st_debt": ["st_debt", "短期借款"],
    "notes_payable": ["notes_payable", "应付票据"],
    "ap": ["ap", "应付账款", "应付票据及应付账款"],
    "contract_liab": ["contract_liab", "合同负债"],
    "total_current_liab": ["total_current_liab", "流动负债合计", "流动负债"],
    "lt_debt": ["lt_debt", "长期借款"],
    "bonds": ["bonds", "应付债券"],
    "total_liab": ["total_liab", "负债合计", "总负债"],
    "total_equity": ["total_equity", "所有者权益合计", "股东权益合计", "净资产"],
    "equity_parent": ["equity_parent", "归母股东权益", "归属于母公司股东权益合计",
                      "归属母公司所有者权益"],
    "minority_equity": ["minority_equity", "少数股东权益"],
    # 期初值（用于平均口径）
    "begin_total_assets": ["begin_total_assets", "期初总资产", "上年末总资产"],
    "begin_equity_parent": ["begin_equity_parent", "期初归母权益", "上年末归母权益"],
    "begin_ar": ["begin_ar", "期初应收账款", "上年末应收账款"],
    "begin_inventory": ["begin_inventory", "期初存货", "上年末存货"],
    "begin_ap": ["begin_ap", "期初应付账款", "上年末应付账款"],
    # 现金流量表
    "ocf": ["ocf", "经营活动产生的现金流量净额", "经营活动现金流净额", "经营现金流"],
    "icf": ["icf", "投资活动产生的现金流量净额", "投资活动现金流净额"],
    "fcf_fin": ["fcf_fin", "筹资活动产生的现金流量净额", "筹资活动现金流净额"],
    "capex": ["capex", "购建固定资产、无形资产和其他长期资产支付的现金", "资本开支", "购建长期资产支付的现金"],
    "dep_amort": ["dep_amort", "折旧与摊销", "折旧摊销", "固定资产折旧、油气资产折耗、生产性生物资产折旧"],
    "interest_paid": ["interest_paid", "已付利息", "分配股利、利润或偿付利息支付的现金"],
    "ending_cash": ["ending_cash", "期末现金及现金等价物余额", "期末现金余额"],
}


def build_lookup(period_dict):
    """把任意键名归一化到规范键。"""
    norm = {}
    flat = {}
    for section in ("income", "balance", "cashflow", "extra", "other"):
        part = period_dict.get(section)
        if isinstance(part, dict):
            flat.update(part)
    flat.update({k: v for k, v in period_dict.items()
                 if k not in ("income", "balance", "cashflow", "extra", "other",
                              "period", "label", "期间")})
    for k, v in flat.items():
        if isinstance(v, (int, float)):
            norm[str(k).strip().lower()] = float(v)
    out = {}
    for canon, names in ALIASES.items():
        for n in names:
            key = n.strip().lower()
            if key in norm:
                out[canon] = norm[key]
                break
    return out


# ---------------------------------------------------------------- 工具
def g(d, key):
    """取值，缺失返回 None。"""
    v = d.get(key)
    return None if v is None else float(v)


def div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def avg(a, b):
    """平均口径：有期初取平均，无期初退回期末。返回 (值, 口径说明)。"""
    if b is None:
        return a, "期末"
    if a is None:
        return None, "期末"
    return (a + b) / 2.0, "平均"


def pct(x, digits=2):
    return NA if x is None else f"{x * 100:.{digits}f}%"


def num(x, digits=2):
    return NA if x is None else f"{x:,.{digits}f}"


def ratio(x, digits=2):
    return NA if x is None else f"{x:.{digits}f}"


def days(x, digits=1):
    return NA if x is None else f"{x:.{digits}f}"


def chg(cur, prev):
    """同比变化：(本期-上期)/|上期|。返回 (文本, 数值)。"""
    if cur is None or prev is None or prev == 0:
        return NA, None
    d = (cur - prev) / abs(prev)
    return f"{d * 100:+.2f}%", d


def delta_pp(cur, prev):
    """比率型指标的变动，用百分点。"""
    if cur is None or prev is None:
        return NA
    return f"{(cur - prev) * 100:+.2f}pp"


def arrow(x):
    if x is None:
        return ""
    return "↑" if x > 0 else ("↓" if x < 0 else "→")


def fmt_cell(v, fmt_kind):
    if fmt_kind == "pct":
        return pct(v)
    if fmt_kind == "ratio":
        return ratio(v)
    if fmt_kind == "days":
        return days(v)
    return num(v)


def chg_cell(cur, prev, fmt_kind):
    """期间变动：比率型用百分点(pp)，绝对/倍数型用百分比。"""
    if prev is None or cur is None:
        return "—"
    if fmt_kind == "pct":
        return delta_pp(cur, prev)
    c, _ = chg(cur, prev)
    return c


# ---------------------------------------------------------------- 计算
def compute_period(d):
    """算出单期全部指标。"""
    r = {"_raw": d}

    # --- 规模
    rev = g(d, "revenue")
    r["revenue"] = rev
    cost = g(d, "cost")
    gp = g(d, "gross_profit")
    if gp is None and rev is not None and cost is not None:
        gp = rev - cost
    r["gross_profit"] = gp
    r["cost"] = cost
    r["net_profit"] = g(d, "net_profit")
    r["net_profit_parent"] = g(d, "net_profit_parent")
    r["net_profit_deducted"] = g(d, "net_profit_deducted")
    r["eps"] = g(d, "eps")

    # --- 盈利
    r["gross_margin"] = div(gp, rev)
    r["net_margin"] = div(r["net_profit"], rev)
    r["parent_margin"] = div(r["net_profit_parent"], rev)
    r["deducted_margin"] = div(r["net_profit_deducted"], rev)
    r["selling_ratio"] = div(g(d, "selling_exp"), rev)
    r["admin_ratio"] = div(g(d, "admin_exp"), rev)
    r["rd_ratio"] = div(g(d, "rd_exp"), rev)
    r["finance_ratio"] = div(g(d, "finance_exp"), rev)
    r["op_margin"] = div(g(d, "op_profit"), rev)

    # --- 回报
    ta = g(d, "total_assets")
    ta_b = g(d, "begin_total_assets")
    eqp = g(d, "equity_parent")
    eqp_b = g(d, "begin_equity_parent")
    if eqp is None:
        te = g(d, "total_equity")
        mi = g(d, "minority_equity")
        if te is not None and mi is not None:
            eqp = te - mi
    r["total_assets"] = ta
    r["equity_parent"] = eqp

    ta_avg, ta_basis = avg(ta, ta_b)
    eqp_avg, eq_basis = avg(eqp, eqp_b)
    r["ta_basis"] = ta_basis
    r["eq_basis"] = eq_basis

    np_parent = r["net_profit_parent"] if r["net_profit_parent"] is not None else r["net_profit"]
    r["roe"] = div(np_parent, eqp_avg)
    r["roe_end"] = div(np_parent, eqp)
    r["roa"] = div(r["net_profit"], ta_avg)
    r["asset_turnover"] = div(rev, ta_avg)
    if ta_avg and eqp_avg:
        r["equity_multiplier"] = ta_avg / eqp_avg
    elif ta and eqp:
        r["equity_multiplier"] = ta / eqp
    else:
        r["equity_multiplier"] = None

    # ROIC ≈ 息前税后经营利润 / (有息负债 + 归母权益) 平均
    ib = 0.0
    ib_parts = [g(d, "st_debt"), g(d, "lt_debt"), g(d, "bonds")]
    if all(p is None for p in ib_parts):
        r["ib_debt"] = None
    else:
        r["ib_debt"] = sum(p for p in ib_parts if p is not None)
        ib = r["ib_debt"]
    fin_exp = g(d, "finance_exp") or 0.0
    tax_rate = 0.25
    nopat = None
    base = r["net_profit"] if r["net_profit"] is not None else np_parent
    if base is not None:
        nopat = base + fin_exp * (1 - tax_rate)
    invest_cap = None
    if eqp_avg is not None:
        invest_cap = eqp_avg + (ib if r["ib_debt"] is not None else 0.0)
    r["roic"] = div(nopat, invest_cap)
    r["_roic_note"] = "假设税率 25%，以净利润+财务费用×(1−25%) 近似 NOPAT" if r["roic"] is not None else ""

    # --- 营运
    ar = g(d, "ar")
    inv = g(d, "inventory")
    ap = g(d, "ap")
    ar_avg, _ = avg(ar, g(d, "begin_ar"))
    inv_avg, _ = avg(inv, g(d, "begin_inventory"))
    ap_avg, _ = avg(ap, g(d, "begin_ap"))
    r["ar_turnover"] = div(rev, ar_avg)
    r["inv_turnover"] = div(cost if cost is not None else rev, inv_avg)
    r["ap_turnover"] = div(cost if cost is not None else rev, ap_avg)
    r["ar_days"] = 365.0 / r["ar_turnover"] if r["ar_turnover"] else None
    r["inv_days"] = 365.0 / r["inv_turnover"] if r["inv_turnover"] else None
    r["ap_days"] = 365.0 / r["ap_turnover"] if r["ap_turnover"] else None
    if None not in (r["ar_days"], r["inv_days"], r["ap_days"]):
        r["ccc"] = r["ar_days"] + r["inv_days"] - r["ap_days"]
    else:
        r["ccc"] = None

    # --- 偿债
    tl = g(d, "total_liab")
    r["total_liab"] = tl
    if tl is None and ta is not None and g(d, "total_equity") is not None:
        tl = ta - g(d, "total_equity")
        r["total_liab"] = tl
    r["debt_ratio"] = div(tl, ta)
    ca = g(d, "total_current_assets")
    cl = g(d, "total_current_liab")
    r["current_ratio"] = div(ca, cl)
    quick = None
    if ca is not None and inv is not None and cl:
        quick = (ca - inv) / cl
    r["quick_ratio"] = quick
    r["ib_ratio"] = div(r["ib_debt"], ta)
    r["net_cash"] = None if (g(d, "cash") is None or r["ib_debt"] is None) else g(d, "cash") - r["ib_debt"]
    r["cash"] = g(d, "cash")
    r["goodwill"] = g(d, "goodwill")
    r["goodwill_to_equity"] = div(g(d, "goodwill"), eqp)
    r["goodwill_to_assets"] = div(g(d, "goodwill"), ta)
    r["contract_liab"] = g(d, "contract_liab")

    # --- 现金流
    ocf = g(d, "ocf")
    capex = g(d, "capex")
    r["ocf"] = ocf
    r["icf"] = g(d, "icf")
    r["fcf_fin"] = g(d, "fcf_fin")
    r["capex"] = capex
    r["ocf_to_np"] = div(ocf, r["net_profit"])
    r["ocf_to_np_parent"] = div(ocf, np_parent)
    r["ocf_to_rev"] = div(ocf, rev)
    r["fcf"] = None if (ocf is None or capex is None) else ocf - capex
    r["capex_to_ocf"] = div(capex, ocf)
    r["dep_amort"] = g(d, "dep_amort")

    # --- 平衡校验
    ta_v = ta
    te_v = g(d, "total_equity")
    tl_v = g(d, "total_liab")
    if None not in (ta_v, te_v, tl_v) and ta_v != 0:
        diff = ta_v - (tl_v + te_v)
        r["balance_diff"] = diff
        r["balance_diff_pct"] = diff / ta_v
    else:
        r["balance_diff"] = None
        r["balance_diff_pct"] = None

    # --- 盈利质量
    r["deducted_share"] = div(r["net_profit_deducted"], r["net_profit_parent"])
    r["nonrecurring_share"] = div(g(d, "nonrecurring"), r["net_profit_parent"])
    return r


# ---------------------------------------------------------------- 输出
def render(data, periods_r):
    """
    约定：periods 数组按时间倒序排列，periods[0] 为「本期」，periods[1] 为「上期」。
    每一期的「同比变动」列 = 本期 vs 数组中紧随其后的那一期（更早一期）。
    """
    L = []
    company = data.get("company", data.get("公司", "（未填公司名）"))
    currency = data.get("currency", data.get("币种", "未披露"))
    unit = data.get("unit", data.get("单位", "未披露"))
    L.append(f"# {company} · 财报核心指标测算")
    L.append("")
    L.append(f"- 币种：{currency}　单位：{unit}　"
             f"报表口径：{data.get('basis', data.get('口径', '合并报表'))}")
    L.append(f"- 数据来源：{data.get('source', data.get('数据来源', '用户提供财报数据'))}")
    L.append(f"- 期间顺序：periods 按时间倒序，**本期 = {periods_r[0]['label']}**；"
             f"「同比变动」列 = 该期 vs 数组中更早一期。")
    L.append("- 说明：本表由 `calc_ratios.py` 确定性计算生成；缺失项一律标「未披露」，未做任何估算或补值。")
    L.append("")

    labels = [p["label"] for p in periods_r]

    def table(title, rows):
        n = len(labels)
        out = [f"## {title}", "",
               "| 指标 |" + "".join(f" {lab} | 同比变动 |" for lab in labels),
               "|" + "---|" * (1 + 2 * n)]
        for label, key, fmt_kind in rows:
            vals = [p["r"].get(key) for p in periods_r]
            cells = []
            for i, v in enumerate(vals):
                cells.append(fmt_cell(v, fmt_kind))
                prev = vals[i + 1] if i + 1 < n else None
                cells.append(chg_cell(v, prev, fmt_kind))
            out.append(f"| {label} | " + " | ".join(cells) + " |")
        out.append("")
        return out

    # 0 平衡校验
    L.append("## 0. 数据校验")
    L.append("")
    L.append("| 期间 | 资产总计 | 负债合计+权益 | 差额 | 差额占比 | 结论 |")
    L.append("|---|---|---|---|---|---|")
    for p in periods_r:
        r = p["r"]
        ta = r.get("total_assets")
        tl = r.get("total_liab")
        te = p["d"].get("total_equity")
        diff = r.get("balance_diff")
        dp = r.get("balance_diff_pct")
        if diff is None:
            L.append(f"| {p['label']} | {num(ta)} | {NA} | {NA} | {NA} | 缺负债或权益数据，无法校验 |")
        else:
            ok = abs(dp) <= 0.005
            L.append(f"| {p['label']} | {num(ta)} | {num((tl or 0) + (te or 0))} | {num(diff)} | {pct(dp)} | "
                     f"{'✅ 勾稽平衡' if ok else '⚠️ 不平，需回查原始报表'} |")
    L.append("")

    # 1 规模与盈利
    L += table("1. 规模与利润表核心（单位：" + str(unit) + "）", [
        ("营业收入", "revenue", "num"),
        ("营业成本", "cost", "num"),
        ("毛利", "gross_profit", "num"),
        ("净利润", "net_profit", "num"),
        ("归母净利润", "net_profit_parent", "num"),
        ("扣非净利润", "net_profit_deducted", "num"),
        ("基本每股收益 EPS", "eps", "num"),
    ])

    # 2 盈利能力
    L += table("2. 盈利能力（占营业收入比重）", [
        ("毛利率 = 毛利/营业收入", "gross_margin", "pct"),
        ("营业利润率 = 营业利润/营业收入", "op_margin", "pct"),
        ("净利率 = 净利润/营业收入", "net_margin", "pct"),
        ("归母净利率 = 归母净利润/营业收入", "parent_margin", "pct"),
        ("扣非净利率 = 扣非净利润/营业收入", "deducted_margin", "pct"),
        ("销售费用率", "selling_ratio", "pct"),
        ("管理费用率", "admin_ratio", "pct"),
        ("研发费用率", "rd_ratio", "pct"),
        ("财务费用率", "finance_ratio", "pct"),
    ])

    # 3 回报与杜邦
    L.append("## 3. 回报水平与杜邦分解")
    L.append("")
    basis_note = "；".join(f"{p['label']}：总资产取{p['r'].get('ta_basis')}口径、归母权益取{p['r'].get('eq_basis')}口径"
                          for p in periods_r)
    L.append(f"> 口径：{basis_note}。有期初值用平均口径，无期初值退回期末口径。")
    L.append("")
    L += table("3.1 回报指标", [
        ("ROE = 归母净利润/平均归母权益", "roe", "pct"),
        ("ROE（期末口径）", "roe_end", "pct"),
        ("ROA = 净利润/平均总资产", "roa", "pct"),
        ("ROIC（近似，税率假设25%）", "roic", "pct"),
    ])
    L += table("3.2 杜邦三因子（ROE = 净利率 × 总资产周转率 × 权益乘数）", [
        ("净利率（归母净利率）", "parent_margin", "pct"),
        ("总资产周转率 = 营业收入/平均总资产", "asset_turnover", "ratio"),
        ("权益乘数 = 平均总资产/平均归母权益", "equity_multiplier", "ratio"),
        ("→ 相乘还原 ROE", "roe", "pct"),
    ])

    # 4 营运效率
    L += table("4. 营运效率（天）", [
        ("应收账款周转天数 = 365/(营业收入/平均应收)", "ar_days", "days"),
        ("存货周转天数 = 365/(营业成本/平均存货)", "inv_days", "days"),
        ("应付账款周转天数 = 365/(营业成本/平均应付)", "ap_days", "days"),
        ("现金转换周期 CCC = 应收+存货−应付", "ccc", "days"),
    ])

    # 5 偿债与资本结构
    L.append("## 5. 偿债能力与资本结构（单位：" + str(unit) + "，比率除外）")
    L.append("")
    L += table("5.1 偿债指标", [
        ("资产负债率 = 负债合计/资产总计", "debt_ratio", "pct"),
        ("流动比率 = 流动资产/流动负债", "current_ratio", "ratio"),
        ("速动比率 = (流动资产−存货)/流动负债", "quick_ratio", "ratio"),
        ("有息负债率 = 有息负债/资产总计", "ib_ratio", "pct"),
        ("商誉/归母权益", "goodwill_to_equity", "pct"),
    ])
    L += table("5.2 关键科目", [
        ("货币资金", "cash", "num"),
        ("有息负债（短借+长借+债券）", "ib_debt", "num"),
        ("净现金 = 货币资金−有息负债", "net_cash", "num"),
        ("商誉", "goodwill", "num"),
        ("合同负债", "contract_liab", "num"),
    ])

    # 6 现金流质量
    L += table("6. 现金流质量（单位：" + str(unit) + "，比率除外）", [
        ("经营活动现金流净额 OCF", "ocf", "num"),
        ("投资活动现金流净额", "icf", "num"),
        ("筹资活动现金流净额", "fcf_fin", "num"),
        ("资本开支", "capex", "num"),
        ("自由现金流 FCF = OCF − 资本开支", "fcf", "num"),
        ("OCF/净利润（现金流匹配度）", "ocf_to_np", "ratio"),
        ("OCF/归母净利润", "ocf_to_np_parent", "ratio"),
        ("OCF/营业收入", "ocf_to_rev", "ratio"),
        ("资本开支/OCF", "capex_to_ocf", "pct"),
    ])

    # 7 盈利质量
    L += table("7. 盈利质量", [
        ("扣非净利润/归母净利润", "deducted_share", "pct"),
        ("非经常性损益/归母净利润", "nonrecurring_share", "pct"),
    ])

    # 8 提示
    L.append("## 8. 自动提示")
    L.append("")
    tips = []
    p = periods_r[0]["r"]          # 本期 = 数组第一项
    lab = periods_r[0]["label"]
    if p.get("ocf_to_np") is not None and p["ocf_to_np"] < 0.8:
        tips.append(f"- ⚠️ {lab} OCF/净利润 = {ratio(p['ocf_to_np'])}，低于 0.8，净利润含金量偏弱，需查应收/存货占用。")
    if p.get("deducted_share") is not None and p["deducted_share"] < 0.8:
        tips.append(f"- ⚠️ {lab} 扣非占归母仅 {pct(p['deducted_share'])}，利润对非经常性损益依赖度高。")
    if p.get("balance_diff_pct") is not None and abs(p["balance_diff_pct"]) > 0.005:
        tips.append(f"- ⚠️ {lab} 资产负债表勾稽不平（差额占比 {pct(p['balance_diff_pct'])}），回查原始报表。")
    if p.get("goodwill_to_equity") is not None and p["goodwill_to_equity"] > 0.3:
        tips.append(f"- ⚠️ {lab} 商誉/归母权益 = {pct(p['goodwill_to_equity'])}，超过 30%，减值风险需单列。")
    if p.get("current_ratio") is not None and p["current_ratio"] < 1:
        tips.append(f"- ⚠️ {lab} 流动比率 {ratio(p['current_ratio'])} < 1，短期偿付压力需关注。")
    if p.get("net_cash") is not None and p["net_cash"] < 0:
        tips.append(f"- ⚠️ {lab} 净现金为负（{num(p['net_cash'])}），处于净负债状态。")
    if p.get("ccc") is not None and p["ccc"] > 120:
        tips.append(f"- ⚠️ {lab} 现金转换周期 {days(p['ccc'])} 天，营运资金占用偏重。")
    if len(periods_r) >= 2:
        cur, prev = periods_r[0]["r"], periods_r[1]["r"]
        if cur.get("gross_margin") is not None and prev.get("gross_margin") is not None:
            d = cur["gross_margin"] - prev["gross_margin"]
            if abs(d) >= 0.02:
                tips.append(f"- 毛利率变动 {d * 100:+.2f}pp，需在报告里给出量价/成本拆解。")
        if cur.get("revenue") is not None and prev.get("revenue") is not None:
            c, _ = chg(cur["revenue"], prev["revenue"])
            tips.append(f"- 营业收入同比 {c}（{periods_r[0]['label']} vs {periods_r[1]['label']}）。")
        if cur.get("ocf") is not None and prev.get("ocf") is not None:
            c, _ = chg(cur["ocf"], prev["ocf"])
            tips.append(f"- 经营现金流同比 {c}。")
    if not tips:
        tips.append("- 未触发自动告警项，仍需人工按「财务质量红旗清单」复核。")
    L += tips
    L.append("")
    L.append("---")
    L.append("")
    L.append("本表仅为财务数据的客观测算与结构化呈现，不构成投资建议。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="财报解读 · 核心指标计算器")
    ap.add_argument("--input", required=True, help="输入 JSON 文件路径")
    ap.add_argument("--out", help="输出 Markdown 文件路径（默认打印到标准输出）")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"❌ 找不到输入文件：{src}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败：{e}", file=sys.stderr)
        sys.exit(1)

    raw_periods = data.get("periods") or data.get("期间")
    if not raw_periods:
        print("❌ 输入缺少 periods 数组", file=sys.stderr)
        sys.exit(1)

    periods_r = []
    for i, p in enumerate(raw_periods):
        d = build_lookup(p)
        label = p.get("period") or p.get("label") or p.get("期间") or f"第{i + 1}期"
        periods_r.append({"label": str(label), "d": d, "r": compute_period(d)})

    md = render(data, periods_r)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"✅ 已写入 {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
