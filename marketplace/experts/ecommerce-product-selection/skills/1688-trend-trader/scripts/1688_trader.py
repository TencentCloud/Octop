#!/usr/bin/env python3
"""
1688 爆款操盘手 — 主入口脚本

【运行环境】
  - Python 3.7+
  - requests 库（pip install requests）
  - 网络：访问 *.1688.com（可选 ALI_APP_KEY/ALI_APP_SECRET 增强）

【凭证说明】
  - 基础功能：无需任何凭证
  - 增强功能（可选）：配置 ALI_APP_KEY / ALI_APP_SECRET 环境变量
    获取方式：https://open.1688.com/ → 创建应用

用法:
  python3 1688_trader.py search <关键词>          # 搜索商品
  python3 1688_trader.py factory <关键词>         # 搜索源头工厂
  python3 1688_trader.py detail <商品ID>           # 商品详情
  python3 1688_trader.py profit <进价> <售价>     # 利润计算
  python3 1688_trader.py full <关键词>            # 全链路：选品+找商+询盘

示例:
  python3 1688_trader.py search 宠物智能喂食器
  python3 1688_trader.py factory 智能喂食器 --province 浙江
  python3 1688_trader.py detail 628734562812
  python3 1688_trader.py profit 150 89.9 --platform amazon --weight-g 1200 --units 100
  python3 1688_trader.py full 户外储能电源
"""

import sys
import json
import re
import os

# 添加 scripts 同级路径以便导入 local 模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from search_products import search_products
from search_factories import search_factories
from product_detail import get_product_detail
from calc_profit import calc_profit as do_calc, PLATFORM_PARAMS, parse_args as calc_parse_args

# ANSI 颜色输出
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def c(text, color=REST):
    return f"{color}{text}{RESET}"


R = RESET; G = GREEN; Y = YELLOW; R_ = RED; B = BLUE; BB = BOLD


def cmd_search(args: list):
    """1688 商品搜索"""
    kw = " ".join(args)
    if not kw:
        print(f"{R_}[用法] {B}search <关键词> [--page N] [--min-price X] [--max-price Y] [--factory-only]")
        return

    page = 1
    factory_only = False
    extra = args.copy()
    if "--page" in extra:
        idx = extra.index("--page")
        page = int(extra[idx+1]); extra = extra[:idx]
    if "--factory-only" in extra:
        factory_only = True; extra.remove("--factory-only")
    kw = " ".join(extra) or kw

    print(f"{BB}🔍 正在搜索 1688: {Y}{kw}{R}")
    if factory_only:
        result = search_factories(kw, page=page)
    else:
        result = search_products(kw, page=page)

    if not result.get("success"):
        print(f"{R_}❌ 错误: {result.get('error','未知错误')}")
        if "raw_snippet" in result:
            print(f"   原始响应片段: {result['raw_snippet'][:200]}")
        return

    items = result.get("items", [])
    stats = result.get("stats", {})
    print(f"\n{BB}📊 搜索结果 — {G}{stats.get('商品数量', len(items))} 件商品{R}")
    print(f"   价格区间: {Y}{stats.get('价格区间', 'N/A')}{R}")
    print(f"   平均价格: {Y}{stats.get('平均价格', 'N/A')}{R}")
    print()

    for i, item in enumerate(items[:20], 1):
        price = item.get("price", "—")
        moq = item.get("最低MOQ", "—")
        sold = item.get("30天成交", "—")
        credit = item.get("诚信通年限", "—")
        addr = item.get("发货地", "—")
        company = item.get("公司名", "—")

        print(f"  {B}{i:02d}. {item.get('title','—')[:45]}{R}")
        if price: print(f"      💰 价格: {Y}¥{price}{R}  |  MOQ: {moq}  |  30天成交: {sold}")
        if addr: print(f"      📍 {addr}  |  诚信通: {credit}年  |  {company}")
        print()


