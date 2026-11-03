#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
walter-product-research.py - 亚马逊选品调研

核心问题: "我这个想法能不能做？"

作者: 分析虾 🦐
日期: 2026-04-13
"""

import sys
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts')))
from unified_data_layer_v2 import AmazonDataLayerV2


class ProductResearch:
    """亚马逊选品调研"""
    
    def __init__(self):
        self.data_layer = AmazonDataLayerV2()
        self.marketplace = "US"
    
    # =========================================================================
    # 主入口
    # =========================================================================
    
    def analyze(self, user_input: str,
                price: Optional[float] = None,
                cost: Optional[float] = None) -> Dict[str, Any]:
        """
        选品调研完整流程
        
        Args:
            user_input: 用户输入，如 "我想做沙滩裤"
            price: 目标售价（可选）
            cost: 预估成本（可选）
            
        Returns:
            选品调研报告
        """
        print(f"\n{'='*70}")
        print(f"[Product Research] Product Selection Research")
        print(f"{'='*70}")
        
        # 1. 提取关键词
        keyword = self._extract_keyword(user_input)
        print(f"\n[Keyword] {keyword}")
        
        # 2. 快速扫描
        print(f"\n[Step 1/5] Quick Scan...")
        scan = self._quick_scan(keyword)
        self._display_scan(scan)
        
        # 3. 市场分析
        print(f"\n[Step 2/5] Market Analysis...")
        market = self._analyze_market(scan.get('node_id'))
        self._display_market(market)
        
        # 4. 利润测算
        if price:
            print(f"\n[Step 3/5] Profit Calculation...")
            profit = self._calculate_profit(price, cost)
            self._display_profit(profit)
        else:
            print(f"\n[Step 3/5] Profit Calculation... [SKIP - No price provided]")
            print(f"[Hint] Provide price to calculate profit")
            profit = None
        
        # 5. 竞品发现
        print(f"\n[Step 4/5] Competitor Discovery...")
        competitors = self._discover_competitors(keyword)
        self._display_competitors(competitors)
        
        # 6. 风险评估
        print(f"\n[Step 5/5] Risk Assessment...")
        risks = self._assess_risks(scan, market)
        self._display_risks(risks)
        
        # 汇总决策
        decision = self._make_decision(scan, market, profit)
        
        # 返回结果
        return {
            'scene': 'product_research',
            'keyword': keyword,
            'timestamp': datetime.now().isoformat(),
            'decision': decision,
            'score': scan.get('score', 0),
            'market': market,
            'profit': profit,
            'competitors': competitors,
            'risks': risks
        }
    
    # =========================================================================
    # 核心方法
    # =========================================================================
    
    def _extract_keyword(self, text: str) -> str:
        """提取关键词"""
        prefixes = ['我想做', '分析', '看看', '调研', '看一下', '查一下', 
                   '能不能做', '可以做吗', '值得做吗', '有机会吗', '市场']
        for p in prefixes:
            text = text.replace(p, '')
        return text.strip()
    
    def _quick_scan(self, keyword: str) -> Dict[str, Any]:
        """快速扫描 - 30秒获取核心指标"""
        # 获取市场情报
        result = self.data_layer.get_complete_market_intelligence(keyword)
        
        if result.get('code') != 'OK':
            return {
                'score': 0,
                'recommendation': 'ERROR',
                'error': result.get('message', 'API failed')
            }
        
        data = result.get('data', {})
        category = data.get('category', {})
        brand_analysis = data.get('brand_analysis', {})
        trend_analysis = data.get('trend_analysis', {})
        
        # 计算机会评分
        score, details = self._calculate_score(
            category.get('products', 0),
            brand_analysis.get('cr3', 1.0),
            trend_analysis.get('direction', 'unknown')
        )
        
        # 决策
        if score >= 60:
            recommendation = 'GO'
        elif score >= 40:
            recommendation = 'CAUTION'
        else:
            recommendation = 'NO-GO'
        
        return {
            'score': score,
            'details': details,
            'recommendation': recommendation,
            'node_id': category.get('nodeIdPath', ''),
            'products': category.get('products', 0),
            'cr3': brand_analysis.get('cr3', 0) * 100,
            'trend': trend_analysis.get('direction', 'unknown'),
            'top_brand': brand_analysis.get('top_brand', '')
        }
    
    def _calculate_score(self, products: int, cr3: float, trend: str) -> tuple:
        """计算机会评分"""
        score = 0
        details = {}
        
        # Market Size (30pts)
        if products >= 50000:
            size_score = 30
        elif products >= 20000:
            size_score = 25
        elif products >= 10000:
            size_score = 20
        elif products >= 5000:
            size_score = 15
        else:
            size_score = 10
        score += size_score
        details['market_size'] = size_score
        
        # Competition (30pts) - CR3越低越好
        if cr3 < 0.3:
            comp_score = 30
        elif cr3 < 0.4:
            comp_score = 25
        elif cr3 < 0.5:
            comp_score = 20
        elif cr3 < 0.6:
            comp_score = 15
        elif cr3 < 0.7:
            comp_score = 10
        else:
            comp_score = 5
        score += comp_score
        details['competition'] = comp_score
        
        # Trend (20pts)
        if trend == 'up':
            trend_score = 20
        elif trend == 'stable':
            trend_score = 15
        elif trend == 'down':
            trend_score = 5
        else:
            trend_score = 10
        score += trend_score
        details['trend'] = trend_score
        
        # Price Opportunity (20pts) - 基于价格带分布
        price_bands = 3  # 简化处理
        if price_bands >= 4:
            price_score = 20
        elif price_bands >= 3:
            price_score = 15
        elif price_bands >= 2:
            price_score = 10
        else:
            price_score = 5
        score += price_score
        details['price_opportunity'] = price_score
        
        return score, details
    
    def _analyze_market(self, node_id: str) -> Dict[str, Any]:
        """市场分析"""
        if not node_id:
            return {}
        
        # 获取品牌集中度
        result = self.data_layer.api.call(
            'market_brand_concentration',
            node_id_path=node_id,
            marketplace=self.marketplace,
            top_n=10
        )
        
        if result.get('code') != 'OK':
            return {'error': result.get('message', 'API failed')}
        
        brands = result.get('data', [])
        
        # 计算指标
        total_units = sum(b.get('totalUnits', 0) for b in brands)
        cr3 = sum(b.get('totalUnitsRatio', 0) for b in brands[:3])
        cr5 = sum(b.get('totalUnitsRatio', 0) for b in brands[:5])
        cr10 = sum(b.get('totalUnitsRatio', 0) for b in brands[:10])
        
        # 平均价格
        avg_price = sum(b.get('avgPrice', 0) for b in brands) / max(len(brands), 1)
        
        return {
            'total_brands': len(brands),
            'total_units': total_units,
            'cr3': cr3 * 100,
            'cr5': cr5 * 100,
            'cr10': cr10 * 100,
            'avg_price': avg_price,
            'top_brands': brands[:5]
        }
    
    def _calculate_profit(self, price: float, cost: float = None) -> Dict[str, Any]:
        """利润测算"""
        if cost is None:
            cost = price * 0.35  # 默认成本35%
        
        # 费用结构（基于经验估算）
        amazon_fee = price * 0.15      # 平台费15%
        fba_fee = price * 0.30          # FBA约30%
        ad_cost = price * 0.15          # ACOS 15%
        
        revenue = price - cost - amazon_fee - fba_fee - ad_cost
        margin = (revenue / price) * 100 if price > 0 else 0
        
        # 盈亏平衡点 (假设固定成本$5000)
        fixed_cost = 5000
        break_even_units = int(fixed_cost / revenue) if revenue > 0 else 0
        
        return {
            'price': price,
            'cost': cost,
            'cost_ratio': (cost / price) * 100 if price > 0 else 0,
            'amazon_fee': amazon_fee,
            'fba_fee': fba_fee,
            'ad_cost': ad_cost,
            'net_profit': revenue,
            'margin': margin,
            'break_even_units': break_even_units
        }
    
    def _discover_competitors(self, keyword: str) -> List[Dict[str, Any]]:
        """发现竞品"""
        result = self.data_layer.api.call(
            'competitor_lookup',
            keyword=keyword,
            marketplace=self.marketplace,
            page=1,
            page_size=5
        )
        
        if result.get('code') != 'OK':
            return []
        
        products = result.get('data', [])
        
        competitors = []
        for p in products[:5]:
            competitors.append({
                'asin': p.get('asin', ''),
                'name': (p.get('title', '') or '')[:60],
                'price': p.get('price', 0),
                'rating': p.get('rating', 0),
                'reviews': p.get('reviews', 0),
                'bsr': p.get('bsr', 0)
            })
        
        return competitors
    
    def _assess_risks(self, scan: Dict, market: Dict) -> List[Dict[str, Any]]:
        """风险评估"""
        risks = []
        
        # 基于评分
        score = scan.get('score', 0)
        if score < 30:
            risks.append({'level': 'high', 'factor': 'Score too low', 'desc': f'Score {score}/100 indicates weak opportunity'})
        
        # 基于CR3
        cr3 = scan.get('cr3', 0)
        if cr3 > 70:
            risks.append({'level': 'high', 'factor': 'High concentration', 'desc': f'CR3={cr3:.0f}% - Market dominated by top brands'})
        elif cr3 > 60:
            risks.append({'level': 'medium', 'factor': 'Medium concentration', 'desc': f'CR3={cr3:.0f}% - Competition is significant'})
        
        # 基于趋势
        trend = scan.get('trend', 'unknown')
        if trend == 'down':
            risks.append({'level': 'high', 'factor': 'Declining trend', 'desc': 'Market trend is downward'})
        elif trend == 'unknown':
            risks.append({'level': 'medium', 'factor': 'Trend unknown', 'desc': 'Cannot determine market trend'})
        
        # 基于利润
        if market and not risks:
            avg_price = market.get('avg_price', 0)
            estimated_cost = avg_price * 0.35
            estimated_profit = avg_price * 0.40  # 约40%费用
            if estimated_profit < avg_price * 0.1:
                risks.append({'level': 'medium', 'factor': 'Low margin', 'desc': 'Profit margin may be tight at current price levels'})
        
        if not risks:
            risks.append({'level': 'low', 'factor': 'No major risks', 'desc': 'Market looks viable'})
        
        return risks
    
    def _make_decision(self, scan: Dict, market: Dict, profit: Dict = None) -> Dict[str, Any]:
        """最终决策"""
        score = scan.get('score', 0)
        
        if score >= 60:
            decision = 'GO'
            summary = 'Market shows strong opportunity'
        elif score >= 40:
            decision = 'CAUTION'
            summary = 'Opportunity exists but with risks'
        else:
            decision = 'NO-GO'
            summary = 'Market opportunity is weak'
        
        return {
            'decision': decision,
            'summary': summary,
            'confidence': 'High' if score >= 60 or score < 40 else 'Medium'
        }
    
    # =========================================================================
    # 显示方法
    # =========================================================================
    
    def _display_scan(self, scan: Dict):
        """显示扫描结果"""
        print(f"\n{'='*50}")
        print(f"[QUICK SCAN] Score: {scan.get('score', 0)}/100")
        print(f"{'='*50}")
        
        rec = scan.get('recommendation', 'UNKNOWN')
        print(f"Recommendation: [{rec}]")
        print(f"Products: {scan.get('products', 0):,}")
        print(f"CR3: {scan.get('cr3', 0):.1f}%")
        print(f"Trend: {scan.get('trend', 'unknown')}")
        print(f"Top Brand: {scan.get('top_brand', 'N/A')}")
        
        # 评分明细
        details = scan.get('details', {})
        print(f"\nScore Breakdown:")
        print(f"  Market Size:   {details.get('market_size', 0)}/30")
        print(f"  Competition:   {details.get('competition', 0)}/30")
        print(f"  Trend:         {details.get('trend', 0)}/20")
        print(f"  Price Opp:     {details.get('price_opportunity', 0)}/20")
    
    def _display_market(self, market: Dict):
        """显示市场分析"""
        if not market or market.get('error'):
            print("[Market Analysis] Data unavailable")
            return
        
        print(f"\n[Market Analysis]")
        print(f"Total Brands: {market.get('total_brands', 0)}")
        print(f"CR3: {market.get('cr3', 0):.1f}%")
        print(f"CR5: {market.get('cr5', 0):.1f}%")
        print(f"CR10: {market.get('cr10', 0):.1f}%")
        print(f"Avg Price: ${market.get('avg_price', 0):.2f}")
        
        print(f"\nTop Brands:")
        for i, brand in enumerate(market.get('top_brands', [])[:3], 1):
            print(f"  {i}. {brand.get('brand', 'Unknown')} ({brand.get('totalUnitsRatio', 0)*100:.1f}%) - ${brand.get('avgPrice', 0):.2f}")
    
    def _display_profit(self, profit: Dict):
        """显示利润测算"""
        if not profit:
            return
        
        print(f"\n[Profit Calculation]")
        print(f"Selling Price: ${profit.get('price', 0):.2f}")
        print(f"Product Cost:  ${profit.get('cost', 0):.2f} ({profit.get('cost_ratio', 0):.0f}%)")
        print(f"Amazon Fee:   -${profit.get('amazon_fee', 0):.2f} (15%)")
        print(f"FBA Fee:      -${profit.get('fba_fee', 0):.2f} (30%)")
        print(f"Ad Cost:      -${profit.get('ad_cost', 0):.2f} (ACOS 15%)")
        print(f"{'-'*30}")
        print(f"Net Profit:    ${profit.get('net_profit', 0):.2f}/unit")
        print(f"Margin:        {profit.get('margin', 0):.1f}%")
        
        break_even = profit.get('break_even_units', 0)
        if break_even > 0:
            print(f"Break-even:    {break_even:,} units (at ${profit.get('price', 0):.2f})")
    
    def _display_competitors(self, competitors: List[Dict]):
        """显示竞品"""
        if not competitors:
            print("[Competitors] No data found")
            return
        
        print(f"\n[Top {len(competitors)} Competitors]")
        for i, comp in enumerate(competitors, 1):
            print(f"\n  {i}. {comp.get('name', 'Unknown')}")
            print(f"     ASIN: {comp.get('asin', 'N/A')}")
            print(f"     Price: ${comp.get('price', 0):.2f} | Rating: {comp.get('rating', 0):.1f} | Reviews: {comp.get('reviews', 0):,}")
            if comp.get('bsr'):
                print(f"     BSR: #{comp.get('bsr', 0):,}")
    
    def _display_risks(self, risks: List[Dict]):
        """显示风险"""
        print(f"\n[Risk Assessment]")
        for risk in risks:
            level = risk.get('level', 'unknown').upper()
            factor = risk.get('factor', '')
            desc = risk.get('desc', '')
            symbol = '🔴' if level == 'HIGH' else '🟡' if level == 'MEDIUM' else '🟢'
            print(f"  {symbol} [{level}] {factor}")
            print(f"      {desc}")


# =========================================================================
# 主入口
# =========================================================================

if __name__ == '__main__':
    import json
    
    researcher = ProductResearch()
    
    # 测试
    print("\n" + "="*70)
    print("TEST: Product Research")
    print("="*70)
    
    result = researcher.analyze("beach shorts", price=28.99)
    
    print(f"\n{'='*70}")
    print(f"[FINAL DECISION] {result['decision']}")
    print(f"{'='*70}")
    print(f"Decision: {result['decision']}")
    print(f"Score: {result['score']}/100")
    print(f"Keyword: {result['keyword']}")
