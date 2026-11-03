#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict

class DataValidator:
    def __init__(self):
        self.min_valid_count = 2000
        self.min_content_length = 5
        self.max_duplicate_ratio = 0.3
    
    def validate_count(self, data: List[Dict], min_count: int) -> Dict:
        total_count = len(data)
        valid = total_count >= min_count
        
        return {
            'valid': valid,
            'total_count': total_count,
            'min_required': min_count,
            'shortage': max(0, min_count - total_count),
            'message': f"数据量{'达标' if valid else '不足'}：{total_count}/{min_count}"
        }
    
    def validate_quality(self, data: List[Dict]) -> Dict:
        valid_items = []
        invalid_items = []
        
        for item in data:
            content = item.get('cleaned_content', item.get('content', ''))
            
            if len(content) < self.min_content_length:
                invalid_items.append({'item': item, 'reason': '内容过短'})
                continue
            
            if not content.strip():
                invalid_items.append({'item': item, 'reason': '内容为空'})
                continue
            
            valid_items.append(item)
        
        valid_ratio = len(valid_items) / len(data) if data else 0
        
        return {
            'valid_count': len(valid_items),
            'invalid_count': len(invalid_items),
            'valid_ratio': valid_ratio,
            'valid_items': valid_items,
            'invalid_items': invalid_items[:10]
        }
    
    def check_duplicates(self, data: List[Dict]) -> Dict:
        contents = [item.get('cleaned_content', item.get('content', '')) for item in data]
        unique_contents = set(contents)
        
        duplicate_count = len(contents) - len(unique_contents)
        duplicate_ratio = duplicate_count / len(contents) if contents else 0
        
        return {
            'total_count': len(contents),
            'unique_count': len(unique_contents),
            'duplicate_count': duplicate_count,
            'duplicate_ratio': duplicate_ratio,
            'has_excessive_duplicates': duplicate_ratio > self.max_duplicate_ratio
        }
    
    def validate_platform_coverage(self, data: List[Dict], expected_platforms: List[str]) -> Dict:
        platform_counts = {}
        
        for item in data:
            platform = item.get('platform', 'unknown')
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        missing_platforms = [p for p in expected_platforms if p not in platform_counts]
        
        return {
            'platform_counts': platform_counts,
            'covered_platforms': list(platform_counts.keys()),
            'missing_platforms': missing_platforms,
            'coverage_ratio': len(platform_counts) / len(expected_platforms) if expected_platforms else 0
        }
    
    def generate_validation_report(self, data: List[Dict], min_count: int = 2000, expected_platforms: List[str] = None) -> Dict:
        count_validation = self.validate_count(data, min_count)
        quality_validation = self.validate_quality(data)
        duplicate_check = self.check_duplicates(data)
        
        platform_validation = {}
        if expected_platforms:
            platform_validation = self.validate_platform_coverage(quality_validation['valid_items'], expected_platforms)
        
        overall_valid = (
            count_validation['valid'] and
            quality_validation['valid_ratio'] >= 0.8 and
            not duplicate_check['has_excessive_duplicates']
        )
        
        return {
            'validation_time': datetime.now().isoformat(),
            'overall_valid': overall_valid,
            'count_validation': count_validation,
            'quality_validation': {
                'valid_count': quality_validation['valid_count'],
                'invalid_count': quality_validation['invalid_count'],
                'valid_ratio': quality_validation['valid_ratio']
            },
            'duplicate_check': duplicate_check,
            'platform_validation': platform_validation,
            'recommendations': self._generate_recommendations(
                count_validation,
                quality_validation,
                duplicate_check,
                platform_validation
            )
        }
    
    def _generate_recommendations(self, count_val, quality_val, dup_check, platform_val) -> List[str]:
        recommendations = []
        
        if not count_val['valid']:
            recommendations.append(f"⚠️  数据量不足，还需抓取至少 {count_val['shortage']} 条数据")
        
        if quality_val['valid_ratio'] < 0.8:
            recommendations.append(f"⚠️  数据质量较低，有效数据占比仅 {quality_val['valid_ratio']:.1%}")
        
        if dup_check['has_excessive_duplicates']:
            recommendations.append(f"⚠️  重复数据过多，重复率 {dup_check['duplicate_ratio']:.1%}")
        
        if platform_val and platform_val.get('missing_platforms'):
            recommendations.append(f"⚠️  缺少以下平台数据：{', '.join(platform_val['missing_platforms'])}")
        
        if not recommendations:
            recommendations.append("✅ 数据质量良好，可以进行下一步分析")
        
        return recommendations
    
    def save_report(self, report: Dict, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n📊 数据验证报告")
        print(f"{'='*50}")
        print(f"验证时间：{report['validation_time']}")
        print(f"总体状态：{'✅ 通过' if report['overall_valid'] else '❌ 未通过'}")
        print(f"\n数据量验证：{report['count_validation']['message']}")
        print(f"数据质量：有效数据 {report['quality_validation']['valid_count']} 条 ({report['quality_validation']['valid_ratio']:.1%})")
        print(f"重复检查：重复数据 {report['duplicate_check']['duplicate_count']} 条 ({report['duplicate_check']['duplicate_ratio']:.1%})")
        
        if report.get('platform_validation'):
            print(f"平台覆盖：{len(report['platform_validation']['covered_platforms'])} 个平台")
        
        print(f"\n💡 建议：")
        for rec in report['recommendations']:
            print(f"  {rec}")
        
        print(f"\n💾 报告已保存到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description='数据质量验证')
    parser.add_argument('--input', type=str, required=True, help='输入文件路径')
    parser.add_argument('--min-count', type=int, default=2000, help='最小数据量要求')
    parser.add_argument('--platforms', type=str, default='', help='期望的平台列表（逗号分隔）')
    parser.add_argument('--output', type=str, default='data/validation_report.json', help='输出文件路径')
    
    args = parser.parse_args()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, dict) and 'data' in data:
        data = data['data']
    
    expected_platforms = [p.strip() for p in args.platforms.split(',') if p.strip()] if args.platforms else None
    
    validator = DataValidator()
    report = validator.generate_validation_report(data, args.min_count, expected_platforms)
    validator.save_report(report, args.output)

if __name__ == '__main__':
    main()
