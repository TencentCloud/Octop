#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电商商品标题生成器
根据产品信息自动生成多个高转化率的商品标题
"""

import sys
import json
from typing import List, Dict

def generate_titles(product_info: Dict) -> List[str]:
    """
    根据产品信息生成标题
    
    Args:
        product_info: 包含 product_name, selling_points, target_audience, 
                     promotion, platform 等信息的字典
    
    Returns:
        生成的标题列表
    """
    titles = []
    
    product_name = product_info.get('product_name', '产品')
    selling_points = product_info.get('selling_points', [])
    target_audience = product_info.get('target_audience', '')
    promotion = product_info.get('promotion', '')
    platform = product_info.get('platform', 'taobao')
    
    # 淘宝标题模板（60 字符）
    if platform == 'taobao':
        templates = [
            f"【买 1 送 3】2026 新款{product_name}{' '.join(selling_points[:2])} {target_audience} 限时特惠",
            f"冬季{product_name} {selling_points[0] if selling_points else ''}+ 热销{target_audience} 今天下单立减",
            f"{target_audience}必备！{product_name} {selling_points[0] if selling_points else ''} 现货速发",
            f"【{promotion}】{product_name} {' '.join(selling_points[:3])} 包邮",
        ]
    
    # 拼多多标题（简单直接）
    elif platform == 'pinduoduo':
        templates = [
            f"9.9 包邮 {product_name} {selling_points[0] if selling_points else ''} 特价",
            f"【{promotion}】{product_name} 限时抢购 手慢无",
            f"{product_name} 爆款热销 {target_audience} 首选",
        ]
    
    # 抖音标题（场景化）
    elif platform == 'douyin':
        templates = [
            f"冬天怕冷？{product_name}让你暖一整天！{selling_points[0] if selling_points else ''}",
            f"还在为{target_audience}烦恼？这款{product_name}帮你解决！",
            f"用了{product_name}才知道，{selling_points[0] if selling_points else ''}这么重要！",
        ]
    
    else:  # 通用
        templates = [
            f"【热销】{product_name} {' '.join(selling_points[:3])} {promotion}",
            f"2026 新款{product_name} {target_audience}推荐 {selling_points[0] if selling_points else ''}",
            f"{product_name} 限时特惠{' '.join(selling_points[:2])} 包邮",
        ]
    
    titles.extend(templates)
    return titles


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "请提供产品信息 JSON",
            "example": {
                "product_name": "保暖内衣",
                "selling_points": ["加绒加厚", "发热", "防静电"],
                "target_audience": "男士",
                "promotion": "买一送一",
                "platform": "taobao"
            }
        }, ensure_ascii=False))
        sys.exit(1)
    
    try:
        product_info = json.loads(sys.argv[1])
        titles = generate_titles(product_info)
        
        result = {
            "product_name": product_info.get('product_name', '产品'),
            "platform": product_info.get('platform', '通用'),
            "titles": titles,
            "tips": [
                "标题前 10 个字最关键（移动端展示）",
                "避免使用违规词（最、第一、国家级等）",
                "包含热搜词提升搜索曝光"
            ]
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析错误：{str(e)}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"生成失败：{str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
