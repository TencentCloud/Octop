#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文搜索脚本
支持按信源、关键词、时间范围搜索论文
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# 配置路径
CONFIG_DIR = os.path.expanduser("~/.openclaw/research-monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    """加载配置文件"""
    if not os.path.exists(CONFIG_FILE):
        print(f"错误：配置文件不存在，请先运行 config.py")
        sys.exit(1)
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def search_papers(source, keywords, days):
    """
    搜索论文
    
    实际实现会调用各信源的API或网页搜索
    这里提供框架和示例
    """
    print(f"搜索信源: {source}")
    print(f"关键词: {', '.join(keywords)}")
    print(f"时间范围: 过去 {days} 天")
    
    # 这里应该实现实际的搜索逻辑
    # 可以调用 web_search 工具或其他API
    
    # 返回示例数据
    results = [
        {
            "title": f"Example paper about {keywords[0] if keywords else 'research'}",
            "authors": ["Author A", "Author B"],
            "source": source,
            "url": f"https://{source}.com/paper/12345",
            "published_date": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
            "abstract": "This is an example abstract."
        }
    ]
    
    return results


def main():
    parser = argparse.ArgumentParser(description='搜索学术论文')
    parser.add_argument('--source', '-s', required=True,
                       choices=['arxiv', 'pubmed', 'google_scholar', 'cnki', 'ieee', 'semantic_scholar'],
                       help='搜索的信源')
    parser.add_argument('--keywords', '-k', required=True,
                       help='搜索关键词，多个用逗号分隔')
    parser.add_argument('--days', '-d', type=int, default=7,
                       help='搜索过去多少天的论文 (默认: 7)')
    parser.add_argument('--output', '-o',
                       help='输出文件路径 (JSON格式)')
    
    args = parser.parse_args()
    
    # 解析关键词
    keywords = [k.strip() for k in args.keywords.split(',')]
    
    # 执行搜索
    results = search_papers(args.source, keywords, args.days)
    
    # 输出结果
    print(f"\n找到 {len(results)} 篇论文:")
    for i, paper in enumerate(results, 1):
        print(f"\n{i}. {paper['title']}")
        print(f"   作者: {', '.join(paper['authors'])}")
        print(f"   链接: {paper['url']}")
        print(f"   发布日期: {paper['published_date']}")
    
    # 保存到文件
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")


if __name__ == "__main__":
    main()
