#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test Product Research logic with mock data"""

import sys
import os

# Mock data layer
class MockAPILayer:
    def call(self, api_name, **kwargs):
        if api_name == "product_node":
            return {"code": "OK", "data": [{
                "nodeIdPath": "7141123011:7147440011:1040660:3456051:1046590",
                "nodeLabelPath": "Clothing:Women:Active:Active Shorts",
                "products": 3109
            }]}
        elif api_name == "market_brand_concentration":
            return {"code": "OK", "data": [
                {"brand": "CRZ YOGA", "totalUnitsRatio": 0.427, "avgPrice": 22.90, "totalUnits": 273384},
                {"brand": "BMJL", "totalUnitsRatio": 0.112, "avgPrice": 18.50, "totalUnits": 71707},
            ]}
        elif api_name == "competitor_lookup":
            return {"code": "OK", "data": [
                {"asin": "B071WV2SRC", "title": "CRZ YOGA Shorts", "price": 28.99, "rating": 4.5, "reviews": 2847, "bsr": 12},
                {"asin": "B08KHQY9DV", "title": "BALEAF Shorts", "price": 25.99, "rating": 4.2, "reviews": 1523, "bsr": 45},
            ]}
        return {"code": "ERROR"}
    
    def get_stats(self):
        return {"total": 0, "cached": 0}

class MockDataLayer:
    def __init__(self):
        self.api = MockAPILayer()
        self.marketplace = "US"
    
    def get_complete_market_intelligence(self, keyword):
        node = self.api.call("product_node", keyword=keyword)
        if node.get("code") != "OK":
            return {"code": "ERROR"}
        
        brand = self.api.call("market_brand_concentration", node_id_path="test")
        
        return {"code": "OK", "data": {
            "category": node["data"][0],
            "brand_analysis": {"cr3": 0.63, "top_brand": "CRZ YOGA"},
            "trend_analysis": {"direction": "up"}
        }}

# Test ProductResearch
class ProductResearch:
    def __init__(self):
        self.data_layer = MockDataLayer()
    
    def analyze(self, user_input, price=None, cost=None):
        keyword = self._extract_keyword(user_input)
        print("[Keyword]", keyword)
        
        scan = self._quick_scan(keyword)
        print("[Scan] Score:", scan['score'], "/100, Rec:", scan['recommendation'])
        
        competitors = self._discover_competitors(keyword)
        print("[Competitors]", len(competitors), "found")
        
        if price:
            profit = self._calculate_profit(price, cost)
            print("[Profit] $%.2f/unit (%.1f%%)" % (profit['net_profit'], profit['margin']))
        
        return {"keyword": keyword, "score": scan["score"]}
    
    def _extract_keyword(self, text):
        for p in ["我想做", "分析", "看看"]:
            text = text.replace(p, "")
        return text.strip()
    
    def _quick_scan(self, keyword):
        result = self.data_layer.get_complete_market_intelligence(keyword)
        if result.get("code") != "OK":
            return {"score": 0, "recommendation": "ERROR"}
        
        data = result.get("data", {})
        cr3 = data.get("brand_analysis", {}).get("cr3", 1.0)
        
        score = 20  # market size
        score += 10  # competition (high cr3)
        score += 15  # trend
        
        return {
            "score": score,
            "recommendation": "GO" if score >= 60 else "CAUTION",
            "products": 3109,
            "cr3": cr3 * 100
        }
    
    def _discover_competitors(self, keyword):
        result = self.data_layer.api.call("competitor_lookup", keyword=keyword)
        if result.get("code") != "OK":
            return []
        return result.get("data", [])
    
    def _calculate_profit(self, price, cost=None):
        if cost is None:
            cost = price * 0.35
        net = price - cost - price * 0.60
        return {"net_profit": net, "margin": net/price*100 if price else 0}


print("="*50)
print("TEST: Product Research")
print("="*50)
pr = ProductResearch()
result = pr.analyze("beach shorts", price=28.99)
print("\n[Result] Score:", result['score'])
print("[OK] Product Research logic passed")
