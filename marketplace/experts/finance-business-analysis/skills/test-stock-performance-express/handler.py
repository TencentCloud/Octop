#!/usr/bin/env python3
"""
A 股业绩快报查询处理器。

调用 market.ft.tech API，获取单只股票所有报告期的业绩快报数据，
并以 Markdown 表格形式输出到 stdout。

用法：
    python handler.py <股票代码>           # 命令行参数
    echo "603323.SH" | python handler.py   # stdin 管道

环境变量（可选，会覆盖 skill.json 中的 config 默认值）：
    BASE_URL   API 服务地址，默认 https://market.ft.tech
    PAGE_SIZE  每页条数，默认 50
"""

import sys
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error

# ──────────────────────────────────────────────
# 配置：优先读环境变量，否则使用默认值
# ──────────────────────────────────────────────
BASE_URL = os.environ.get("BASE_URL", "https://market.ft.tech").rstrip("/")

# PAGE_SIZE 来自环境变量时做类型校验，避免非数字引发下游异常
_page_size_env = os.environ.get("PAGE_SIZE", "50")
if _page_size_env.isdigit() and int(_page_size_env) > 0:
    PAGE_SIZE = int(_page_size_env)
else:
    PAGE_SIZE = 50

# 股票代码格式：6 位数字 + 市场后缀（SH / SZ / BJ）
STOCK_CODE_RE = re.compile(r"\b(\d{6}\.(SH|SZ|BJ))\b", re.IGNORECASE)

# 报告类型兜底映射（API 返回 report_type_cn 时优先使用接口值）
REPORT_TYPE_ZH = {
    "q1": "一季报",
    "q2": "半年报",
    "q3": "三季报",
    "annual": "年报",
}

# 请求超时（秒）
REQUEST_TIMEOUT = 10


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def validate_stock_code(code: str) -> bool:
    """校验股票代码是否符合「6位数字.SH/SZ/BJ」格式。"""
    return bool(re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code, re.IGNORECASE))


def format_amount(value) -> str:
    """
    将元为单位的数值格式化为亿元或万元字符串，提升可读性。
    当 value 为 None 或无法转换时返回 "N/A"。
    除法说明：除数 1e8 / 1e4 均为正常量，不可能为零。
    """
    if value is None:
        return "N/A"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "N/A"

    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f} 亿元"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f} 万元"
    return f"{v:.2f} 元"


def format_yoy(value) -> str:
    """
    将同比增长率格式化为百分比字符串。
    API 返回值已是百分比数值（如 -14.4063 表示 -14.41%），直接保留两位小数展示，
    不再乘以 100。
    当 value 为 None 或无法转换时返回 "N/A"。
    """
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return "N/A"


def format_float(value, suffix: str = "") -> str:
    """格式化浮点数，无效值返回 N/A。"""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.4f}{suffix}"
    except (ValueError, TypeError):
        return "N/A"


# ──────────────────────────────────────────────
# API 请求
# ──────────────────────────────────────────────

def fetch_performance(stock_code: str, page: int = 1) -> dict:
    """
    请求业绩快报接口，返回原始 JSON 字典。

    Args:
        stock_code: 股票代码，如 603323.SH
        page:       页码，默认 1

    Returns:
        解析后的 JSON 字典，结构为 {"items": [...], "total_pages": N, "total_items": N}

    Raises:
        urllib.error.URLError: 网络连接失败
        urllib.error.HTTPError: HTTP 状态码异常（4xx / 5xx）
        json.JSONDecodeError:  响应体不是合法 JSON
        ValueError:            响应结构校验失败
    """
    params = urllib.parse.urlencode({
        "stock_code": stock_code,
        "page": page,
        "page_size": PAGE_SIZE,
    })
    url = f"{BASE_URL}/data/api/v1/market/data/finance/stock-performance-express?{params}"

    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "openclaw-skill/1.0"},
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        # HTTPError 会在 urlopen 时抛出，此处只处理读取失败
        raw = resp.read().decode("utf-8")

    data = json.loads(raw)

    # 校验响应结构：items 字段必须存在且为列表
    if not isinstance(data.get("items"), list):
        raise ValueError(f"API 响应格式异常：缺少 items 字段，实际内容：{raw[:200]}")

    return data


