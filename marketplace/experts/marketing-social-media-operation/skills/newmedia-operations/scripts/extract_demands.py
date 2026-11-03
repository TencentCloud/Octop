#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict
from collections import Counter, defaultdict

class DemandExtractor:
    def __init__(self):
        self.demand_keywords = {
            '功能需求': ['功能', '增加', '缺少', '需要', '希望', '应该', '添加', '支持'],
            '体验需求': ['体验', '慢', '卡', '复杂', '简单', '方便', '好用', '流畅'],
            '服务需求': ['客服', '服务', '回复', '响应', '售后', '态度', '帮助'],
            '内容需求': ['内容', '质量', '数量', '详细', '介绍', '说明', '透明']
        }
    
    def extract_demand_type(self, text: str) -> str:
        scores = {}
        for demand_type, keywords in self.demand_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            scores[demand_type] = score
        
        max_score = max(scores.values())
        if max_score == 0:
            return '其他'
        
        for demand_type, score in scores.items():
            if score == max_score:
                return demand_type
        
        return '其他'
    
    def extract_pain_points(self, text: str) -> List[str]:
        pain_points = []
        negative_words = ['差', '慢', '不好', '问题', '困难', '麻烦', '复杂', '失败']
        
        for word in negative_words:
            if word in text:
                pain_points.append(word)
        
        return pain_points
    
    def extract_demands(self, data: List[Dict]) -> List[Dict]:
        demands = []
        
        for item in data:
            content = item.get('cleaned_content', item.get('content', ''))
            if not content:
                continue
            
            demand = {
                'id': item.get('id', ''),
                'platform': item.get('platform', ''),
                'content': content,
                'demand_type': self.extract_demand_type(content),
                'pain_points': self.extract_pain_points(content),
                'sentiment': item.get('sentiment', 'neutral'),
                'is_negative': item.get('is_negative', False),
                'likes': item.get('likes', 0),
                'timestamp': item.get('timestamp', datetime.now().isoformat())
            }
            
            demands.append(demand)
        
        return demands
    
    def analyze_demands(self, demands: List[Dict]) -> Dict:
        demand_types = Counter([d['demand_type'] for d in demands])
        pain_points = Counter()
        
        for demand in demands:
            for point in demand['pain_points']:
                pain_points[point] += 1
        
        sentiment_counts = Counter([d['sentiment'] for d in demands])
        negative_count = sum(1 for d in demands if d['is_negative'])
        
        return {
            'total_demands': len(demands),
            'demand_types': dict(demand_types),
            'pain_points': dict(pain_points),
            'sentiment_distribution': dict(sentiment_counts),
            'negative_ratio': negative_count / len(demands) if demands else 0
        }
    
    def save_to_json(self, demands: List[Dict], analysis: Dict, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "extract_time": datetime.now().isoformat(),
                "analysis": analysis,
                "demands": demands
            }, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已提取 {len(demands)} 条需求到 {output_path}")
        print(f"   需求类型分布: {analysis['demand_types']}")
        print(f"   痛点统计: {analysis['pain_points']}")

def main():
    parser = argparse.ArgumentParser(description='需求提取与分析')
    parser.add_argument('--input', type=str, required=True, help='输入文件路径')
    parser.add_argument('--output', type=str, default='data/demands.json', help='输出文件路径')
    
    args = parser.parse_args()
    
    extractor = DemandExtractor()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    demands_data = data.get('data', []) if isinstance(data, dict) else data
    
    demands = extractor.extract_demands(demands_data)
    analysis = extractor.analyze_demands(demands)
    extractor.save_to_json(demands, analysis, args.output)

if __name__ == '__main__':
    main()
