#!/usr/bin/env python3
"""
1688 开放平台 API 客户端 — ali_api.py

【重要说明】
本脚本为可选增强模块，无需配置即可运行基础功能。
如需获取更完整的1688数据（价格阶梯、SKU详情、认证资质），可选择性配置：
  1. 注册 1688 开放平台：https://open.1688.com/
  2. 创建应用获取 AppKey + AppSecret
  3. 设置环境变量：
     export ALI_APP_KEY=your_app_key
     export ALI_APP_SECRET=your_app_secret

未配置时，脚本会返回友好提示，不影响其他脚本使用。

API 覆盖范围：
  - 商品搜索 (alibaba.product.search)
  - 商品详情 (alibaba.product.get)
  - 公司信息 (alibaba.company.get)
  - 旺旺在线状态

依赖：python3, requests（标准库 + pip install requests）
网络：仅访问 gw.open.1688.com
凭证：可选（ALI_APP_KEY / ALI_APP_SECRET）
"""

import os
import json
import time
import hashlib
import requests
from urllib.parse import urlencode, quote
from typing import Optional

# ── 配置 ──────────────────────────────────────────────
# 【可选】1688 开放平台凭证，未配置时脚本会返回友好提示
# 获取方式：https://open.1688.com/ → 创建应用 → 获取 AppKey + AppSecret
APP_KEY    = os.environ.get("ALI_APP_KEY",    "")
APP_SECRET = os.environ.get("ALI_APP_SECRET", "")

# 1688 开放平台 API 基础地址
API_BASE = "https://gw.open.1688.com/openapi"

# ── 签名算法 ──────────────────────────────────────────
def _sign(params: dict, secret: str) -> str:
    """MD5 签名（1688 开放平台标准）"""
    sorted_keys = sorted(params.keys())
    pairs = [f"{k}{params[k]}" for k in sorted_keys]
    sign_str = "".join(pairs) + secret
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


def _top_call(method: str, params: dict, timeout: int = 20) -> Optional[dict]:
    """
    调用 1688 TOP API（开放平台标准协议）。
    method: 类似 alibaba.product.search
    """
    if not APP_KEY or not APP_SECRET:
        return None

    # 公共参数
    ts = str(int(time.time() * 1000))
    all_params = {
        "appKey":       APP_KEY,
        "method":       method,
        "timestamp":    ts,
        "format":       "json",
        "v":            "2.0",
        "signMethod":   "md5",
        # 业务参数
        **{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
           for k, v in params.items()},
    }
    all_params["sign"] = _sign(all_params, APP_SECRET)

    url = f"{API_BASE}/{method}/2.0"
    try:
        resp = requests.post(url, data=all_params, timeout=timeout)
        resp.encoding = "utf-8"
        data = resp.json()
        return data
    except Exception as e:
        return {"error": str(e)}


# ── 商品搜索 ──────────────────────────────────────────
def search_products(keyword: str, page: int = 1, page_size: int = 20,
                    category_id: str = "", price_min: float = 0,
                    price_max: float = 0, sort: str = "commissionRate-desc") -> dict:
    """
    搜索 1688 商品，支持按价格区间、排序筛选。
    sort 选项：commissionRate-desc / price-asc / price-desc / salecount-desc
    """
    params = {
        "keyword":    keyword,
        "pageNo":     page,
        "pageSize":   page_size,
        "sort":       sort,
    }
    if category_id:
        params["categoryId"] = category_id
    if price_min:
        params["priceStart"] = str(price_min)
    if price_max:
        params["priceEnd"] = str(price_max)

    result = _top_call("alibaba.product.search", params)

    if result is None:
        return {
            "success": False,
            "error": "未配置 ALI_APP_KEY / ALI_APP_SECRET",
            "setup_hint": "请访问 https://open.1688.com/ 注册并配置环境变量",
        }

    if result.get("error"):
        return {"success": False, "error": result.get("error")}

    try:
        products = result.get("result", {}).get("products", {}).get("product", [])
        total = result.get("result", {}).get("total", 0)
        return _format_product_result(products, keyword, total, page, page_size)
    except Exception as e:
        return {"success": False, "error": str(e), "raw": result}


def _format_product_result(products: list, keyword: str, total: int,
                            page: int, page_size: int) -> dict:
    """格式化商品搜索结果"""
    items = []
    for p in products:
        skus = p.get("skuInfos", {}).get("skuInfo", [])
        price_range = ""
        if skus:
            prices = [float(s.get("price", 0)) for s in skus if s.get("price")]
            if prices:
                price_range = f"¥{min(prices):.2f}~¥{max(prices):.2f}"

        items.append({
            "productId":    p.get("productID", ""),
            "商品ID":       p.get("productID", ""),
            "title":       p.get("subject", ""),
            "价格区间":     price_range,
            "单件起批价":   p.get("price", ""),
            "30天成交":     p.get("saleCount", ""),
            "起订量MOQ":   p.get("minimumOrderQuantity", "未标注"),
            "计量单位":     p.get("unit", ""),
            "诚信通年限":   p.get("creditYear", "未标注"),
            "旺旺在线":     "✅" if p.get("wStatus") == "1" else "❌",
            "发货地":       p.get("province", "") + p.get("city", ""),
            "公司名":       p.get("companyName", ""),
            "图片":         p.get("imageUri", ""),
            "商品链接":     f"https://detail.1688.com/offer/{p.get('productID','')}.html",
        })

    prices = []
    for item in items:
        m = [float(x) for x in str(item.get("单件起批价", "")).split("~") if x.replace(".","").isdigit()]
        if m: prices.extend(m)
    stats = {
        "关键词": keyword,
        "总数": total,
        "当前页": f"{page}/{max(1,(total+page_size-1)//page_size)}",
        "本页数量": len(items),
        "价格区间": f"¥{min(prices):.2f}~¥{max(prices):.2f}" if prices else "未获取",
        "平均起批价": f"¥{sum(prices)/len(prices):.2f}" if prices else "未获取",
    }
    return {"success": True, "items": items, "stats": stats}


