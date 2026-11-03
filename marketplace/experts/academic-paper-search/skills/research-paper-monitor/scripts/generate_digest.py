#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成文献综述摘要
汇总指定时间段内的文献，生成综述报告
"""

import argparse
import json
import os
from datetime import datetime, timedelta

# 配置路径
CONFIG_DIR = os.path.expanduser("~/.openclaw/research-monitor")
INDEX_FILE = os.path.join(CONFIG_DIR, "literature-index.json")
REPORTS_DIR = os.path.expanduser("~/.openclaw/research-monitor/daily-reports")


def load_index():
    """加载文献索引"""
    if not os.path.exists(INDEX_FILE):
        return {"papers": []}
    
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_papers_in_date_range(days):
    """获取指定日期范围内的论文"""
    index = load_index()
    cutoff_date = datetime.now() - timedelta(days=days)
    
    papers = []
    for paper in index.get('papers', []):
        collected_date = paper.get('collected_date', '')
        if collected_date:
            try:
                paper_date = datetime.strptime(collected_date, '%Y-%m-%d')
                if paper_date >= cutoff_date:
                    papers.append(paper)
            except ValueError:
                continue
    
    return papers


def generate_digest(papers, days):
    """生成综述报告"""
    now = datetime.now()
    start_date = now - timedelta(days=days)
    
    # 分类统计
    by_source = {}
    by_score = {'high': [], 'medium': [], 'low': []}
    
    for paper in papers:
        # 按信源分类
        source = paper.get('source', 'unknown')
        by_source.setdefault(source, []).append(paper)
        
        # 按评分分类
        score = paper.get('score', 0)
        if score >= 80:
            by_score['high'].append(paper)
        elif score >= 50:
            by_score['medium'].append(paper)
        else:
            by_score['low'].append(paper)
    
    # 构建报告
    report = f"""# 文献综述报告

**报告周期**: {start_date.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}  
**生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}

## 统计概览

| 指标 | 数量 |
|------|------|
| 新增论文总数 | {len(papers)} 篇 |
| 高相关论文 (≥80分) | {len(by_score['high'])} 篇 |
| 中等相关 (50-79分) | {len(by_score['medium'])} 篇 |
| 低相关 (<50分) | {len(by_score['low'])} 篇 |

## 按信源分布

"""
    
    for source, source_papers in sorted(by_source.items()):
        report += f"- **{source.upper()}**: {len(source_papers)} 篇\n"
    
    report += "\n## 高相关论文详情\n\n"
    
    for i, paper in enumerate(by_score['high'], 1):
        report += f"""### {i}. {paper['title']}

- **作者**: {', '.join(paper.get('authors', ['Unknown']))}
- **来源**: {paper.get('source', 'Unknown')}
- **评分**: {paper.get('score', 0)}/100
- **链接**: {paper.get('url', 'N/A')}
- **本地文件**: {paper.get('local_file', 'N/A')}
- **采集日期**: {paper.get('collected_date', 'Unknown')}

"""
    
    if by_score['medium']:
        report += "## 中等相关论文列表\n\n"
        for paper in by_score['medium']:
            report += f"- [{paper['title']}]({paper.get('url', '#')}) - 评分: {paper.get('score', 0)}\n"
    
    report += """
## 研究趋势分析

基于本期采集的论文，可以观察到以下研究趋势：

（此处可由AI根据论文内容生成趋势分析）

"""
    
    return report


def main():
    parser = argparse.ArgumentParser(description='生成文献综述摘要')
    parser.add_argument('--days', '-d', type=int, default=7,
                       help='汇总过去多少天的论文 (默认: 7)')
    parser.add_argument('--output', '-o', required=True,
                       help='输出文件路径 (Markdown格式)')
    
    args = parser.parse_args()
    
    # 获取论文
    print(f"获取过去 {args.days} 天的论文...")
    papers = get_papers_in_date_range(args.days)
    print(f"找到 {len(papers)} 篇论文")
    
    # 生成综述
    print("生成综述报告...")
    report = generate_digest(papers, args.days)
    
    # 保存报告
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✓ 综述报告已保存到: {args.output}")
    print(f"  包含 {len(papers)} 篇论文")
    print(f"  其中高相关论文: {len([p for p in papers if p.get('score', 0) >= 80])} 篇")


if __name__ == "__main__":
    main()
