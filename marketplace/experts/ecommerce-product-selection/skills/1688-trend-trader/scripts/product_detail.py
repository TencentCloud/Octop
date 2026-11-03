#!/usr/bin/env python3
"""
1688 商品详情 & 价格分析 — product_detail.py
用法: python3 product_detail.py <商品ID或链接>

依赖：python3, requests（标准库 + pip install requests）
网络：仅访问 *.1688.com 域名
凭证：无需，可选配置 ALI_COOKIE 环境变量增强访问能力
"""

import sys
import json
import re
import os
import requests

# 可选 Cookie（从环境变量读取，非必需）
_OPTIONAL_COOKIE = os.environ.get("ALI_COOKIE", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://detail.1688.com/",
}
if _OPTIONAL_COOKIE:
    HEADERS["Cookie"] = _OPTIONAL_COOKIE

def get_product_detail(product_id: str) -> dict:
    """
    获取 1688 商品详细信息，包含价格阶梯、MOQ、认证资质等。
    """
    # 1688 offer detail 接口
    url = "https://greenwholesale.1688.com/service/offerdetail/v1/detail.json"
    params = {"offerId": product_id}

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        data = resp.json()
        return _parse_detail(data)
    except Exception:
        pass

    # 兜底: 淘宝/1688 open API 风格
    try:
        url2 = f"https://m.1688.com/offer/{product_id}.html"
        resp2 = requests.get(url2, headers=HEADERS, timeout=15)
        resp2.encoding = "utf-8"
        html = resp2.text
        return _parse_html_detail(html, product_id)
    except Exception as e:
        return {"error": str(e), "success": False}


def _parse_detail(data: dict) -> dict:
    """解析商品详情 JSON"""
    if not data:
        return {"error": "空响应", "success": False}

    # 提取核心字段
    basic = data.get("detail", {}) or data.get("data", {}) or data
    price = data.get("price", {}) or basic.get("price", {})
    seller = data.get("sellerInfo", {}) or data.get("company", {}) or {}

    # 价格阶梯
    price_list = []
    for entry in (price.get("priceRange", []) or price.get("skuCalPrice", []) or []):
        if isinstance(entry, dict):
            price_list.append({
                "数量区间": entry.get("range", entry.get("quantityRange", "")),
                "单价": entry.get("price", entry.get("priceString", "")),
                "折扣": entry.get("discount", ""),
            })

    # 认证资质
    certs = []
    for cert in (data.get("certList", []) or data.get("authenticateInfo", []) or []):
        certs.append(_clean_html(str(cert)))

    return {
        "success": True,
        "offerId": basic.get("offerId", basic.get("id", "")),
        "商品标题": _clean_html(basic.get("subject", basic.get("title", ""))),
        "商品链接": basic.get("detailUrl", f"https://detail.1688.com/offer/{basic.get('offerId','')}.html"),
        "公司信息": {
            "公司名称": _clean_html(seller.get("companyName", "")),
            "诚信通年限": seller.get("creditYear", "未标注"),
            "旺旺": seller.get("aliId", ""),
            "诚信等级": seller.get("creditLevel", ""),
            "工厂标签": seller.get("factoryTag", ""),
            "近90天成交额": _parse_amount(seller.get("AmountInfo", "")),
            "发货地": _clean_html(seller.get("address", "")),
            "旺铺链接": seller.get("homeUrl", ""),
        },
        "价格阶梯": price_list if price_list else [{"区间": "见详情页", "单价": price.get("priceString", price.get("unitPrice", ""))}],
        "MOQ": basic.get("最小起订量", basic.get("minOrder", "未标注")),
        "30天成交": basic.get("soldCount30", basic.get("soldCount", "未披露")),
        "180天成交": basic.get("soldCount180", "未披露"),
        "认证资质": certs if certs else ["需进入详情页查看"],
        "SKU信息": _extract_skus(data),
        "详细描述链接": basic.get("descriptionUrl", ""),
    }


def _parse_html_detail(html: str, product_id: str) -> dict:
    """从 HTML 中解析商品详情（兜底方案）"""
    # 尝试提取 JSON 数据
    patterns = [
        r'window\.__INIT_STATE__\s*=\s*(\{.*?\});',
        r'"price":"([\d.]+)"',
        r'"title":"([^"]+)"',
        r'"soldCount30":(\d+)',
        r'"minOrder":(\d+)',
        r'"companyName":"([^"]+)"',
    ]

    result = {"success": True, "fallback": True, "offerId": product_id}

    for pat in patterns:
        ms = re.findall(pat, html)
        if ms:
            result["matched_data"] = ms[:5]

    result["商品链接"] = f"https://detail.1688.com/offer/{product_id}.html"
    result["提示"] = "建议登录1688账号后获取完整数据"
    return result


def _extract_skus(data: dict) -> list:
    """提取 SKU 规格信息"""
    skus = []
    for sku_list in (data.get("skuList", []) or data.get("skus", []) or [data.get("sku", {})]):
        if isinstance(sku_list, dict):
            skus.append({
                "规格": sku_list.get("spec", sku_list.get("name", "")),
                "库存": sku_list.get("amount", sku_list.get("stock", "")),
                "价格": sku_list.get("price", sku_list.get("unitPrice", "")),
            })
    return skus[:10]  # 最多10条


def _parse_amount(val) -> str:
    if not val: return "未披露"
    val = str(val)
    if "万" in val or "元" in val: return val
    try:
        f = float(re.search(r"[\d.]+", val).group())
        if f >= 10000: return f"¥{f/10000:.1f}万"
        return f"¥{f:.0f}"
    except: return val

def _clean_html(t) -> str:
    return re.sub(r"<[^>]+>", "", str(t)).strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 product_detail.py <商品ID或1688链接>")
        sys.exit(1)

    pid = sys.argv[1]
    # 从链接中提取 ID
    m = re.search(r"(?:offer/|id=)(\d+)", pid)
    if m:
        pid = m.group(1)

    result = get_product_detail(pid)
    print(json.dumps(result, ensure_ascii=False, indent=2))
