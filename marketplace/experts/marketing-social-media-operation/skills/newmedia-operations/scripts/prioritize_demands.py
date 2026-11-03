#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

class DemandPrioritizer:
    def __init__(self):
        self.priority_levels = {
            'P0': {'min_frequency': 15, 'description': '紧急重要'},
            'P1': {'min_frequency': 8, 'description': '重要不紧急'},
            'P2': {'min_frequency': 3, 'description': '紧急不重要'},
            'P3': {'min_frequency': 0, 'description': '不紧急不重要'}
        }
    
    def group_similar_demands(self, demands: List[Dict]) -> List[Dict]:
        grouped = defaultdict(list)
        
        for demand in demands:
            key = f"{demand['demand_type']}_{demand['pain_points'][0] if demand['pain_points'] else 'other'}"
            grouped[key].append(demand)
        
        result = []
        for key, group in grouped.items():
            result.append({
                'demand_group': key,
                'demand_type': group[0]['demand_type'],
                'pain_points': list(set([p for d in group for p in d['pain_points']])),
                'frequency': len(group),
                'total_likes': sum(d.get('likes', 0) for d in group),
                'negative_count': sum(1 for d in group if d.get('is_negative', False)),
                'platforms': list(set(d.get('platform', '') for d in group)),
                'sample_contents': [d['content'] for d in group[:3]],
                'all_demands': group
            })
        
        return result
    
    def calculate_priority(self, demand_group: Dict) -> str:
        frequency = demand_group['frequency']
        negative_ratio = demand_group['negative_count'] / demand_group['frequency']
        avg_likes = demand_group['total_likes'] / demand_group['frequency']
        
        for level, criteria in self.priority_levels.items():
            if frequency >= criteria['min_frequency']:
                if level == 'P0':
                    return 'P0'
                elif level == 'P1' and negative_ratio > 0.3:
                    return 'P0'
                elif level == 'P1':
                    return 'P1'
                elif level == 'P2':
                    return 'P2'
        
        return 'P3'
    
    def calculate_score(self, demand_group: Dict) -> float:
        frequency = demand_group['frequency']
        negative_ratio = demand_group['negative_count'] / demand_group['frequency']
        avg_likes = demand_group['total_likes'] / demand_group['frequency']
        
        score = frequency * 10 + negative_ratio * 50 + avg_likes * 0.1
        return score
    
    def prioritize_demands(self, demands: List[Dict]) -> List[Dict]:
        grouped = self.group_similar_demands(demands)
        
        for group in grouped:
            group['priority'] = self.calculate_priority(group)
            group['score'] = self.calculate_score(group)
        
        priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
        
        sorted_demands = sorted(grouped, key=lambda x: (
            priority_order[x['priority']],
            -x['score']
        ))
        
        return sorted_demands
    
    def generate_priority_summary(self, prioritized_demands: List[Dict]) -> Dict:
        summary = defaultdict(list)
        
        for demand in prioritized_demands:
            summary[demand['priority']].append(demand)
        
        return {
            'P0': summary['P0'],
            'P1': summary['P1'],
            'P2': summary['P2'],
            'P3': summary['P3'],
            'total_demands': len(prioritized_demands),
            'priority_distribution': {
                'P0': len(summary['P0']),
                'P1': len(summary['P1']),
                'P2': len(summary['P2']),
                'P3': len(summary['P3'])
            }
        }
    
    def save_to_json(self, prioritized_demands: List[Dict], summary: Dict, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "prioritize_time": datetime.now().isoformat(),
                "summary": summary,
                "prioritized_demands": prioritized_demands
            }, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已完成需求分级并保存到 {output_path}")
        print(f"   P0级需求: {summary['priority_distribution']['P0']} 个")
        print(f"   P1级需求: {summary['priority_distribution']['P1']} 个")
        print(f"   P2级需求: {summary['priority_distribution']['P2']} 个")
        print(f"   P3级需求: {summary['priority_distribution']['P3']} 个")

def main():
    parser = argparse.ArgumentParser(description='需求分级与优先级排序')
    parser.add_argument('--input', type=str, required=True, help='输入文件路径')
    parser.add_argument('--output', type=str, default='data/prioritized_demands.json', help='输出文件路径')
    
    args = parser.parse_args()
    
    prioritizer = DemandPrioritizer()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    demands = data.get('demands', [])
    
    prioritized_demands = prioritizer.prioritize_demands(demands)
    summary = prioritizer.generate_priority_summary(prioritized_demands)
    prioritizer.save_to_json(prioritized_demands, summary, args.output)

if __name__ == '__main__':
    main()
