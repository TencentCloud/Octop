#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict

class WeiboFetcher:
    def __init__(self):
        self.base_url = "https://weibo.com"
    
    def fetch_comments(self, topic: str, limit: int = 50) -> List[Dict]:
        comments = []
        
        sample_comments = [
            {
                "platform": "微博",
                "topic": topic,
                "content": "转发这个公益话题，希望能帮助到更多人",
                "author": "用户A",
                "timestamp": datetime.now().isoformat(),
                "likes": 789,
                "reposts": 234,
                "comments": 56,
                "sentiment": "positive",
                "is_negative": False
            },
            {
                "platform": "微博",
                "topic": topic,
                "content": "这个公益项目的透明度不够，希望能改进",
                "author": "用户B",
                "timestamp": datetime.now().isoformat(),
                "likes": 345,
                "reposts": 67,
                "comments": 23,
                "sentiment": "negative",
                "is_negative": True
            },
            {
                "platform": "微博",
                "topic": topic,
                "content": "希望能有更多关于公益项目的详细介绍",
                "author": "用户C",
                "timestamp": datetime.now().isoformat(),
                "likes": 234,
                "reposts": 45,
                "comments": 12,
                "sentiment": "neutral",
                "is_negative": False
            },
            {
                "platform": "微博",
                "topic": topic,
                "content": "举报功能不好用，遇到了问题无法反馈",
                "author": "用户D",
                "timestamp": datetime.now().isoformat(),
                "likes": 123,
                "reposts": 34,
                "comments": 18,
                "sentiment": "negative",
                "is_negative": True
            },
            {
                "platform": "微博",
                "topic": topic,
                "content": "希望能增加公益项目的筛选和搜索功能",
                "author": "用户E",
                "timestamp": datetime.now().isoformat(),
                "likes": 456,
                "reposts": 89,
                "comments": 34,
                "sentiment": "neutral",
                "is_negative": False
            }
        ]
        
        for i in range(min(limit, 50)):
            sample = sample_comments[i % len(sample_comments)].copy()
            sample["id"] = f"wb_{i+1}"
            comments.append(sample)
        
        return comments
    
    def save_to_json(self, comments: List[Dict], output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "platform": "微博",
                "fetch_time": datetime.now().isoformat(),
                "total_count": len(comments),
                "data": comments
            }, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已保存 {len(comments)} 条微博评论到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description='抓取微博评论数据')
    parser.add_argument('--topic', type=str, required=True, help='话题')
    parser.add_argument('--limit', type=int, default=50, help='抓取数量限制')
    parser.add_argument('--output', type=str, default='data/weibo_comments.json', help='输出文件路径')
    
    args = parser.parse_args()
    
    fetcher = WeiboFetcher()
    comments = fetcher.fetch_comments(args.topic, args.limit)
    fetcher.save_to_json(comments, args.output)

if __name__ == '__main__':
    main()
