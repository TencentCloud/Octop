#!/usr/bin/env python3
import json
import argparse
import re
import os
from datetime import datetime
from typing import List, Dict, Tuple
from collections import Counter

class DataCleaner:
    def __init__(self):
        self.emoticon_pattern = re.compile(r'[\U00010000-\U0010ffff]')
        self.spam_keywords = ['广告', '推广', '加微信', '兼职', '赚钱', '代购', '优惠', '折扣']
        self.min_content_length = 5
        self.similarity_threshold = 0.8
    
    def clean_text(self, text: str) -> str:
        text = self.emoticon_pattern.sub('', text)
        text = re.sub(r'[^\w\s\u4e00-\u9fff,.!?;:，。！？；：]', '', text)
        text = text.strip()
        return text
    
    def is_spam(self, text: str) -> bool:
        return any(keyword in text for keyword in self.spam_keywords)
    
    def is_valid(self, text: str) -> bool:
        if not text or len(text) < self.min_content_length:
            return False
        if self.is_spam(text):
            return False
        if text.count('好') > 5 or text.count('赞') > 5:
            return False
        return True
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1)
        words2 = set(text2)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def deduplicate_advanced(self, data: List[Dict]) -> List[Dict]:
        if not data:
            return []
        
        unique_data = []
        seen_contents = []
        
        for item in data:
            content = item.get('cleaned_content', item.get('content', ''))
            
            is_duplicate = False
            for seen_content in seen_contents:
                similarity = self.calculate_similarity(content, seen_content)
                if similarity > self.similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_data.append(item)
                seen_contents.append(content)
        
        return unique_data
    
    def clean_data(self, data: List[Dict], min_valid_count: int = 2000) -> Tuple[List[Dict], Dict]:
        cleaned = []
        invalid_stats = {
            'too_short': 0,
            'spam': 0,
            'empty': 0,
            'other': 0
        }
        
        for item in data:
            content = item.get('content', '')
            
            if not content:
                invalid_stats['empty'] += 1
                continue
            
            if len(content) < self.min_content_length:
                invalid_stats['too_short'] += 1
                continue
            
            if self.is_spam(content):
                invalid_stats['spam'] += 1
                continue
            
            cleaned_content = self.clean_text(content)
            
            if not self.is_valid(cleaned_content):
                invalid_stats['other'] += 1
                continue
            
            item['cleaned_content'] = cleaned_content
            item['is_valid'] = True
            cleaned.append(item)
        
        cleaned = self.deduplicate_advanced(cleaned)
        
        stats = {
            'original_count': len(data),
            'cleaned_count': len(cleaned),
            'invalid_stats': invalid_stats,
            'valid_ratio': len(cleaned) / len(data) if data else 0,
            'meets_minimum': len(cleaned) >= min_valid_count
        }
        
        return cleaned, stats
    
    def merge_files(self, input_paths: List[str]) -> List[Dict]:
        all_data = []
        platform_counts = Counter()
        
        for path in input_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if isinstance(data, dict) and 'data' in data:
                        platform = data.get('platform', 'unknown')
                        platform_counts[platform] += len(data['data'])
                        all_data.extend(data['data'])
                    elif isinstance(data, list):
                        all_data.extend(data)
                        
            except Exception as e:
                print(f"⚠️  读取文件 {path} 失败: {e}")
        
        print(f"\n📊 数据源统计：")
        for platform, count in platform_counts.items():
            print(f"   {platform}: {count} 条")
        
        return all_data
    
    def save_to_json(self, data: List[Dict], stats: Dict, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "clean_time": datetime.now().isoformat(),
                "total_count": len(data),
                "stats": stats,
                "data": data
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 数据清洗完成")
        print(f"{'='*50}")
        print(f"原始数据：{stats['original_count']} 条")
        print(f"清洗后数据：{stats['cleaned_count']} 条")
        print(f"有效率：{stats['valid_ratio']:.1%}")
        print(f"\n无效数据统计：")
        print(f"  内容过短：{stats['invalid_stats']['too_short']} 条")
        print(f"  垃圾信息：{stats['invalid_stats']['spam']} 条")
        print(f"  内容为空：{stats['invalid_stats']['empty']} 条")
        print(f"  其他原因：{stats['invalid_stats']['other']} 条")
        
        if not stats['meets_minimum']:
            print(f"\n⚠️  警告：清洗后数据量不足2000条，建议增加数据抓取")
        
        print(f"\n💾 数据已保存到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description='数据清洗与预处理')
    parser.add_argument('--input', type=str, required=True, help='输入文件或目录路径')
    parser.add_argument('--output', type=str, default='data/cleaned_data.json', help='输出文件路径')
    parser.add_argument('--min-valid-count', type=int, default=2000, help='最小有效数据量要求')
    
    args = parser.parse_args()
    
    cleaner = DataCleaner()
    
    if os.path.isdir(args.input):
        input_files = []
        for filename in os.listdir(args.input):
            if filename.endswith('.json'):
                input_files.append(os.path.join(args.input, filename))
        all_data = cleaner.merge_files(input_files)
    else:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_data = data.get('data', []) if isinstance(data, dict) else data
    
    cleaned_data, stats = cleaner.clean_data(all_data, args.min_valid_count)
    cleaner.save_to_json(cleaned_data, stats, args.output)

if __name__ == '__main__':
    main()
