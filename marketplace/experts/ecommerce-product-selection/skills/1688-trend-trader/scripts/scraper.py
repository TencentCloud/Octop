#!/usr/bin/env python3
"""
1688 通用抓取器 — scraper.py
直接抓取 1688 页面 HTML，从页面 DOM / script 内嵌 JSON 中提取商品和工厂数据。
"""

import os
import sys
import json
import re
import time
import requests
from typing import Optional

# Cookie 可选配置（从环境变量读取）
_OPTIONAL_COOKIE = os.environ.get("ALI_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
if _OPTIONAL_COOKIE:
    HEADERS["Cookie"] = _OPTIONAL_COOKIE

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url: str, encoding: str = "utf-8", timeout: int = 20) -> Optional[str]:
    """抓取页面，返回 HTML 文本"""
    try:
        resp = SESSION.get(url, timeout=timeout)
        # 1688 用 GBK 编码
        if resp.apparent_encoding in ("gbk", "gb2312", "gb18030", "windows-1252"):
            encoding = "gbk"
        resp.encoding = encoding
        return resp.text
    except Exception as e:
        return None


def extract_json_field(html: str, patterns: list) -> Optional[dict]:
    """从 HTML 中用多个正则匹配内嵌 JSON"""
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                return data
            except Exception:
                pass
    return None


