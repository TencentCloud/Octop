#!/usr/bin/env python3
"""
1688 商品搜索 — search_products.py
用法: python3 search_products.py <关键词> [--page N] [--min-price X] [--max-price Y] [--factory-only]

依赖：python3, requests（标准库 + pip install requests）
网络：仅访问 *.1688.com 域名
凭证：无需，可选配置 ALI_COOKIE 环境变量增强访问能力
"""

import sys
import json
import re
import os
import urllib.parse
import requests
from typing import Optional

# 可选 Cookie（从环境变量读取，非必需）
_OPTIONAL_COOKIE = os.environ.get("ALI_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.1688.com/",
}
if _OPTIONAL_COOKIE:
    HEADERS["Cookie"] = _OPTIONAL_COOKIE

def search_products(keyword: str, page: int = 1, min_price: Optional[float] = None,
                     max_price: Optional[float] = None, factory_only: bool = False,
                     page_size: int = 20) -> dict:
    """
    搜索 1688 商品，返回结构化 JSON 数据。
    """
    params = {
        "keywords": keyword,
        "beginPage": page,
        "pageSize": page_size,
        "qrquick": "search",
        "exposureType": "normal",
        "n": "y",
        "topTab": "供给",
        "s Suggest Input": keyword,
    }

    url = "https://search.1688.com/service/json.htm"

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.encoding = "gbk" if resp.apparent_encoding in ("gbk", "gb2312", "windows-1252") else "utf-8"
    except Exception as e:
        return {"error": str(e), "success": False}

    text = resp.text

    # 策略1: 直接 JSON
    try:
        raw = resp.json()
        return _parse_json_response(raw, keyword)
    except Exception:
        pass

    # 策略2: HTML 内嵌 JSON
    try:
        raw = _extract_json_from_html(text)
        return _parse_json_response(raw, keyword)
    except Exception:
        pass

    return {"error": "无法解析响应", "raw_snippet": text[:500], "success": False}


def _extract_json_from_html(html: str) -> dict:
    """从 HTML 中提取 embeded JSON 数据"""
    # 尝试找 <script>window.__INIT_STATE__ = {...}</script>
    patterns = [
        r'window\.__INIT_STATE__\s*=\s*(\{.*?\});',
        r'"moduleList"\s*:\s*(\[.*?\])',
        r'"resultList"\s*:\s*(\[.*?\])',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                continue
    raise ValueError("No JSON found in HTML")


def _parse_json_response(data: dict, keyword: str) -> dict:
    """解析 1688 JSON 响应，提取商品列表"""
    items = []
    # 遍历多种可能的数据路径
    content = data
    for path in ["data.moduleList", "data.resultList", "resultList", "data.modules"]:
        try:
            for key in path.split(".")[1:]:
                content = content[key]
            break
        except Exception:
            content = data

    if isinstance(content, list):
        raw_items = content
    else:
        raw_items = []

    for item in raw_items[:20]:
        if not isinstance(item, dict):
            continue
        items.append({
            "productId": item.get("id") or item.get("itemId") or item.get("offerId", ""),
            "title": _clean_html(item.get("title", "") or item.get("subject", "")),
            "price": _clean_price(item.get("price", "") or item.get("priceString", "")),
            "最低MOQ": item.get("最小起订量") or item.get("minOrder", "") or "未标注",
            "30天成交": item.get("soldCount30") or item.get("soldInfo", {}).get("soldCount30", "未披露"),
            "诚信通年限": item.get("creditYear", "未标注"),
            "旺旺在线": item.get("online", "") or item.get("w_status", ""),
            "发货地": _parse_address(item),
            "公司名": _clean_html(item.get("companyName", "") or item.get("company", "") or ""),
            "旺铺链接": item.get("w_homeUrl") or item.get("wapHomeUrl") or "",
            "图片链接": item.get("imageUrl", "") or item.get("pic_url", "") or "",
        })

    # 汇总统计
    prices = [float(it["price"]) for it in items if it["price"]]
    stats = {
        "搜索关键词": keyword,
        "商品数量": len(items),
        "价格区间": f"¥{min(prices):.2f} - ¥{max(prices):.2f}" if prices else "未获取到价格",
        "平均价格": f"¥{sum(prices)/len(prices):.2f}" if prices else "未获取到价格",
        "数据来源": "1688 搜索接口",
    }
    return {"success": True, "items": items, "stats": stats, "raw_keys": list(data.keys()) if isinstance(data, dict) else []}


def _clean_html(text: str) -> str:
    """去除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _clean_price(text) -> str:
    """提取价格数字"""
    if not text:
        return ""
    text = str(text)
    m = re.search(r"[\d.]+", text)
    return m.group() if m else text


def _parse_address(item: dict) -> str:
    """解析发货地"""
    loc = item.get("location", {}) or {}
    if isinstance(loc, dict):
        return f"{loc.get('province','')}{loc.get('city','')}{loc.get('area','')}".strip()
    return str(item.get("address", item.get("province", "")))


# --- CLI ---
if __name__ == "__main__":
    args = sys.argv[1:]
    kw = ""
    page = 1
    factory_only = False
    min_p = None
    max_p = None

    i = 0
    while i < len(args):
        if args[i] == "--page" and i+1 < len(args):
            page = int(args[i+1]); i += 2
        elif args[i] == "--min-price" and i+1 < len(args):
            min_p = float(args[i+1]); i += 2
        elif args[i] == "--max-price" and i+1 < len(args):
            max_p = float(args[i+1]); i += 2
        elif args[i] == "--factory-only":
            factory_only = True; i += 1
        else:
            kw = args[i]; i += 1

    if not kw:
        print("用法: python3 search_products.py <关键词> [--page N] [--min-price X] [--max-price Y] [--factory-only]")
        sys.exit(1)

    result = search_products(kw, page, min_p, max_p, factory_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