def cmd_factory(args: list):
    """1688 工厂搜索"""
    kw = " ".join(args)
    if not kw:
        print(f"{R_}[用法] factory <关键词> [--province 省名]")
        return

    province = ""
    if "--province" in args:
        idx = args.index("--province")
        province = args[idx+1] if idx+1 < len(args) else ""
        kw = " ".join(args[:idx]) or kw

    print(f"{BB}🏭 正在搜索 1688 源头工厂: {Y}{kw}{R}" + (f" ({province})" if province else ""))
    result = search_factories(kw, province=province)

    if not result.get("success"):
        print(f"{R_}❌ 错误: {result.get('error','未知错误')}")
        return

    items = result.get("items", [])
    stats = result.get("stats", {})
    print(f"\n{BB}📊 搜索结果 — {G}{stats.get('工厂数量', len(items))} 家工厂{R}")
    print(f"   平均成交额: {Y}{stats.get('平均成交额（万）','N/A')}{R}\n")

    for i, f in enumerate(items[:10], 1):
        tags = f.get("工厂标签","—")
        credit = f.get("诚信通年限","—")
        amount = f.get("近90天成交额","—")
        sold = f.get("30天成交","—")
        rep = f.get("复购率","—")
        wm = f.get("旺旺在线","—")
        addr = f.get("发货地","—")

        print(f"  {B}{i:02d}. {f.get('公司名称','—')[:40]}{R}")
        print(f"      🏷️ {tags or '—'}  |  诚信通: {Y}{credit}年{R}  |  {wm}")
        print(f"      💰 近90天: {Y}{amount}{R}  |  复购率: {rep or '—'}  |  30天: {sold}")
        print(f"      📍 {addr}")
        if f.get("旺铺链接"):
            print(f"      🔗 {f['旺铺链接']}")
        print()


def cmd_detail(args: list):
    """商品详情"""
    if not args:
        print(f"{R_}[用法] detail <商品ID或1688链接>")
        return

    pid = args[0]
    m = re.search(r"(?:offer/|id=)(\d+)", " ".join(args))
    if m: pid = m.group(1)

    print(f"{BB}📦 正在获取商品详情: {Y}{pid}{R}")
    result = get_product_detail(pid)

    if not result.get("success"):
        print(f"{R_}❌ 错误: {result.get('error')}")
        return

    co = result.get("公司信息", {})
    print(f"\n{BB}📌 {result.get('商品标题','—')}{R}")
    print(f"   🔗 {result.get('商品链接','—')}")
    print()
    print(f"{BB}🏭 供应商信息{R}")
    print(f"   公司名: {co.get('公司名称','—')}")
    print(f"   诚信通: {Y}{co.get('诚信通年限','—')}年{R}  |  诚信等级: {co.get('诚信等级','—')}")
    print(f"   工厂标签: {co.get('工厂标签','—')}")
    print(f"   近90天成交额: {Y}{co.get('近90天成交额','—')}{R}  |  发货地: {co.get('发货地','—')}")

    print()
    print(f"{BB}💰 价格阶梯{R}")
    for p in result.get("价格阶梯", [])[:5]:
        print(f"   {p.get('数量区间','—'):20s}  →  ¥{p.get('单价','—')}")

    print()
    print(f"{BB}📊 交易数据{R}")
    print(f"   MOQ: {Y}{result.get('MOQ','—')}{R}  |  30天成交: {result.get('30天成交','—')}  |  180天成交: {result.get('180天成交','—')}")

    certs = result.get("认证资质", [])
    if certs and certs != ["需进入详情页查看"]:
        print()
        print(f"{BB}✅ 认证资质{R}")
        for c in certs: print(f"   • {c}")