def search_products(keyword: str, page: int = 1) -> dict:
    """抓取 1688 商品搜索结果"""
    kw_encoded = requests.utils.quote(keyword)
    # 搜索结果页
    url = f"https://s.1688.com/youzhan/search/searchOffer.json?keywords={kw_encoded}&beginPage={page}&pageSize=20"
    html = fetch(url, encoding="gbk")
    if not html:
        # 兜底：用旧版搜索
        url2 = f"https://search.1688.com/service/json.htm?keywords={kw_encoded}&beginPage={page}&pageSize=20&qrquick=search"
        html = fetch(url2, encoding="gbk")

    if not html:
        return {"success": False, "error": "网络请求失败"}

    # 尝试直接 JSON
    try:
        data = json.loads(html)
        return _parse_product_list(data, keyword)
    except Exception:
        pass

    # 从 HTML 提取内嵌 JSON
    patterns = [
        r'window\.__INIT_STATE__\s*=\s*(\{.{5000,})\s*;</script>',
        r'"moduleList"\s*:\s*(\[.*?\])\s*,',
        r'var\s+offerList\s*=\s*(\[.*?\])\s*;',
        r'"resultList"\s*:\s*(\[.*?\])',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                return _parse_product_list(data, keyword)
            except Exception:
                pass

    # 兜底：正则提取商品列表
    items = _regex_extract_products(html)
    if items:
        return _format_product_result(items, keyword)

    return {"success": False, "error": "无法解析页面", "snippet": html[:300]}


def _parse_product_list(data, keyword: str) -> dict:
    """通用 JSON 数据解析"""
    items = []

    def find_items(obj):
        if isinstance(obj, list):
            for x in obj:
                find_items(x)
        elif isinstance(obj, dict):
            # 命中含商品字段的列表
            if "title" in obj or "subject" in obj:
                if any(k in obj for k in ["price", "unitPrice", "最小起订量"]):
                    items.append(obj)
            for v in obj.values():
                find_items(v)

    find_items(data)

    formatted = []
    for item in items[:20]:
        formatted.append({
            "productId": item.get("id") or item.get("offerId") or item.get("itemId", ""),
            "title": _strip(item.get("title", item.get("subject", ""))),
            "price": _price(item.get("price", item.get("unitPrice", ""))),
            "最低MOQ": item.get("最小起订量", item.get("minOrder", "未标注")),
            "30天成交": item.get("soldCount30", "未披露"),
            "诚信通年限": item.get("creditYear", "未标注"),
            "旺旺在线": "✅" if item.get("online") or item.get("w_status") == "1" else "❌",
            "发货地": _addr(item.get("location", {})),
            "公司名": _strip(item.get("companyName", item.get("company", ""))),
            "图片": item.get("imageUrl", "") or item.get("pic_url", ""),
            "链接": f"https://detail.1688.com/offer/{item.get('offerId', item.get('id',''))}.html",
        })

    prices = [float(i["price"]) for i in formatted if i["price"]]
    return {
        "success": True,
        "items": formatted,
        "stats": {
            "关键词": keyword,
            "数量": len(formatted),
            "价格区间": f"¥{min(prices):.2f}~¥{max(prices):.2f}" if prices else "未获取",
            "平均价": f"¥{sum(prices)/len(prices):.2f}" if prices else "未获取",
        }
    }


def _regex_extract_products(html: str) -> list:
    """正则直接提取商品卡片数据"""
    items = []

    # 匹配价格
    price_pat = re.compile(r'"price"\s*:\s*"([^"]+)"')
    title_pat = re.compile(r'"title"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"')
    id_pat = re.compile(r'"offerId"\s*:\s*"?(\d+)"?')
    moq_pat = re.compile(r'"最小起订量"\s*:\s*"([^"]+)"')
    sold_pat = re.compile(r'"soldCount30"\s*:\s*"([^"]+)"')
    addr_pat = re.compile(r'"location"\s*:\s*"\s*([^"]{2,20})"')
    co_pat = re.compile(r'"companyName"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"')

    # 逐行扫描（以 offerId 为锚点分段）
    segments = re.split(r'(?={"offerId")', html)
    for seg in segments[1:]:
        item = {}
        m_id = id_pat.search(seg)
        if not m_id:
            m_id = re.search(r'"id"\s*:\s*"?(\d+)"?', seg)
        if m_id:
            item["offerId"] = m_id.group(1)
        else:
            continue

        m_price = price_pat.search(seg)
        if m_price: item["price"] = m_price.group(1)

        m_title = title_pat.search(seg)
        if m_title: item["title"] = m_title.group(1)

        m_moq = moq_pat.search(seg)
        if m_moq: item["最小起订量"] = m_moq.group(1)

        m_sold = sold_pat.search(seg)
        if m_sold: item["soldCount30"] = m_sold.group(1)

        m_addr = addr_pat.search(seg)
        if m_addr: item["location"] = m_addr.group(1)

        m_co = co_pat.search(seg)
        if m_co: item["companyName"] = m_co.group(1)

        if item:
            items.append(item)

    return items


def _format_product_result(items: list, keyword: str) -> dict:
    formatted = []
    for item in items[:20]:
        formatted.append({
            "productId": item.get("offerId", item.get("id", "")),
            "title": _strip(item.get("title", "")),
            "price": _price(item.get("price", "")),
            "最低MOQ": item.get("最小起订量", "未标注"),
            "30天成交": item.get("soldCount30", "未披露"),
            "诚信通年限": item.get("creditYear", "未标注"),
            "旺旺在线": "✅",
            "发货地": item.get("location", "未标注"),
            "公司名": _strip(item.get("companyName", "")),
            "图片": item.get("imageUrl", ""),
            "链接": f"https://detail.1688.com/offer/{item.get('offerId','')}.html",
        })
    prices = [float(i["price"]) for i in formatted if i["price"]]
    return {
        "success": True,
        "items": formatted,
        "stats": {
            "关键词": keyword,
            "数量": len(formatted),
            "价格区间": f"¥{min(prices):.2f}~¥{max(prices):.2f}" if prices else "未获取",
            "平均价": f"¥{sum(prices)/len(prices):.2f}" if prices else "未获取",
        }
    }


def search_factories(keyword: str, province: str = "", page: int = 1) -> dict:
    """抓取 1688 工厂搜索结果"""
    kw_encoded = requests.utils.quote(keyword)
    province_encoded = requests.utils.quote(province) if province else ""

    # 工厂频道搜索
    url = f"https://s.1688.com/youzhan/search/searchFactory.json?keywords={kw_encoded}&beginPage={page}&pageSize=20"
    if province_encoded:
        url += f"&province={province_encoded}"

    html = fetch(url, encoding="gbk")
    if not html:
        url2 = f"https://search.1688.com/service/json.htm?keywords={kw_encoded}&beginPage={page}&pageSize=20&topTab=工厂&qrquick=factory"
        html = fetch(url2, encoding="gbk")

    if not html:
        return {"success": False, "error": "网络请求失败"}

    # 直接 JSON
    try:
        data = json.loads(html)
        return _parse_factory_list(data, keyword)
    except Exception:
        pass

    # HTML 内嵌 JSON
    patterns = [
        r'window\.__INIT_STATE__\s*=\s*(\{.{5000,})\s*;</script>',
        r'"factoryList"\s*:\s*(\[.*?\])\s*[,}]',
        r'"companyList"\s*:\s*(\[.*?\])',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                return _parse_factory_list(data, keyword)
            except Exception:
                pass

    # 正则提取工厂
    items = _regex_extract_factories(html)
    if items:
        return _format_factory_result(items, keyword)

    return {"success": False, "error": "无法解析页面", "snippet": html[:300]}


def _parse_factory_list(data, keyword: str) -> dict:
    items = []

    def find(obj):
        if isinstance(obj, list):
            for x in obj:
                find(x)
        elif isinstance(obj, dict):
            if any(k in obj for k in ["companyName", "memberId", "factoryType"]):
                if "companyName" in obj or "memberId" in obj:
                    items.append(obj)
            for v in obj.values():
                find(v)

    find(data)
    formatted = []
    for f in items[:10]:
        tags = _strip(" ".join(str(t) for t in f.get("keyWords", []) or f.get("tags", []) or []))
        amount = f.get("AmountInfo", f.get("soldAmount", ""))
        if isinstance(amount, dict):
            amount = amount.get("amount90Day", "")
        formatted.append({
            "companyId": f.get("companyId", f.get("memberId", "")),
            "公司名称": _strip(f.get("companyName", f.get("subject", ""))),
            "工厂标签": tags or "源头工厂",
            "诚信通年限": f.get("creditYear", "未标注"),
            "近90天成交额": _amount(amount),
            "30天成交": f.get("soldCount30", "未披露"),
            "复购率": f.get("repeatCustomerRatio", ""),
            "旺旺在线": "✅" if f.get("online") else "❌",
            "发货地": _addr(f.get("location", {})),
            "旺铺链接": f.get("w_homeUrl", ""),
        })
    amounts = []
    for f in formatted:
        m = re.search(r"[\d.]+", str(f.get("近90天成交额", "")))
        if m: amounts.append(float(m.group()))
    avg = f"¥{sum(amounts)/len(amounts):.1f}万" if amounts else "未获取"
    return {
        "success": True,
        "items": formatted,
        "stats": {"关键词": keyword, "数量": len(formatted), "平均成交额": avg}
    }


def _regex_extract_factories(html: str) -> list:
    items = []
    id_pat = re.compile(r'"companyId"\s*:\s*"?(\d+)"?|"memberId"\s*:\s*"?(\d+)"?')
    name_pat = re.compile(r'"companyName"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"')
    year_pat = re.compile(r'"creditYear"\s*:\s*"?(\d+)"?')
    amt_pat = re.compile(r'"amount90Day"\s*:\s*"?([\d.]+)"?|"AmountInfo"\s*:\s*"?([\d.]+)"?')
    addr_pat = re.compile(r'"province"\s*:\s*"([^"]{2,10})"')

    segments = re.split(r'(?={"companyId"|"memberId")', html)
    for seg in segments[1:]:
        item = {}
        m_id = id_pat.search(seg)
        if m_id: item["companyId"] = m_id.group(1) or m_id.group(2)
        else: continue
        m_name = name_pat.search(seg)
        if m_name: item["companyName"] = m_name.group(1)
        m_year = year_pat.search(seg)
        if m_year: item["creditYear"] = m_year.group(1)
        m_amt = amt_pat.search(seg)
        if m_amt: item["amount90Day"] = m_amt.group(1) or m_amt.group(2)
        m_addr = addr_pat.search(seg)
        if m_addr: item["location"] = m_addr.group(1)
        if item: items.append(item)
    return items


def _format_factory_result(items: list, keyword: str) -> dict:
    formatted = []
    for f in items[:10]:
        formatted.append({
            "companyId": f.get("companyId", ""),
            "公司名称": _strip(f.get("companyName", "")),
            "工厂标签": "源头工厂",
            "诚信通年限": f.get("creditYear", "未标注"),
            "近90天成交额": _amount(f.get("amount90Day", "")),
            "30天成交": f.get("soldCount30", "未披露"),
            "复购率": f.get("repeatCustomerRatio", ""),
            "旺旺在线": "✅",
            "发货地": f.get("location", "未标注"),
            "旺铺链接": f"https:{f.get('w_homeUrl','')}",
        })
    amounts = []
    for f in formatted:
        m = re.search(r"[\d.]+", str(f.get("近90天成交额", "")))
        if m: amounts.append(float(m.group()))
    avg = f"¥{sum(amounts)/len(amounts):.1f}万" if amounts else "未获取"
    return {
        "success": True,
        "items": formatted,
        "stats": {"关键词": keyword, "数量": len(formatted), "平均成交额": avg}
    }


# --- 工具函数 ---
def _strip(t) -> str:
    return re.sub(r"<[^>]+>", "", str(t)).strip()

def _price(t) -> str:
    if not t: return ""
    m = re.search(r"[\d.]+", str(t))
    return m.group() if m else str(t)

def _amount(t) -> str:
    if not t: return "未披露"
    try:
        f = float(re.search(r"[\d.]+", str(t)).group())
        if f >= 10000: return f"¥{f/10000:.1f}万"
        return f"¥{f:.0f}"
    except: return str(t)

def _addr(loc) -> str:
    if isinstance(loc, dict): return f"{loc.get('province','')}{loc.get('city','')}".strip()
    return str(loc) if loc else ""


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["products", "factories"])
    p.add_argument("keyword", nargs="+")
    p.add_argument("--province")
    p.add_argument("--page", type=int, default=1)
    args = p.parse_args()

    kw = " ".join(args.keyword)
    if args.cmd == "products":
        r = search_products(kw, args.page)
    else:
        r = search_factories(kw, args.province or "", args.page)

    print(json.dumps(r, ensure_ascii=False, indent=2))
