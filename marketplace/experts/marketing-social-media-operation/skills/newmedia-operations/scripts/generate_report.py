#!/usr/bin/env python3
import json
import argparse
from datetime import datetime
from typing import List, Dict

class ReportGenerator:
    def __init__(self):
        self.template = """# {title}

## 1. 执行摘要

### 1.1 数据抓取概况
- 抓取时间：{fetch_time}
- 数据来源：{data_sources}
- 总数据量：{total_data_count} 条
- 有效需求数：{total_demands} 条

### 1.2 核心发现
{core_findings}

### 1.3 关键需求概览
{key_demands}

## 2. 数据来源与方法

### 2.1 数据源列表
{data_sources_list}

### 2.2 数据抓取时间范围
{time_range}

### 2.3 数据清洗方法
- 去重处理：去除重复内容
- 过滤无效数据：删除广告、垃圾信息
- 文本清洗：去除表情符号和特殊字符
- 数据标注：情感倾向、需求类型、紧急程度

### 2.4 分析方法说明
- 需求提取：基于关键词匹配和情感分析
- 需求分类：功能需求、体验需求、服务需求、内容需求
- 优先级评估：综合频率、情感强度、影响范围

## 3. 用户反馈分析

### 3.1 总体反馈情况
- 正面反馈：{positive_count} 条 ({positive_ratio:.1%})
- 负面反馈：{negative_count} 条 ({negative_ratio:.1%})
- 中性反馈：{neutral_count} 条 ({neutral_ratio:.1%})

### 3.2 情感分析结果
{sentiment_analysis}

### 3.3 各平台反馈特点
{platform_characteristics}

## 4. 需求提取结果

### 4.1 需求分类统计
{demand_type_stats}

### 4.2 需求详细列表
{demand_list}

### 4.3 需求关联分析
{demand_correlation}

## 5. 需求分级与优先级

### 5.1 P0级需求（紧急重要）
{p0_demands}

### 5.2 P1级需求（重要不紧急）
{p1_demands}

### 5.3 P2级需求（紧急不重要）
{p2_demands}

### 5.4 P3级需求（不紧急不重要）
{p3_demands}

## 6. 建议与行动计划

### 6.1 短期行动建议（1-3个月）
{short_term_actions}

### 6.2 中期规划建议（3-6个月）
{mid_term_actions}

### 6.3 长期战略建议（6个月以上）
{long_term_actions}

## 7. 附录

### 7.1 原始数据样本
{data_samples}

### 7.2 分析方法说明
{analysis_methods}

### 7.3 参考资料
- 数据来源：各平台公开数据
- 分析工具：Python + 自然语言处理
- 生成时间：{generation_time}
"""
    
    def generate_report(self, data: Dict, title: str = "用户需求调研报告") -> str:
        summary = data.get('summary', {})
        prioritized_demands = data.get('prioritized_demands', [])
        
        total_data_count = summary.get('total_demands', 0)
        total_demands = len(prioritized_demands)
        
        core_findings = self._generate_core_findings(prioritized_demands)
        key_demands = self._generate_key_demands(prioritized_demands)
        
        data_sources = self._generate_data_sources(data)
        data_sources_list = self._generate_data_sources_list(data)
        
        sentiment_analysis = self._generate_sentiment_analysis(data)
        platform_characteristics = self._generate_platform_characteristics(data)
        
        demand_type_stats = self._generate_demand_type_stats(data)
        demand_list = self._generate_demand_list(prioritized_demands)
        
        p0_demands = self._generate_priority_demands(summary.get('P0', []))
        p1_demands = self._generate_priority_demands(summary.get('P1', []))
        p2_demands = self._generate_priority_demands(summary.get('P2', []))
        p3_demands = self._generate_priority_demands(summary.get('P3', []))
        
        short_term_actions = self._generate_actions(summary.get('P0', []), '短期')
        mid_term_actions = self._generate_actions(summary.get('P1', []), '中期')
        long_term_actions = self._generate_actions(summary.get('P2', []) + summary.get('P3', []), '长期')
        
        report = self.template.format(
            title=title,
            fetch_time=data.get('prioritize_time', datetime.now().isoformat()),
            data_sources=data_sources,
            total_data_count=total_data_count,
            total_demands=total_demands,
            core_findings=core_findings,
            key_demands=key_demands,
            data_sources_list=data_sources_list,
            time_range=datetime.now().strftime('%Y-%m-%d'),
            positive_count=0,
            positive_ratio=0.0,
            negative_count=0,
            negative_ratio=0.0,
            neutral_count=0,
            neutral_ratio=0.0,
            sentiment_analysis=sentiment_analysis,
            platform_characteristics=platform_characteristics,
            demand_type_stats=demand_type_stats,
            demand_list=demand_list,
            demand_correlation="基于需求类型和痛点强度的关联分析",
            p0_demands=p0_demands,
            p1_demands=p1_demands,
            p2_demands=p2_demands,
            p3_demands=p3_demands,
            short_term_actions=short_term_actions,
            mid_term_actions=mid_term_actions,
            long_term_actions=long_term_actions,
            data_samples="详见原始数据文件",
            analysis_methods="基于自然语言处理和统计分析",
            generation_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        return report
    
    def _generate_core_findings(self, demands: List[Dict]) -> str:
        if not demands:
            return "暂无核心发现"
        
        findings = []
        for i, demand in enumerate(demands[:3], 1):
            findings.append(f"{i}. {demand['demand_type']} - 出现频率 {demand['frequency']} 次")
        
        return "\n".join(findings)
    
    def _generate_key_demands(self, demands: List[Dict]) -> str:
        if not demands:
            return "暂无关键需求"
        
        key_demands = []
        for i, demand in enumerate(demands[:5], 1):
            key_demands.append(f"{i}. {demand['demand_group']} (P{demand['priority'][-1]})")
        
        return "\n".join(key_demands)
    
    def _generate_data_sources(self, data: Dict) -> str:
        return "小红书、抖音、微博、电商平台"
    
    def _generate_data_sources_list(self, data: Dict) -> str:
        return """- 小红书：用户评论和笔记内容
- 抖音：视频评论和用户互动
- 微博：话题讨论和用户观点
- 电商平台：商品评价和差评"""
    
    def _generate_sentiment_analysis(self, data: Dict) -> str:
        return "基于关键词匹配和情感词典分析"
    
    def _generate_platform_characteristics(self, data: Dict) -> str:
        return """- 小红书：用户更关注产品细节和使用体验
- 抖音：用户更关注视频内容和互动体验
- 微博：用户更关注话题讨论和社会影响
- 电商平台：用户更关注产品质量和服务体验"""
    
    def _generate_demand_type_stats(self, data: Dict) -> str:
        analysis = data.get('analysis', {})
        demand_types = analysis.get('demand_types', {})
        
        if not demand_types:
            return "暂无需求数据统计"
        
        stats = []
        for demand_type, count in demand_types.items():
            stats.append(f"- {demand_type}：{count} 条")
        
        return "\n".join(stats)
    
    def _generate_demand_list(self, demands: List[Dict]) -> str:
        if not demands:
            return "暂无需求列表"
        
        demand_list = []
        for i, demand in enumerate(demands[:10], 1):
            demand_list.append(f"{i}. **{demand['demand_group']}**\n   - 频率：{demand['frequency']} 次\n   - 痛点：{', '.join(demand['pain_points'])}\n   - 样例：{demand['sample_contents'][0] if demand['sample_contents'] else '无'}")
        
        return "\n\n".join(demand_list)
    
    def _generate_priority_demands(self, demands: List[Dict]) -> str:
        if not demands:
            return "暂无该级别需求"
        
        priority_demands = []
        for i, demand in enumerate(demands, 1):
            priority_demands.append(f"{i}. **{demand['demand_group']}**\n   - 频率：{demand['frequency']} 次\n   - 负面比例：{demand['negative_count']/demand['frequency']:.1%}\n   - 平台：{', '.join(demand['platforms'])}")
        
        return "\n\n".join(priority_demands)
    
    def _generate_actions(self, demands: List[Dict], term: str) -> str:
        if not demands:
            return f"暂无{term}行动建议"
        
        actions = []
        for i, demand in enumerate(demands[:3], 1):
            action = f"{i}. 针对「{demand['demand_group']}」问题："
            if '功能' in demand['demand_type']:
                action += "优化产品功能，提升用户体验"
            elif '服务' in demand['demand_type']:
                action += "加强客服培训，提升服务质量"
            elif '体验' in demand['demand_type']:
                action += "简化操作流程，提升使用体验"
            else:
                action += "持续关注用户反馈，优化相关功能"
            actions.append(action)
        
        return "\n".join(actions)
    
    def save_report(self, report: str, output_path: str):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"✅ 已生成需求调研报告到 {output_path}")

def main():
    parser = argparse.ArgumentParser(description='生成需求调研报告')
    parser.add_argument('--input', type=str, required=True, help='输入文件路径')
    parser.add_argument('--output', type=str, default='report/demand_mining_report.md', help='输出文件路径')
    parser.add_argument('--title', type=str, default='用户需求调研报告', help='报告标题')
    
    args = parser.parse_args()
    
    generator = ReportGenerator()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    report = generator.generate_report(data, args.title)
    generator.save_report(report, args.output)

if __name__ == '__main__':
    main()
