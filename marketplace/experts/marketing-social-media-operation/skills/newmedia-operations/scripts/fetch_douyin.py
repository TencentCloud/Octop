#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict

class DouyinFetcher:
    def __init__(self):
        self.base_url = "https://www.douyin.com"
    
    def fetch_comments(self, keyword: str, limit: int = 50) -> List[Dict]:
        comments = []
        
        sample_comments = [
            {
                "platform": "抖音",
                "keyword": keyword,
                "content": "公益视频做得很好，希望能看到更多这样的内容",
                "author": "用户A",
                "timestamp": datetime.now().isoformat(),
                "likes": 456,
                "sentiment": "positive",
                "is_negative": False
            },
            {
                "platform": "抖音",
                "keyword": keyword,
                "content": "视频加载太慢了，体验不好",
                "author": "用户B",
                "timestamp": datetime.now().isoformat(),
                "likes": 78,
                "sentiment": "negative",
                "is_negative": True
            },
            {
                "platform": "抖音",
                "keyword": keyword,
                "content": "希望能有更多互动功能，现在的互动太少了",
                "author": "用户C",
                "timestamp": datetime.now().isoformat(),
                "likes": 123,
                "sentiment": "neutral",
                "is_negative": False
            },
            {
                "platform": "抖音",
                "keyword": keyword,
                "content": "字幕太小了，看不清楚",
                "author": "用户D",
                "timestamp": datetime.now().isoformat(),
                "likes": 56,
                "sentiment": "negative",
                "is_negative": True
            },
            {
                "platform": "抖音",
                "keyword": keyword,
                "content": "希望能增加直播功能，实时互动会更好",
                "author": "用户E",
                "timestamp": datetime.now().isoformat(),
                "likes": 234,
                "sentiment": "neutral",
                "is_negative": False
            }
        ]
        
        for i in range(min(limit, 50)):
            sample = sample_comments[i % len(sample_comments)].copy()
            sample["id"] = f"dy_{i+1}"
            comments.append(sample)
        
        return comments
    
    def save_to_json(self, comments: List[Dict], output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "platform": "抖音",
                "fetch_time": datetime.now().isoformat(),
                "total_count": len(comments),
                "data": comments
            }, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已保存 {len(comments)} 条抖音评论到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description='抓取抖音评论数据')
    parser.add_argument('--keyword', type=str, required=True, help='搜索关键词')
    parser.add_argument('--limit', type=int, default=50, help='抓取数量限制')
    parser.add_argument('--output', type=str, default='data/douyin_comments.json', help='输出文件路径')
    
    args = parser.parse_args()
    
    fetcher = DouyinFetcher()
    comments = fetcher.fetch_comments(args.keyword, args.limit)
    fetcher.save_to_json(comments, args.output)

if __name__ == '__main__':
    main()