def cmd_profit(args: list):
    """利润计算"""
    if len(args) < 2:
        print(f"{R_}[用法] profit <进货价(元)> <售价(美元)> [--platform amazon|tiktok|shopify|temu]")
        print(f"       [--weight-g X] [--freight-kg Y] [--units N] [--currency USD|EUR|GBP]")
        return

    # 用 argparse 解析利润参数
    raw = [args[0], args[1]] + args[2:]
    sys.argv = ["calc"] + raw
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("cost_price", type=float)
    p.add_argument("sell_price", type=float)
    p.add_argument("--currency", default="USD")
    p.add_argument("--platform", default="amazon")
    p.add_argument("--weight-g", type=float, default=500.0)
    p.add_argument("--freight-kg", type=float, default=5.0)
    p.add_argument("--units", type=int, default=100)
    p.add_argument("--exchange-rate", type=float, default=7.20)
    p.add_argument("--exchange-eur", type=float, default=7.80)
    p.add_argument("--exchange-gbp", type=float, default=9.10)
    parsed = p.parse_args(raw)

    result = do_calc(parsed)
    if not result.get("success"):
        print(f"{R_}❌ 错误"); return

    bd = result["cost_breakdown_cny"]
    sym = "$" if result["currency"] != "CNY" else "¥"

    print(f"\n{BB}💰 利润分析 — {result['platform'].upper()} | {result['currency']}{R}")
    print(f"{BB}┌{'─'*42}┐")
    print(f"│ 进货成本合计:                        {R}¥{result['total_cost_cny']:.2f}{BB}  ({result['platform']}平台，首批{result['params']['首批数量']}个)")
    print(f"│{R}")
    print(f"│  进货价:     ¥{bd['进货价']:.2f}  |  头程:  ¥{bd['头程运费']:.2f}")
    print(f"│  平台佣金:   ¥{bd['平台佣金']:.2f}  |  推广:  ¥{bd['推广费']:.2f}")
    print(f"│  尾程配送:   ¥{bd['尾程配送']:.2f}  |  损耗:  ¥{bd['退货损耗']:.2f}")
    print(f"│  汇损:       ¥{bd['汇损']:.2f}")
    print(f"│{R}")
    print(f"│  合计成本:   ¥{bd['合计成本']:.2f} / 件")
    print(f"│{B}")
    print(f"│  折合售价:   ¥{result['sell_price_cny']:.2f} (汇率{result['exchange_rate']})")
    print(f"│  单品毛利:   {G}{result['unit_margin_pct']:.2f}%{R}  |  单品利润: {G}¥{result['unit_profit_cny']:.2f}{R}")
    print(f"│  首批总利润: {G}{result['total_profit_cny']:.2f}{R} 元")
    print(f"│{R}")
    print(f"│  健康状态:   {result['health_check']['status']}  {result['health_check']['建议']}")
    print(f"{BB}└{'─'*42}┘{R}")


