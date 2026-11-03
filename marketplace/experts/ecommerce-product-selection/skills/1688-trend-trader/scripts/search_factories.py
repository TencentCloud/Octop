#!/usr/bin/env python3
"""
1688 源头工厂搜索 — search_factories.py
用法: python3 search_factories.py <关键词> [--province 省名]

依赖：python3, requests（标准库 + pip install requests）
网络：仅访问 *.1688.com 域名
凭证：无需，可选配置 ALI_COOKIE 环境变量增强访问能力
"""

import sys
import json
import re
import os
import requests
from typing import Optional

# 可选 Cookie（从环境变量读取，非必需）
_OPTIONAL_COOKIE = os.environ.get("ALI_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://vip.1688.com/",
}
if _OPTIONAL_COOKIE:
    HEADERS["Cookie"] = _OPTIONAL_COOKIE

def search_factories(keyword: str, province: str = "", page: int = 1) -> dict:
    """
    搜索 1688 "实力工厂" / "超级工厂" 标签的源头厂家。
    """
    # 1688 工厂搜索接口
    params = {
        "keywords": keyword,
        "beginPage": page,
        "pageSize": 20,
        "qrquick": "factory",
        "topTab": "工厂",
        "filter": "type=proFactor",
    }
    if province:
        params["province"] = province

    url = "https://search.1688.com/service/json.htm"

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.encoding = "gbk" if resp.apparent_encoding in ("gbk", "gb2312") else "utf-8"
    except Exception as e:
        return {"error": str(e), "success": False}

    text = resp.text

    # 尝试解析 JSON
    try:
        raw = resp.json()
        return _parse_factory_response(raw, keyword)
    except Exception:
        pass

    # HTML 内嵌 JSON 兜底
    try:
        m = re.search(r'window\.__INIT_STATE__\s*=\s*(\{.*?\})\s*;', text, re.DOTALL)
        if m:
            raw = json.loads(m.group(1))
            return _parse_factory_response(raw, keyword)
    except Exception:
        pass

    return {"error": "无法解析响应", "raw_snippet": text[:500], "success": False}


def _parse_factory_response(data: dict, keyword: str) -> dict:
    """解析工厂数据"""
    items = []

    def dig(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                dig(v)
        elif isinstance(obj, list):
            for item in obj:
                dig(item)

    # 提取所有 offer/company 相关列表
    all_lists = []
    def collect_lists(obj, path=""):
        if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
            if len(obj) > 0 and any(k in str(obj[0]) for k in ["companyName","creditYear","factoryType","isFactory"]):
                all_lists.append(obj)
        elif isinstance(obj, dict):
            for k,v in obj.items():
                collect_lists(v, path+"."+k)
    collect_lists(data)

    for lst in all_lists:
        for item in lst[:10]:
            if not isinstance(item, dict):
                continue
            # 筛选工厂（标签识别）
            title = _clean_html(item.get("title","") or item.get("subject",""))
            company = _clean_html(item.get("companyName","") or item.get("company",""))
            tags = " ".join(str(t) for t in item.get("tags",[]) or item.get("keyWords",[]) or [])
            is_factory = item.get("isFactory") or item.get("isFactoryInfo") or \
                         ("工厂" in title or "工厂" in company or "实力" in tags or "超级" in tags)

            if not is_factory:
                continue

            items.append({
                "companyId": item.get("companyId") or item.get("memberId","") or item.get("id",""),
                "公司名称": company or title,
                "工厂标签": tags,
                "诚信通年限": item.get("creditYear","未标注"),
                "近90天成交额": _parse_amount(item.get("AmountInfo") or item.get("soldInfo",{}).get("amount90Day","")),
                "30天成交": item.get("soldInfo",{}).get("soldCount30","未披露") or item.get("soldCount30","未披露"),
                "复购率": item.get("repeatCustomerRatio","") or item.get("repeatRate",""),
                "旺旺在线": "✅在线" if item.get("online") or item.get("w_status") == "1" else "❌离线",
                "发货地": _parse_addr(item.get("location",{})),
                "联系方式": item.get("mobile") or item.get("phone") or "需登录查看",
                "旺铺链接": item.get("w_homeUrl") or "",
                "产品列表": [_clean_html(p) for p in (item.get("productList",[]) or item.get("products",[]) or [])[:5]],
            })

    prices = []
    for it in items:
        m = re.search(r"[\d.]+", str(it.get("近90天成交额","")))
        if m: prices.append(float(m.group()))

    stats = {
        "搜索关键词": keyword,
        "工厂数量": len(items),
        "平均成交额（万）": f"¥{sum(prices)/len(prices):.1f}万" if prices else "未获取",
        "来源": "1688 工厂搜索",
    }
    return {"success": True, "items": items, "stats": stats}


def _parse_amount(val) -> str:
    if not val: return "未披露"
    val = str(val)
    if "万" in val: return val
    try:
        f = float(re.search(r"[\d.]+", val).group())
        if f >= 10000: return f"¥{f/10000:.1f}万"
        return f"¥{f:.0f}"
    except: return val

def _parse_addr(loc) -> str:
    if isinstance(loc, dict):
        return f"{loc.get('province','')}{loc.get('city','')}".strip()
    return str(loc) if loc else ""

def _clean_html(t) -> str:
    return re.sub(r"<[^>]+>", "", str(t)).strip()


if __name__ == "__main__":
    args = sys.argv[1:]
    kw = ""
    province = ""
    page = 1
    i = 0
    while i < len(args):
        if args[i] == "--province" and i+1 < len(args):
            province = args[i+1]; i += 2
        elif args[i] == "--page" and i+1 < len(args):
            page = int(args[i+1]); i += 2
        else:
            kw = args[i]; i += 1

    if not kw:
        print("用法: python3 search_factories.py <关键词> [--province 省名]")
        sys.exit(1)

    result = search_factories(kw, province, page)
    print(json.dumps(result, ensure_ascii=False, indent=2))