# ──────────────────────────────────────────────
# 渲染
# ──────────────────────────────────────────────

def render_table(items: list) -> str:
    """
    将业绩快报列表渲染为 Markdown 表格。
    表格列：报告期 | 营业总收入 | 收入同比 | 净利润 | 利润同比 | EPS | ROE | 每股净资产 | 发布日期
    """
    if not items:
        return "_暂无数据_"

    header = (
        "| 报告期 | 营业总收入 | 收入同比 | 净利润 | 利润同比 | "
        "EPS(元/股) | ROE(%) | 每股净资产 | 发布日期 |"
    )
    separator = "|--------|-----------|---------|--------|---------|-----------|--------|----------|---------|"
    rows = [header, separator]

    for item in items:
        year = item.get("year", "")
        # 优先使用接口返回的中文报告类型，兜底用本地映射
        rtype_cn = item.get("report_type_cn") or REPORT_TYPE_ZH.get(
            item.get("report_type", ""), "未知"
        )
        period = f"{year} {rtype_cn}"

        revenue = format_amount(item.get("total_revenue"))
        revenue_yoy = format_yoy(item.get("total_revenue_yoy"))
        profit = format_amount(item.get("net_profit"))
        profit_yoy = format_yoy(item.get("net_profit_yoy"))
        eps = format_float(item.get("eps"))
        roe = format_float(item.get("roe"), suffix="%")
        nav_ps = format_float(item.get("sh_netassets_ps"))
        publish = item.get("publish_date") or "N/A"

        rows.append(
            f"| {period} | {revenue} | {revenue_yoy} | {profit} | {profit_yoy} | "
            f"{eps} | {roe} | {nav_ps} | {publish} |"
        )

    return "\n".join(rows)


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def resolve_stock_code() -> str:
    """
    从命令行参数或 stdin 中解析股票代码。
    优先级：命令行参数 > stdin 全文搜索。
    若均找不到合法代码，打印错误并退出。
    """
    # 1. 命令行参数
    if len(sys.argv) >= 2:
        candidate = sys.argv[1].strip().upper()
        if validate_stock_code(candidate):
            return candidate
        # 参数不合法时给出明确提示，而非静默进入 stdin 逻辑
        print(f"错误：命令行参数 '{sys.argv[1]}' 不是合法的股票代码。")
        print("格式：6 位数字 + 市场后缀，如 603323.SH、000001.SZ、832566.BJ")
        sys.exit(1)

    # 2. stdin（OpenClaw shell 模式下传入用户原始输入）
    raw = sys.stdin.read().strip()
    match = STOCK_CODE_RE.search(raw.upper())
    if match:
        return match.group(1).upper()

    print("错误：未能从输入中识别股票代码。")
    print("格式：6 位数字 + 市场后缀，如 603323.SH、000001.SZ、832566.BJ")
    sys.exit(1)


def main() -> None:
    """主流程：解析股票代码 → 请求 API → 校验数据 → 输出表格。"""
    stock_code = resolve_stock_code()

    # 请求数据，区分网络错误和数据错误分别提示
    try:
        data = fetch_performance(stock_code)
    except urllib.error.HTTPError as e:
        print(f"错误：API 返回 HTTP {e.code}，请确认股票代码是否正确。")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"错误：网络请求失败 —— {e.reason}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误：API 响应不是合法 JSON —— {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"错误：{e}")
        sys.exit(1)

    items = data["items"]  # fetch_performance 已校验 items 存在且为 list

    if not items:
        print(f"{stock_code} 暂无业绩快报数据。")
        sys.exit(0)

    # 从第一条记录取股票名称（API 保证同一 stock_code 下名称一致）
    stock_name = items[0].get("stock_name") or stock_code
    total_items = data.get("total_items", len(items))
    total_pages = data.get("total_pages", 1)

    # 输出 Markdown 格式结果
    print(f"## {stock_name}（{stock_code}）业绩快报\n")
    print(f"> 共 {total_items} 条记录，当前第 1/{total_pages} 页\n")
    print(render_table(items))


if __name__ == "__main__":
    main()