def cmd_full(args: list):
    """全链路选品+找商+利润分析"""
    kw = " ".join(args)
    if not kw:
        print(f"{R_}[用法] full <关键词（产品品类）>")
        return

    print(f"\n{B}{'═'*55}")
    print(f"  1688 爆款操盘手 — 全链路分析")
    print(f"  产品: {Y}{kw}{B}")
    print(f"{'═'*55}{R}\n")

    # Step 1: 搜索商品
    print(f"{BB}[1/3] 🔍 搜索 1688 市场数据...{R}")
    prod_result = search_products(kw, page=1)
    items = prod_result.get("items", []) if prod_result.get("success") else []
    print(f"   找到 {Y}{len(items)}{R} 件相关商品\n")

    # Step 2: 搜索工厂
    print(f"{BB}[2/3] 🏭 穿透搜索源头工厂...{R}")
    fac_result = search_factories(kw, page=1)
    factories = fac_result.get("items", []) if fac_result.get("success") else []
    print(f"   找到 {Y}{len(factories)}{R} 家源头工厂\n")

    # Step 3: 推荐 Top 产品 & 工厂
    if items:
        top = items[0]
        print(f"{BB}📦 推荐商品 (Top 1){R}")
        print(f"   {top.get('title','—')[:50]}")
        print(f"   💰 ¥{top.get('price','—')}  |  MOQ: {top.get('最低MOQ','—')}")
        print(f"   📊 30天成交: {top.get('30天成交','—')}  |  {top.get('发货地','—')}\n")

    if factories:
        top_f = factories[0]
        print(f"{BB}🏭 推荐工厂 (Top 1){R}")
        print(f"   {top_f.get('公司名称','—')[:45]}")
        print(f"   诚信通: {Y}{top_f.get('诚信通年限','—')}年{R}  |  近90天: {Y}{top_f.get('近90天成交额','—')}{R}")
        print(f"   📍 {top_f.get('发货地','—')}  |  {top_f.get('旺旺在线','—')}\n")
        if top_f.get("旺铺链接"):
            print(f"   🔗 {top_f['旺铺链接']}\n")

    # Step 4: 利润计算（用商品价格估算）
    if items and factories:
        price = items[0].get("price", "150")
        try: price = float(price)
        except: price = 150.0

        print(f"{BB}[3/3] 💰 利润预估 (进价¥{price:.0f} → 售价$89.99){R}")
        print(f"   （以下为Amazon FBA模式参考）\n")

        raw = [str(price), "89.99", "--platform", "amazon", "--units", "100"]
        sys.argv = ["calc"] + raw
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("cost_price", type=float)
        p.add_argument("sell_price", type=float)
        p.add_argument("--currency", default="USD")
        p.add_argument("--platform", default="amazon")
        p.add_argument("--weight-g", type=float, default=500.0)
        p.add_argument("--freight-kg", type=float, default=5.0)
        p.add_argument("--units", type=int, default=100)
        p.add_argument("--exchange-rate", type=float, default=7.20)
        p.add_argument("--exchange-eur", type=float, default=7.80)
        p.add_argument("--exchange-gbp", type=float, default=9.10)
        parsed = p.parse_args(raw)
        result = do_calc(parsed)
        bd = result["cost_breakdown_cny"]
        print(f"   ┌─────────────────────────────────────────────┐")
        print(f"   │ 进货成本合计: ¥{result['total_cost_cny']:.2f}  |  首批100个  │")
        print(f"   │ 折合售价: ¥{result['sell_price_cny']:.2f}  |  合计成本/件: ¥{bd['合计成本']:.2f}  │")
        print(f"   │ 单品毛利: {G}{result['unit_margin_pct']:.2f}%{R}  |  单品利润: {G}¥{result['unit_profit_cny']:.2f}{R}   │")
        print(f"   │ 首批100个总利润: {G}¥{result['total_profit_cny']:.2f}{R}             │")
        print(f"   │ 健康状态: {result['health_check']['status']}                      │")
        print(f"   └─────────────────────────────────────────────┘")

    print(f"\n{B}{'═'*55}{R}")
    print(f"  分析完毕。如需询盘话术或详细报告，请告诉我具体需求。")


# --- 命令行路由 ---
COMMANDS = {
    "search":    (cmd_search,    "搜索 1688 商品"),
    "factory":   (cmd_factory,   "搜索 1688 源头工厂"),
    "detail":    (cmd_detail,    "获取商品详情"),
    "profit":    (cmd_profit,    "利润计算"),
    "full":      (cmd_full,      "全链路分析（选品+工厂+利润）"),
    "--help":    (None,          "显示帮助"),
    "-h":        (None,          "显示帮助"),
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print(f"""
{B}╔═══════════════════════════════════════════════════╗
║        1688 爆款操盘手 CLI  (v1.0)                 ║
╠═══════════════════════════════════════════════════╣
║  search   <关键词>      搜索 1688 商品               ║
║  factory  <关键词>      搜索源头工厂                  ║
║  detail   <商品ID>      获取商品详情                  ║
║  profit   <进价> <售价> 利润计算                     ║
║  full     <关键词>      全链路分析                    ║
╠═══════════════════════════════════════════════════╣
║  示例:                                               ║
║  python3 1688_trader.py search 宠物喂食器            ║
║  python3 1688_trader.py factory 智能喂食器 --province 浙江 ║
║  python3 1688_trader.py detail 628734562812          ║
║  python3 1688_trader.py profit 150 89.9 --platform amazon --units 100 ║
║  python3 1688_trader.py full 户外储能电源           ║
╚═══════════════════════════════════════════════════╝{R}
        """)
        return

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"{R_}❌ 未知命令: {cmd}  （可用: {', '.join(COMMANDS)}){R}")
        return

    fn, desc = COMMANDS[cmd]
    args = sys.argv[2:]
    fn(args)


if __name__ == "__main__":
    main()