# ── 商品详情 ──────────────────────────────────────────
def get_product_detail(product_id: str) -> dict:
    """获取商品详细信息（含价格阶梯、SKU、认证）"""
    params = {"productID": product_id}
    result = _top_call("alibaba.product.get", params)

    if result is None:
        return {
            "success": False,
            "error": "未配置 ALI_APP_KEY / ALI_APP_SECRET",
            "setup_hint": "请访问 https://open.1688.com/ 注册并配置环境变量",
        }

    if result.get("error"):
        return {"success": False, "error": result.get("error")}

    try:
        p = result.get("result", {}).get("product", {})
        return _format_product_detail(p, product_id)
    except Exception as e:
        return {"success": False, "error": str(e), "raw": result}


def _format_product_detail(p: dict, product_id: str) -> dict:
    """格式化商品详情"""
    skus = p.get("skuInfos", {}).get("skuInfo", [])
    price_list = []
    for s in skus:
        price_list.append({
            "规格":    s.get("specId", "") + " " + str(s.get("specProps", "")),
            "价格":    s.get("price", ""),
            "MOQ":     s.get("minOrderQuantity", ""),
            "库存":    s.get("canBookCount", ""),
        })

    # 认证资质
    certs = p.get("certificationList", {}).get("certification", [])
    cert_names = [c.get("certificationName", "") for c in certs if c.get("certificationName")]

    return {
        "success": True,
        "商品ID": product_id,
        "商品标题": p.get("subject", ""),
        "商品链接": f"https://detail.1688.com/offer/{product_id}.html",
        "公司信息": {
            "公司名称": p.get("companyName", ""),
            "诚信通年限": p.get("creditYear", "未标注"),
            "旺旺": p.get("memberId", ""),
            "旺旺在线": "✅" if p.get("wStatus") == "1" else "❌",
            "近90天成交额": p.get("amountOfBusinessVolume", "未披露"),
            "发货地": p.get("province", "") + p.get("city", ""),
            "旺铺": p.get("homePage", ""),
        },
        "价格阶梯": price_list if price_list else [{"区间":"见详情","单价":p.get("price","")}],
        "MOQ": p.get("minimumOrderQuantity", "未标注"),
        "30天成交": p.get("saleCount", "未披露"),
        "计量单位": p.get("unit", "件"),
        "认证资质": cert_names if cert_names else ["需进入详情页查看"],
        "图片列表": [p.get("imageUri", "")] + [x.get("imageUri","") for x in p.get("imageList",{}).get("image",[])],
        "SKU": price_list,
    }


# ── 旺旺状态 ──────────────────────────────────────────
def check_ww_status(member_id: str) -> dict:
    """检查旺旺在线状态"""
    params = {"memberId": member_id}
    result = _top_call("alibaba.ww.isOnline", params)
    if result is None:
        return {"success": False, "error": "未配置 API Key"}
    try:
        online = result.get("result", {}).get("isOnline", None)
        return {"success": True, "memberId": member_id, "在线": bool(online), "online": online}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import sys, argparse
    p = argparse.ArgumentParser(description="1688 开放平台 API 客户端")
    sub = p.add_subparsers(dest="cmd")

    search = sub.add_parser("search", help="搜索商品")
    search.add_argument("keyword", nargs="+")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int, default=20)
    search.add_argument("--price-min", type=float, default=0)
    search.add_argument("--price-max", type=float, default=0)
    search.add_argument("--sort", default="salecount-desc")

    detail = sub.add_parser("detail", help="商品详情")
    detail.add_argument("product_id")

    check = sub.add_parser("check", help="旺旺状态")
    check.add_argument("member_id")

    args = p.parse_args()

    if args.cmd == "search":
        kw = " ".join(args.keyword)
        r = search_products(kw, page=args.page, page_size=args.page_size,
                           price_min=args.price_min, price_max=args.price_max, sort=args.sort)
    elif args.cmd == "detail":
        r = get_product_detail(args.product_id)
    elif args.cmd == "check":
        r = check_ww_status(args.member_id)
    else:
        print("用法: python3 ali_api.py [search|detail|check] ...")
        sys.exit(1)

    print(json.dumps(r, ensure_ascii=False, indent=2))
